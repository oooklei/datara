-- ============================================================
-- dwd_order_detail 派生种子转换参考（I2 设计文档 §6.4）
-- 用途：转换逻辑的声明式参考物；执行体是生成器 gen 模式的 seed_dw 步骤
--       （tools/datagen/gen.py），因为 src/dw 分属两个容器实例，MySQL 无法
--       单语句跨实例 INSERT...SELECT，由生成器以 pymysql 双连接搬运。
--       若 src/dw 同实例部署（schema 合并场景），本文件可直接执行：
--         mysql -h <dw主机> datara_dw < 02_seed_dwd.sql
-- 注意：gen 重灌前会 TRUNCATE dwd_order_detail（幂等重跑语义）。
-- ============================================================

INSERT INTO dwd_order_detail
  (item_id, order_id, order_no, user_id, goods_id, goods_name, category_id,
   qty, unit_price, item_amount, order_status, pay_channel, pay_amount, order_date)
SELECT
  i.id                                   AS item_id,
  o.id                                   AS order_id,
  o.order_no                             AS order_no,
  o.user_id                              AS user_id,
  i.goods_id                             AS goods_id,
  g.goods_name                           AS goods_name,
  g.category_id                          AS category_id,
  i.qty                                  AS qty,
  i.unit_price                           AS unit_price,
  i.item_amount                          AS item_amount,
  o.status                               AS order_status,
  p.pay_channel                          AS pay_channel,
  p.pay_amount                           AS pay_amount,
  o.order_date                           AS order_date
FROM ec_retail.ods_order_item i
LEFT JOIN ec_retail.ods_order o        ON i.order_id = o.id
LEFT JOIN ec_retail.dim_goods g        ON i.goods_id = g.id
LEFT JOIN (
  SELECT order_id, MIN(pay_channel) AS pay_channel, SUM(pay_amount) AS pay_amount
  FROM ec_retail.ods_payment GROUP BY order_id
) p ON p.order_id = o.id;
