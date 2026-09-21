"""I2 测试数据基座 · 行生成器与灌数（I2 设计文档 §6）。

设计要点：
- 配置驱动：字段策略来自 tables.yaml，脏注入来自 dirty_rules.yaml（计数驱动）
- 确定性：每表/每列/每规则派生独立随机源（seed:{seed}:{名}；faker 按「表:列/计算名」独立播种），同 seed 逐行一致
- 时间一致性：订单时间由行位置确定性函数推导（order_day/order_ctime），
  子表（item/payment/refund）无需驻留父表数据即可对齐时间——内存约束（用户规则）
- 写入：pymysql executemany 批量 + 每表单事务；不落中间 SQL/CSV 文件
- 分区滚动：gen 前置 REORG——TRUNCATE → DROP 旧日分区 → REORGANIZE pmax
  按运行日 T 重建（DDL 单源于 init SQL，生成器只做分区手术，无 DDL 重复）
- dw 派生种子：src/dw 跨容器无法单语句 INSERT...SELECT，由本模块以双连接
  流式搬运（转换逻辑与 infra/mysql/dw/init/02_seed_dwd.sql 保持一致）
"""

import random
import time as time_mod
from dataclasses import replace
from datetime import date, datetime, time, timedelta

import pymysql
from faker import Faker

from tools.datagen.config import DatagenConfig, RuleSpec, TableSpec, anchor_blocks, run_today

# 灌数拓扑序（先维表后事实；coupon 先于 usage——usage_time 读取券有效期缓存）
GEN_ORDER = [
    "dim_category", "dim_supplier", "dim_goods", "dim_user", "dim_user_address",
    "ods_cart", "dim_inventory", "ods_order", "ods_order_item", "ods_payment",
    "ods_refund", "ods_coupon", "ods_coupon_usage", "dim_promotion_activity",
    "sec_user_identity", "sec_bank_card", "sec_supplier_contract",
]

CAT_TOP = [
    "手机数码", "家用电器", "服饰鞋包", "美妆个护", "食品生鲜", "母婴玩具",
    "图书文娱", "运动户外", "家居家装", "汽车用品", "医药保健", "宠物生活",
    "珠宝钟表", "酒水饮料", "办公设备", "虚拟充值", "厨具餐具", "灯饰照明",
    "五金工具", "箱包配饰", "鲜花绿植", "乐器音像", "教育培训", "本地生活",
]
CAT_TOP_N = len(CAT_TOP)
GOODS_NOUN = [
    "手机", "平板电脑", "笔记本电脑", "蓝牙耳机", "智能手表", "电视机",
    "空调", "冰箱", "洗衣机", "电饭煲", "加湿器", "电动牙刷", "洗发水",
    "防晒霜", "运动鞋", "羽绒服", "双肩包", "保温杯", "桌面台灯", "机械键盘",
    "游戏手柄", "坚果礼盒", "益生菌", "猫粮",
]
SUP_SUFFIX = [
    "科技有限公司", "贸易有限公司", "实业有限公司", "电子商务有限公司",
    "网络科技有限公司", "供应链管理有限公司",
]


# ---------------- 确定性时间推导（跨表共享，零内存驻留） ----------------

def order_day(pos: int, today: date, days: int = 90) -> date:
    """订单所在日：行位置 → [T-(days-1), T] 乘法散列均匀散布。"""
    idx = (pos * 2654435761 + 11) % days
    return today - timedelta(days=days - 1 - idx)


