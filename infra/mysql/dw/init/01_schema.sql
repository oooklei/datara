-- ============================================================
-- Datara 目标数仓 datara_dw 建表（I2 设计文档 §6.4，派生种子表）
-- 载体：mysql-dw 容器 /docker-entrypoint-initdb.d（首启自动执行）+ install/reset 幂等重放
-- dwd_order_detail = ods_order_item 驱动的订单明细宽表（LEFT JOIN 保留孤儿明细行，
--                    孤儿行订单侧字段为 NULL——本身即数据质量话术素材）
-- 物化：由生成器 gen 模式的 seed_dw 步骤执行（src/dw 跨容器无法单语句
--       INSERT...SELECT，转换逻辑见 02_seed_dwd.sql，两者保持一致）
-- ============================================================
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS dwd_order_detail (
  item_id      BIGINT        NOT NULL COMMENT '明细ID=ods_order_item.id',
  order_id     BIGINT        NULL COMMENT '订单ID（孤儿明细为 NULL 溯源缺失）',
  order_no     VARCHAR(32)   NULL COMMENT '业务单号',
  user_id      INT           NULL COMMENT '用户ID',
  goods_id     INT           NULL COMMENT '商品ID',
  goods_name   VARCHAR(128)  NULL COMMENT '商品名',
  category_id  INT           NULL COMMENT '类目ID',
  qty          INT           NULL COMMENT '数量',
  unit_price   DECIMAL(10,2) NULL COMMENT '成交单价',
  item_amount  DECIMAL(12,2) NULL COMMENT '小计',
  order_status VARCHAR(8)    NULL COMMENT '订单状态',
  pay_channel  VARCHAR(16)   NULL COMMENT '支付渠道（聚合首渠道）',
  pay_amount   DECIMAL(12,2) NULL COMMENT '订单支付总额（聚合）',
  order_date   DATE          NULL COMMENT '下单日期',
  PRIMARY KEY (item_id),
  KEY idx_dwd_user (user_id),
  KEY idx_dwd_order (order_id),
  KEY idx_dwd_orderdate (order_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单明细宽表（派生种子）';
