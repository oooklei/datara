"""I2 测试数据基座 · 配置加载与生成计划（I2 设计文档 §6.2）。

数据契约：tables.yaml（schema 分组的表清单）+ dirty_rules.yaml（脏规则声明）。
本模块只做结构解析/校验/计划计算，不连库——plan 模式本机 dry-run 依托此性质。

关键约定：
- 脏注入为「计数驱动」：expected_total = 规则声明 count 或 round(rows*ratio)，
  其中锚定行从 expected_total 中切出（expected = random_k + anchor），生成器
  按精确条数注入 → reconcile 的 expected/actual 严格相等，无容差。
- 锚定段布局：每表按规则 id 排序、自表尾切互不重叠的锚定块（值型规则）；
  duplicate_row（重复对）与 phone_pair（同号对）为结构型规则，不占锚定块。
- DSN 解析：tables.yaml 声明 [环境变量名, 默认值]，容器内由 compose 注入。
"""

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

# 规则种类全集（dirty_rules.yaml kind 字段）
KNOWN_KINDS = {
    "null_value", "format_phone", "format_idcard", "format_credit",
    "out_of_range", "enum_out", "orphan", "time_future", "time_invalid",
    "time_before_order", "time_before_coupon", "dirty_chars",
    "duplicate_row", "phone_pair",
}

# 列生成策略前缀全集（tables.yaml strategy 字段）
STRATEGY_PREFIXES = ("seq", "const:", "null", "int:", "dec:", "choice:",
                     "faker:", "ref:", "phone:", "randphone", "calc:")


class ConfigError(Exception):
    """配置结构/引用错误（plan 阶段提前失败，不进容器才发现）。"""


@dataclass
class ColumnSpec:
    name: str
    ctype: str
    strategy: str
    nullable: bool = False
    comment: str = ""


@dataclass
class TableSpec:
    name: str
    schema_name: str
    db: str                     # src / dw
    rows: int
    columns: list  # list[ColumnSpec]
    partition_column: str = ""  # 空=不分区
    partition_days: int = 0     # >0=按天分区（+pmax 兜底）
    sec_level: str = ""         # 机密/绝密（空=业务表）
    derived: bool = False       # dw 派生表（seed 物化，不逐行生成）
    comment: str = ""

    @property
    def pk(self) -> str:
        return self.columns[0].name

    @property
    def col_names(self) -> list:
        return [c.name for c in self.columns]

    @property
    def is_partitioned(self) -> bool:
        return self.partition_days > 0

    @property
    def partition_count(self) -> int:
        return self.partition_days + 1 if self.is_partitioned else 0

    @property
    def is_business(self) -> bool:
        """是否计入 1,077,200 主口径（机密表另计）。"""
        return not self.sec_level and not self.derived


@dataclass
class RuleSpec:
    id: str
    table: str
    kind: str
    column: str = ""
    ratio: float = 0.0
    anchor: int = 0
    params: dict = field(default_factory=dict)

    def expected_total(self, table: TableSpec) -> int:
        """期望脏单元总数（计数驱动：锚定行含在内）。"""
        if self.params.get("count") is not None:
            return int(self.params["count"])
        prod = table.rows * self.ratio
        if abs(prod - round(prod)) > 1e-9:
            raise ConfigError(f"规则 {self.id}：rows*ratio={prod} 非整数（计数驱动要求整除），请调整 ratio")
        return int(round(prod))


@dataclass
class DatagenConfig:
    seed: int
    window_days: int
    batch_size: int
    target_rows_total: int
    tables: list  # list[TableSpec]
    rules: list  # list[RuleSpec]
    dsn_env: dict
    relations: list

    def table(self, name: str) -> TableSpec:
        for t in self.tables:
            if t.name == name:
                return t
        raise ConfigError(f"未知表：{name}")

    def rules_of(self, table_name: str) -> list:
        return [r for r in self.rules if r.table == table_name]

    def business_tables(self) -> list:
        return [t for t in self.tables if t.is_business]

    def dsn(self, which: str) -> dict:
        """解析 DSN：tables.yaml 声明 [环境变量名, 默认值]。"""
        if which not in self.dsn_env:
            raise ConfigError(f"tables.yaml dsn_env 缺少 {which} 配置")
        out = {}
        for key, pair in self.dsn_env[which].items():
            env_name, default = pair[0], pair[1]
            out[key] = os.environ.get(env_name, str(default))
        out["port"] = int(out["port"])
        return out