def order_ctime(pos: int, today: date, days: int = 90) -> datetime:
    """订单下单时间：日期散布 + 当日秒数由行位置确定。"""
    secs = (pos * 40503 + 7) % 86400
    return datetime.combine(order_day(pos, today, days),
                            time(secs // 3600, (secs % 3600) // 60, secs % 60))


def _rand_time(rng: random.Random) -> time:
    return time(rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59))


def _seeded_faker(ctx: "GenCtx", ns: str) -> Faker:
    """按命名空间独立播种的 zh_CN Faker（同 seed 逐行一致；消费者互不干扰）。"""
    f = Faker("zh_CN")
    f.seed_instance(f"{ctx.cfg.seed}:{ns}")
    return f


class GenCtx:
    """生成上下文（跨表共享仅小体量缓存，内存约束）。"""

    def __init__(self, cfg: DatagenConfig, today: date):
        self.cfg = cfg
        self.today = today
        self.days = cfg.window_days
        self.rows_of = {t.name: t.rows for t in cfg.tables}
        self.cache = {}  # 如 ods_coupon: [(valid_from, valid_to)]（5k 行小缓存）


# ---------------- 列生成器 ----------------

def build_producer(col, table: TableSpec, ctx: GenCtx, rng: random.Random):
    """按策略构造 f(pos, row) -> value 生成闭包。"""
    s = col.strategy

    if s == "seq":
        return lambda pos, row: pos + 1
    if s.startswith("const:"):
        v = s[6:]
        return lambda pos, row: v
    if s == "null":
        return lambda pos, row: None
    if s.startswith("int:"):
        _, lo, hi = s.split(":")
        lo, hi = int(lo), int(hi)
        return lambda pos, row: rng.randint(lo, hi)
    if s.startswith("dec:"):
        _, lo, hi, scale = s.split(":")
        lo, hi, scale = float(lo), float(hi), int(scale)
        f = 10 ** scale
        return lambda pos, row: rng.randint(int(lo * f), int(hi * f)) / f
    if s.startswith("choice:"):
        vals = s[7:].split("|")
        return lambda pos, row: rng.choice(vals)
    if s.startswith("faker:"):
        fn = getattr(_seeded_faker(ctx, f"{table.name}:{col.name}"), s[6:])
        return lambda pos, row: fn()
    if s.startswith("ref:"):
        n = ctx.rows_of[s[4:].split(".")[0]]
        return lambda pos, row: rng.randint(1, n)
    if s.startswith("phone:"):
        prefix = s[6:]
        return lambda pos, row: f"{prefix}{(pos + 1) % 100000000:08d}"
    if s == "randphone":
        return lambda pos, row: f"13{rng.randint(0, 999999999):09d}"
    if s.startswith("calc:"):
        return _build_calc(s[5:], table, ctx, rng)
    raise ValueError(f"未知策略：{s}（表 {table.name}.{col.name}）")  # pragma: no cover


def _build_calc(name: str, table: TableSpec, ctx: GenCtx, rng: random.Random):
    """命名计算器：跨列推导与时间一致性逻辑。"""
    today, days = ctx.today, ctx.days

    if name == "username":
        return lambda pos, row: f"user_{(pos + 1):06d}"
    if name == "nickname":
        fk = _seeded_faker(ctx, f"{table.name}:{name}")
        return lambda pos, row: f"{fk.word()}_{(pos + 1):04d}"
    if name == "order_no":
        return lambda pos, row: f"SO{(pos + 1):010d}"
    if name == "contract_no":
        return lambda pos, row: f"CT2026{(pos + 1):06d}"
    if name == "coupon_name":
        return lambda pos, row: f"{rng.choice(['满减', '折扣', '新人', '会员', '节日'])}券{(pos + 1):04d}"
    if name == "activity_name":
        fk = _seeded_faker(ctx, f"{table.name}:{name}")
        return lambda pos, row: f"{fk.word()}促销活动{(pos + 1):03d}"
    if name == "supplier_name":
        fk = _seeded_faker(ctx, f"{table.name}:{name}")
        return lambda pos, row: f"{fk.city_name()}{rng.choice(SUP_SUFFIX)}"
    if name == "goods_name":
        fk = _seeded_faker(ctx, f"{table.name}:{name}")
        return lambda pos, row: f"{rng.choice(GOODS_NOUN)}{fk.word()}({(pos + 1):05d})"
    if name == "cat_name":
        return lambda pos, row: (CAT_TOP[pos] if pos < CAT_TOP_N
                                 else f"{CAT_TOP[(pos * 7) % CAT_TOP_N]}-{CAT_TOP[pos % CAT_TOP_N]}")
    if name == "cat_parent":
        return lambda pos, row: (None if pos < CAT_TOP_N else rng.randint(1, CAT_TOP_N))
    if name == "cat_level":
        return lambda pos, row: 1 if pos < CAT_TOP_N else 2
    if name == "credit_unique":
        return lambda pos, row: f"91{(pos + 1):010d}{rng.randint(0, 999999):06d}"
    if name == "card_no":
        return lambda pos, row: f"62{(pos + 1):016d}"
    if name == "cost_price":
        return lambda pos, row: round((row["price"] or 0) * 0.6, 2)
    if name == "item_amount":
        return lambda pos, row: round(row["qty"] * row["unit_price"], 2)
    if name == "min_spend":
        return lambda pos, row: round((row["discount"] or 0) * 2 + 10, 2)
    if name == "remark":
        fk = _seeded_faker(ctx, f"{table.name}:{name}")
        return lambda pos, row: f"{fk.word()}备注"
    if name == "order_ctime":
        return lambda pos, row: order_ctime(pos, today, days)
    if name == "order_date_self":
        return lambda pos, row: order_day(pos, today, days)
    if name == "item_order_date":
        return lambda pos, row: order_day(row["order_id"] - 1, today, days)
    if name == "pay_time":
        return lambda pos, row: (order_ctime(row["order_id"] - 1, today, days)
                                 + timedelta(seconds=rng.randint(60, 7200)))
    if name == "date_of_pay":
        return lambda pos, row: row["pay_time"].date()
    if name == "refund_time":
        return lambda pos, row: (order_ctime(row["order_id"] - 1, today, days)
                                 + timedelta(days=rng.randint(1, 7), seconds=rng.randint(0, 86399)))
    if name == "coupon_from":
        return lambda pos, row: today - timedelta(days=rng.randint(0, 60))
    if name == "coupon_to":
        return lambda pos, row: row["valid_from"] + timedelta(days=rng.randint(15, 90))
    if name == "usage_time":
        def f(pos, row):
            valid_from, valid_to = ctx.cache["ods_coupon"][row["coupon_id"] - 1]
            span = max((valid_to - valid_from).days, 0)
            return datetime.combine(valid_from + timedelta(days=rng.randint(0, span)), _rand_time(rng))
        return f
    if name == "register_time":
        return lambda pos, row: datetime.combine(today - timedelta(days=rng.randint(0, 720)), _rand_time(rng))
    if name == "cart_time":
        return lambda pos, row: datetime.combine(today - timedelta(days=rng.randint(0, 30)), _rand_time(rng))
    if name == "window_dt":
        return lambda pos, row: datetime.combine(today - timedelta(days=rng.randint(0, days - 1)), _rand_time(rng))
    if name == "act_end":
        return lambda pos, row: (row["start_time"] + timedelta(days=rng.randint(7, 30), seconds=rng.randint(0, 86399)))
    if name == "expire_date":
        def f(pos, row):
            m = today.month + rng.randint(1, 60)
            return f"{(m - 1) % 12 + 1:02d}/{today.year + (m - 1) // 12}"
        return f
    if name == "snapshot_today":
        return lambda pos, row: today
    raise ValueError(f"未知 calc 计算器：{name}（表 {table.name}）")  # pragma: no cover


# ---------------- 脏注入计划 ----------------

class DirtyPlan:
    """计数驱动脏注入：位置采样 + 锚定块，apply() 逐行变换。

    采样顺序（防跨规则计数串扰，保证 reconcile 严格相等）：
      1) 值型规则锚定块（表尾，config.anchor_blocks）
      2) 值型规则随机位（池排除锚定块与 {0,1,2}）
      3) duplicate_row 随机位（池排除值型位，且 p-1 也必须值干净——dup 复制
         上一行最终内容，若 p-1 带脏值会使该规则计数 +1）；锚定重复对 =
         行位 2 复制行位 1（对 = PK 2、3；每个 dup 位恰贡献 1 个邻接对，
         actual = |D| = 随机位 + 锚定对，与随机位是否相邻无关）
      4) phone_pair 同号对（池排除值型位与 dup 位；leader/follower 按 sorted
         连续配对，follower 继承 leader 基础手机号）
    """

    def __init__(self, table: TableSpec, rules: list, ctx: GenCtx):
        self.table = table
        self.ctx = ctx
        self.blocks = anchor_blocks(table, rules)
        value_anchor = set()
        for s, _e in self.blocks.values():
            value_anchor.update(range(s, _e + 1))
        reserved = value_anchor | {0, 1, 2}   # 行 0 无前驱；1/2 留给锚定重复对

        self.dup_positions = set()      # duplicate_row：该行=复制上一行内容（PK 除外）
        self.pair_map = {}              # phone_pair：follower_pos -> leader_pos
        self.by_pos = {}                # pos -> [(rule, is_anchor, ord_)]

        # 1+2) 值型规则：锚定块 + 随机位
        pool_v = [p for p in range(table.rows) if p not in reserved]
        for r in rules:
            if r.kind in ("duplicate_row", "phone_pair"):
                continue
            pick_rng = random.Random(f"{ctx.cfg.seed}:{table.name}:{r.id}:pick")
            total = r.expected_total(table)
            if r.anchor:
                s, e = self.blocks[r.id]
                for pos in range(s, e + 1):
                    self.by_pos.setdefault(pos, []).append((r, True, pos - s + 1))
            for pos in pick_rng.sample(pool_v, total - r.anchor):
                self.by_pos.setdefault(pos, []).append((r, False, 0))
        value_positions = value_anchor | set(self.by_pos)

        # 3) duplicate_row（锚定对 = PK2、PK3：行位 1 正常、行位 2 复制行位 1）
        dup_rules = [r for r in rules if r.kind == "duplicate_row"]
        if dup_rules:
            pool_d = [p for p in range(3, table.rows)
                      if p not in value_positions and (p - 1) not in value_positions]
            for r in dup_rules:
                pick_rng = random.Random(f"{ctx.cfg.seed}:{table.name}:{r.id}:pick")
                total = r.expected_total(table)
                self.dup_positions.update(pick_rng.sample(pool_d, total - r.anchor))
            if any(r.anchor for r in dup_rules):
                self.dup_positions.add(2)

        # 4) phone_pair（同号不同户对）
        for r in (x for x in rules if x.kind == "phone_pair"):
            pick_rng = random.Random(f"{ctx.cfg.seed}:{table.name}:{r.id}:pick")
            pool_p = [p for p in range(table.rows)
                      if p not in value_positions and p not in self.dup_positions]
            picks = sorted(pick_rng.sample(pool_p, r.expected_total(table) * 2))
            for i in range(0, len(picks) - 1, 2):
                self.pair_map[picks[i + 1]] = picks[i]

    def apply(self, row: dict, pos: int) -> None:
        for r, is_anchor, ord_ in self.by_pos.get(pos, ()):
            self._transform(r, row, pos, is_anchor, ord_)
        if pos in self.pair_map:
            row["phone"] = f"139{(self.pair_map[pos] + 1):08d}"  # 前缀对齐 tables.yaml phone:139

    def _transform(self, r: RuleSpec, row: dict, pos: int, is_anchor: bool, ord_: int) -> None:
        k, col, p = r.kind, r.column, r.params
        ctx, today, days = self.ctx, self.ctx.today, self.ctx.days
        if k == "null_value":
            row[col] = None
        elif k == "format_phone":
            row[col] = f"1X{(pos + 1):09d}"          # 唯一化：含字母 11 位
        elif k == "format_idcard":
            row[col] = f"{(pos + 1):017d}Q"          # 唯一化：校验位非法
        elif k == "format_credit":
            row[col] = f"91BAD0{(pos + 1):012d}"     # 唯一化：含字母
        elif k == "out_of_range":
            row[col] = p["values"][pos % len(p["values"])]
        elif k == "enum_out":
            row[col] = p["value"]
        elif k == "orphan":
            if is_anchor:
                row[col] = p["anchor_from"] + ord_ - 1
            else:
                row[col] = ctx.rows_of[p["parent"].split(".")[0]] + 1000 + (pos % 500)
        elif k == "time_future":
            row[col] = datetime.strptime(p["value"], "%Y-%m-%d %H:%M:%S")
            if self.table.name == "ods_payment":
                row["pay_date"] = row[col].date()    # 落 pmax 分区，分区键同步
        elif k == "time_invalid":
            row[col] = datetime.strptime(p["values"][pos % len(p["values"])], "%Y-%m-%d %H:%M:%S")
        elif k == "time_before_order":
            row[col] = order_ctime(row["order_id"] - 1, today, days) - timedelta(seconds=p.get("offset", 7200))
            if self.table.name == "ods_payment":
                row["pay_date"] = row[col].date()
        elif k == "time_before_coupon":
            valid_from = ctx.cache["ods_coupon"][row["coupon_id"] - 1][0]
            row[col] = datetime.combine(valid_from - timedelta(days=p.get("offset_days", 5)), time(0, 0, 0))
        elif k == "dirty_chars":
            marker = p["marker"]
            row[col] = f" {marker}脏数据\x07 " if is_anchor else f" {row[col]} {marker}\x07"
        elif k in ("duplicate_row", "phone_pair"):
            pass  # 结构型规则在采样/行循环中处理


# ---------------- 行迭代（gen 与 samples 共用） ----------------

def iter_rows(table: TableSpec, rules: list, ctx: GenCtx, rows: int = 0):
    """逐行产出 (row_dict, content_list)：content 为插入用值序列（含脏变换）。"""
    total = rows or table.rows
    plan = DirtyPlan(table, rules, ctx)
    cols = table.columns
    rngs = {c.name: random.Random(f"{ctx.cfg.seed}:{table.name}:{c.name}") for c in cols}
    producers = [build_producer(c, table, ctx, rngs[c.name]) for c in cols]
    prev_content = None
    for pos in range(total):
        row = {}
        for c, prod in zip(cols, producers):
            row[c.name] = prod(pos, row)
        plan.apply(row, pos)
        if table.name == "ods_coupon":
            ctx.cache.setdefault("ods_coupon", []).append((row["valid_from"], row["valid_to"]))
        if pos in plan.dup_positions and prev_content is not None:
            content = list(prev_content)
            content[0] = pos + 1                       # 同内容重复行：仅主键不同
        else:
            content = [row[c.name] for c in cols]
        prev_content = content
        yield row, content


# ---------------- 建表维护（分区滚动手术） ----------------

def reorg(conn, table: TableSpec, ctx: GenCtx) -> None:
    """gen 前置：清空表；分区表按运行日 T 滚动重建日分区（90+pmax=91）。"""
    with conn.cursor() as cur:
        if not table.is_partitioned:
            cur.execute(f"TRUNCATE TABLE {table.name}")
            return
        cur.execute(f"TRUNCATE TABLE {table.name}")
        cur.execute(
            "SELECT PARTITION_NAME FROM information_schema.PARTITIONS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND PARTITION_NAME IS NOT NULL",
            (table.name,),
        )
        names = [r[0] for r in cur.fetchall()]
        if "pmax" not in names:
            raise RuntimeError(f"表 {table.name} 缺少 pmax 分区，请先执行 init SQL（install/reset）")
        day_parts = [n for n in names if n != "pmax"]
        if day_parts:
            cur.execute(f"ALTER TABLE {table.name} DROP PARTITION {','.join(day_parts)}")
        today, n = ctx.today, table.partition_days
        days = [today - timedelta(days=n - 1 - i) for i in range(n)]
        defs = ",".join(
            f"PARTITION p{d.strftime('%Y%m%d')} VALUES LESS THAN ('{(d + timedelta(days=1)).isoformat()}')"
            for d in days
        )
        reorg_sql = (f"ALTER TABLE {table.name} REORGANIZE PARTITION pmax INTO "
                     f"({defs}, PARTITION pmax VALUES LESS THAN (MAXVALUE))")
        cur.execute(reorg_sql)


def connect(dsn: dict):
    return pymysql.connect(
        host=dsn["host"], port=dsn["port"], user=dsn["user"], password=dsn["pwd"],
        database=dsn["db"], charset="utf8mb4", autocommit=False,
    )


def gen_table(conn, table: TableSpec, rules: list, ctx: GenCtx, log=print) -> int:
    """清表 + 批量灌数（每表单事务）。返回插入行数。"""
    t0 = time_mod.time()
    reorg(conn, table, ctx)
    cols = table.columns
    sql = f"INSERT INTO {table.name} ({','.join(c.name for c in cols)}) VALUES ({','.join(['%s'] * len(cols))})"
    cur = conn.cursor()
    buf, inserted = [], 0
    try:
        for _row, content in iter_rows(table, rules, ctx):
            buf.append(content)
            if len(buf) >= ctx.cfg.batch_size:
                cur.executemany(sql, buf)
                inserted += len(buf)
                buf = []
                if log:
                    log(f"    [gen] {table.name} {inserted:,}/{table.rows:,}")
        if buf:
            cur.executemany(sql, buf)
            inserted += len(buf)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    if log:
        log(f"[gen] {table.name} 完成 {inserted:,} 行（{time_mod.time() - t0:.1f}s）")
    return inserted


def seed_dw(src_conn, dw_conn, cfg: DatagenConfig, log=print) -> int:
    """dw 派生种子：item 驱动 LEFT JOIN，src 流式读 → dw 批量写（内存安全）。"""
    t0 = time_mod.time()
    with dw_conn.cursor() as wcur:
        wcur.execute("TRUNCATE TABLE dwd_order_detail")
    read_sql = (
        "SELECT i.id, o.id, o.order_no, o.user_id, i.goods_id, g.goods_name, g.category_id, "
        "i.qty, i.unit_price, i.item_amount, o.status, p.pay_channel, p.pay_amount, o.order_date "
        "FROM ods_order_item i "
        "LEFT JOIN ods_order o ON i.order_id = o.id "
        "LEFT JOIN dim_goods g ON i.goods_id = g.id "
        "LEFT JOIN (SELECT order_id, MIN(pay_channel) AS pay_channel, SUM(pay_amount) AS pay_amount "
        "           FROM ods_payment GROUP BY order_id) p ON p.order_id = o.id"
    )
    insert_sql = (
        "INSERT INTO dwd_order_detail (item_id, order_id, order_no, user_id, goods_id, goods_name, "
        "category_id, qty, unit_price, item_amount, order_status, pay_channel, pay_amount, order_date) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
    )
    rcur = src_conn.cursor(pymysql.cursors.SSCursor)  # 流式游标：不驻留全量结果
    wcur = dw_conn.cursor()
    n, buf = 0, []
    try:
        rcur.execute(read_sql)
        for r in rcur:
            buf.append(r)
            if len(buf) >= cfg.batch_size:
                wcur.executemany(insert_sql, buf)
                n += len(buf)
                buf = []
                if log:
                    log(f"    [seed_dw] {n:,}")
        if buf:
            wcur.executemany(insert_sql, buf)
            n += len(buf)
        dw_conn.commit()
    except Exception:
        dw_conn.rollback()
        raise
    finally:
        rcur.close()
        wcur.close()
    if log:
        log(f"[seed_dw] dwd_order_detail 完成 {n:,} 行（{time_mod.time() - t0:.1f}s）")
    return n


def run_gen(cfg: DatagenConfig, log=print) -> dict:
    """gen 模式主流程：灌 src 17 表 → dw 种子 → 自动对账。"""
    today = run_today()
    log(f"[gen] 运行日 T={today} seed={cfg.seed} 窗口 {cfg.window_days} 天")
    ctx = GenCtx(cfg, today)
    src = connect(cfg.dsn("src"))
    dw = connect(cfg.dsn("dw"))
    try:
        t0 = time_mod.time()
        total = 0
        for name in GEN_ORDER:
            t = cfg.table(name)
            total += gen_table(src, t, cfg.rules_of(name), ctx, log)
        log(f"[gen] src 灌数完成：{total:,} 行（{time_mod.time() - t0:.1f}s）")
        seed_dw(src, dw, cfg, log)
        # 生成即对账（I2 设计文档 §7）
        from tools.datagen.reconcile import run_verify
        return run_verify(cfg, log)
    finally:
        src.close()
        dw.close()


def plan_table_copy(table: TableSpec, rows: int) -> TableSpec:
    """行数覆盖副本（samples 小体量生成用，不改动原配置）。"""
    return replace(table, rows=rows)
