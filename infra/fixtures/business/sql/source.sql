-- INFRA-DATA-01: deterministic source-side business fixture.
-- Reserved identifiers start with 910; reruns restore the same rows in place.
SET NAMES utf8mb4;

INSERT INTO dim_category (id, category_name, parent_id, level, sort_order) VALUES
  (910001, 'Fixture 办公设备', NULL, 1, 910001)
ON DUPLICATE KEY UPDATE category_name=VALUES(category_name), parent_id=VALUES(parent_id), level=VALUES(level), sort_order=VALUES(sort_order);

INSERT INTO dim_supplier (id, supplier_name, credit_code, contact_person, contact_phone, address, status) VALUES
  (910001, 'Fixture 示例供应商', '91310000FIXTURE01X', 'Fixture 联系人', '13800000000', 'Fixture 测试地址', 1)
ON DUPLICATE KEY UPDATE supplier_name=VALUES(supplier_name), credit_code=VALUES(credit_code), contact_person=VALUES(contact_person), contact_phone=VALUES(contact_phone), address=VALUES(address), status=VALUES(status);

INSERT INTO dim_user (id, username, real_name, phone, id_card, nickname, age, gender, city, user_level, register_time) VALUES
  (910001, 'fixture_alice', '示例用户甲', '13800000001', NULL, 'Alice Fixture', 31, 'F', '上海', 3, '2026-10-01 09:00:00'),
  (910002, 'fixture_bob',   '示例用户乙', '13800000002', NULL, 'Bob Fixture',   36, 'M', '杭州', 2, '2026-10-02 10:00:00')
ON DUPLICATE KEY UPDATE username=VALUES(username), real_name=VALUES(real_name), phone=VALUES(phone), id_card=VALUES(id_card), nickname=VALUES(nickname), age=VALUES(age), gender=VALUES(gender), city=VALUES(city), user_level=VALUES(user_level), register_time=VALUES(register_time);

INSERT INTO dim_goods (id, goods_name, category_id, supplier_id, price, cost_price, status, shelf_time) VALUES
  (910001, 'Fixture 机械键盘', 910001, 910001, 199.00, 120.00, 1, '2026-10-01 08:00:00'),
  (910002, 'Fixture 无线鼠标', 910001, 910001,  89.00,  45.00, 1, '2026-10-01 08:00:00'),
  (910003, 'Fixture 扩展坞',   910001, 910001, 259.00, 170.00, 1, '2026-10-01 08:00:00')
ON DUPLICATE KEY UPDATE goods_name=VALUES(goods_name), category_id=VALUES(category_id), supplier_id=VALUES(supplier_id), price=VALUES(price), cost_price=VALUES(cost_price), status=VALUES(status), shelf_time=VALUES(shelf_time);

INSERT INTO ods_order (id, order_no, user_id, status, amount, receiver_name, receiver_phone, remark, create_time, order_date) VALUES
  (910000000001, 'FX202610200001', 910001, 'PAID',    377.00, '示例用户甲', '13800000001', 'fixture-paid',    '2026-10-20 10:00:00', '2026-10-20'),
  (910000000002, 'FX202610210001', 910002, 'DONE',    518.00, '示例用户乙', '13800000002', 'fixture-done',    '2026-10-21 11:00:00', '2026-10-21'),
  (910000000003, 'FX202610220001', 910001, 'CREATED',  89.00, '示例用户甲', '13800000001', 'fixture-created', '2026-10-22 12:00:00', '2026-10-22')
ON DUPLICATE KEY UPDATE order_no=VALUES(order_no), user_id=VALUES(user_id), status=VALUES(status), amount=VALUES(amount), receiver_name=VALUES(receiver_name), receiver_phone=VALUES(receiver_phone), remark=VALUES(remark), create_time=VALUES(create_time);

INSERT INTO ods_order_item (id, order_id, goods_id, qty, unit_price, item_amount, order_date) VALUES
  (910000000101, 910000000001, 910001, 1, 199.00, 199.00, '2026-10-20'),
  (910000000102, 910000000001, 910002, 2,  89.00, 178.00, '2026-10-20'),
  (910000000103, 910000000002, 910003, 2, 259.00, 518.00, '2026-10-21'),
  (910000000104, 910000000003, 910002, 1,  89.00,  89.00, '2026-10-22')
ON DUPLICATE KEY UPDATE order_id=VALUES(order_id), goods_id=VALUES(goods_id), qty=VALUES(qty), unit_price=VALUES(unit_price), item_amount=VALUES(item_amount);

INSERT INTO ods_payment (id, order_id, pay_channel, pay_amount, pay_time, pay_date) VALUES
  (910000000201, 910000000001, 'alipay', 377.00, '2026-10-20 10:05:00', '2026-10-20'),
  (910000000202, 910000000002, 'wechat', 518.00, '2026-10-21 11:08:00', '2026-10-21')
ON DUPLICATE KEY UPDATE order_id=VALUES(order_id), pay_channel=VALUES(pay_channel), pay_amount=VALUES(pay_amount), pay_time=VALUES(pay_time);

CREATE OR REPLACE VIEW fixture_order_detail_source AS
SELECT
  'INFRA-DATA-01' AS fixture_key,
  i.id AS item_id,
  o.id AS order_id,
  o.order_no,
  o.user_id,
  u.username,
  i.goods_id,
  g.goods_name,
  i.qty,
  i.unit_price,
  i.item_amount,
  o.status AS order_status,
  p.pay_channel,
  p.pay_amount,
  o.order_date
FROM ods_order_item i
JOIN ods_order o ON o.id=i.order_id AND o.order_date=i.order_date
JOIN dim_user u ON u.id=o.user_id
JOIN dim_goods g ON g.id=i.goods_id
LEFT JOIN (
  SELECT order_id, MIN(pay_channel) AS pay_channel, SUM(pay_amount) AS pay_amount
  FROM ods_payment
  WHERE id BETWEEN 910000000201 AND 910000000299
  GROUP BY order_id
) p ON p.order_id=o.id
WHERE i.id BETWEEN 910000000101 AND 910000000199;