def run_today() -> date:
    """运行日 T（分区窗口 T-89~T 的基准）。"""
    return date.today()


def anchor_blocks(table: TableSpec, rules: list) -> dict:
    """每表锚定块布局：按规则 id 排序自表尾切块（0 基闭区间，互不重叠）。

    结构型规则（duplicate_row/phone_pair）不占块——它们的锚定由采样实现。
    """
    blocks = {}
    cursor = table.rows
    for r in sorted(rules, key=lambda x: x.id):
        if r.anchor > 0 and r.kind not in ("duplicate_row", "phone_pair"):
            blocks[r.id] = (cursor - r.anchor, cursor - 1)
            cursor -= r.anchor
    return blocks


# ---------------- 配置加载与校验 ----------------

def load_config(datagen_dir: Path) -> DatagenConfig:
    datagen_dir = Path(datagen_dir)
    with open(datagen_dir / "tables.yaml", encoding="utf-8") as f:
        raw_t = yaml.safe_load(f)
    with open(datagen_dir / "dirty_rules.yaml", encoding="utf-8") as f:
        raw_r = yaml.safe_load(f) or {}
    if not raw_t or "global" not in raw_t or "schemas" not in raw_t:
        raise ConfigError("tables.yaml 缺少 global/schemas 顶层结构")

    g = raw_t["global"]
    known_global = {"seed", "window_days", "batch_size", "target_rows_total", "dsn_env"}
    unknown = set(g) - known_global
    if unknown:
        raise ConfigError(f"tables.yaml global 未知键：{sorted(unknown)}")

    tables, seen = [], set()
    for schema_name, schema in (raw_t.get("schemas") or {}).items():
        db = schema.get("db")
        if db not in ("src", "dw"):
            raise ConfigError(f"schema {schema_name} 的 db 必须为 src/dw")
        for t in schema.get("tables") or []:
            _validate_table(t, schema_name, db, seen)
            cols = [ColumnSpec(
                name=c["name"], ctype=c["type"], strategy=c.get("strategy") or "",
                nullable=bool(c.get("nullable", False)), comment=c.get("comment", ""),
            ) for c in t["columns"]]
            part = t.get("partition") or {}
            tables.append(TableSpec(
                name=t["name"], schema_name=schema_name, db=db, rows=int(t["rows"]),
                columns=cols, partition_column=part.get("column", ""),
                partition_days=int(part.get("days", 0)), sec_level=t.get("sec_level", ""),
                derived=bool(t.get("derived", False)), comment=t.get("comment", ""),
            ))

    rules = []
    for r in raw_r.get("rules") or []:
        rules.append(_validate_rule(r, tables))

    cfg = DatagenConfig(
        seed=int(g["seed"]), window_days=int(g["window_days"]), batch_size=int(g["batch_size"]),
        target_rows_total=int(g["target_rows_total"]), tables=tables, rules=rules,
        dsn_env=g["dsn_env"], relations=raw_t.get("relations") or [],
    )
    _validate_totals(cfg)
    return cfg


def _validate_table(t: dict, schema_name: str, db: str, seen: set) -> None:
    name = t.get("name", "")
    if not name or not t.get("rows") or not t.get("columns"):
        raise ConfigError(f"schema {schema_name} 表定义缺 name/rows/columns：{name}")
    if name in seen:
        raise ConfigError(f"表重名：{name}")
    seen.add(name)
    if t["columns"][0].get("strategy") != "seq":
        raise ConfigError(f"表 {name} 首列必须为主键 seq 策略")
    pks = [c["name"] for c in t["columns"] if c.get("strategy") == "seq"]
    if len(pks) != 1:
        raise ConfigError(f"表 {name} 必须恰好一个 seq 主键列")
    if (t.get("partition") or {}).get("days"):
        pcol = t["partition"].get("column", "")
        if pcol not in [c["name"] for c in t["columns"]]:
            raise ConfigError(f"表 {name} 分区键 {pcol} 不在列定义中")
    for c in t["columns"]:
        s = c.get("strategy") or ""
        if t.get("derived"):
            continue  # dw 派生表列由 seed 物化，不校验生成策略（strategy 仅为占位）
        if s == "seq" and c is not t["columns"][0]:
            raise ConfigError(f"表 {name} 仅主键允许 seq 策略")
        if not any(s == p or s.startswith(p if p.endswith(":") else p + ":") for p in STRATEGY_PREFIXES):
            raise ConfigError(f"表 {name}.{c.get('name')} 未知策略：{s}")


def _validate_rule(r: dict, tables: list) -> RuleSpec:
    rid = r.get("id", "")
    tname = r.get("table", "")
    kind = r.get("kind", "")
    tmap = {t.name: t for t in tables}
    if rid and kind in KNOWN_KINDS and tname in tmap:
        pass
    elif kind not in KNOWN_KINDS:
        raise ConfigError(f"规则 {rid} 未知 kind：{kind}")
    elif tname not in tmap:
        raise ConfigError(f"规则 {rid} 目标表不存在：{tname}")
    t = tmap[tname]
    col = r.get("column", "")
    colnames = t.col_names
    if kind != "duplicate_row" and col not in colnames:
        raise ConfigError(f"规则 {rid} 列不存在：{tname}.{col}")
    params = {k: v for k, v in r.items()
              if k not in ("id", "table", "column", "kind", "ratio", "anchor")}
    rule = RuleSpec(id=rid, table=tname, kind=kind, column=col,
                    ratio=float(r.get("ratio", 0.0)), anchor=int(r.get("anchor", 0)),
                    params=params)
    total = rule.expected_total(t)
    if rule.anchor < 0 or rule.anchor > total:
        raise ConfigError(f"规则 {rid} 锚定量 {rule.anchor} 超出期望总数 {total}")
    if kind == "orphan":
        parent = str(params.get("parent", "")).split(".")[0]
        if parent not in tmap:
            raise ConfigError(f"规则 {rid} 孤儿父表不存在：{parent}")
        if not params.get("anchor_from"):
            raise ConfigError(f"规则 {rid} 缺 anchor_from")
    if kind == "enum_out" and ("value" not in params or "allowed" not in params):
        raise ConfigError(f"规则 {rid} 枚举外规则需 value+allowed")
    if kind == "out_of_range" and ("values" not in params or "bounds" not in params):
        raise ConfigError(f"规则 {rid} 越界规则需 values+bounds")
    if kind == "dirty_chars" and "marker" not in params:
        raise ConfigError(f"规则 {rid} 脏字符规则需 marker")
    return rule


def _validate_totals(cfg: DatagenConfig) -> None:
    names = {t.name for t in cfg.tables}
    for r in cfg.rules:
        pass  # 引用校验已在 _validate_rule 完成
    for t in cfg.tables:
        for c in t.columns:
            if c.strategy.startswith("ref:"):
                parent = c.strategy[4:].split(".")[0]
                if parent not in names:
                    raise ConfigError(f"表 {t.name}.{c.name} 外键父表不存在：{parent}")
    # 主口径断言：业务表合计 == target_rows_total（机密表另计）
    total = sum(t.rows for t in cfg.business_tables())
    if total != cfg.target_rows_total:
        raise ConfigError(f"业务表行数合计 {total} != 目标 {cfg.target_rows_total}")


# ---------------- 生成计划（plan dry-run） ----------------

def compute_plan(cfg: DatagenConfig) -> dict:
    """不连库计算生成计划：表×行数×规则条数×分区数。"""
    today = run_today().isoformat()
    schemas = {}
    for t in cfg.tables:
        rules = []
        for r in cfg.rules_of(t.name):
            total = r.expected_total(t)
            rules.append({
                "rule": r.id, "kind": r.kind, "column": r.column,
                "expected": total, "anchor": r.anchor, "random": total - r.anchor,
            })
        entry = {"table": t.name, "rows": t.rows, "sec_level": t.sec_level,
                 "derived": t.derived, "partitions": t.partition_count, "rules": rules}
        schemas.setdefault(t.schema_name, {"db": t.db, "tables": [], "rows_total": 0})
        schemas[t.schema_name]["tables"].append(entry)
        if t.is_business:
            schemas[t.schema_name]["rows_total"] += t.rows
    business_total = sum(t.rows for t in cfg.business_tables())
    return {
        "today": today, "seed": cfg.seed, "window_days": cfg.window_days,
        "schemas": schemas, "relations": len(cfg.relations),
        "business_total": business_total, "target_rows_total": cfg.target_rows_total,
        "ok": business_total == cfg.target_rows_total,
    }
