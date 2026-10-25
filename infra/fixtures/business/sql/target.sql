-- INFRA-DATA-01: target table and immutable expected synchronization baseline.
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS fixture_order_detail_actual (
  fixture_key  VARCHAR(32) NOT NULL,
  item_id      BIGINT NOT NULL,
  order_id     BIGINT NOT NULL,
  order_no     VARCHAR(32) NOT NULL,
  user_id      INT NOT NULL,
  username     VARCHAR(64) NOT NULL,
  goods_id     INT NOT NULL,
  goods_name   VARCHAR(128) NOT NULL,
  qty          INT NOT NULL,
  unit_price   DECIMAL(10,2) NOT NULL,
  item_amount  DECIMAL(12,2) NOT NULL,
  order_status VARCHAR(8) NOT NULL,
  pay_channel  VARCHAR(16) NULL,
  pay_amount   DECIMAL(12,2) NULL,
  order_date   DATE NOT NULL,
  PRIMARY KEY (item_id),
  KEY idx_fixture_actual_key (fixture_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS fixture_order_detail_expected LIKE fixture_order_detail_actual;

DELETE FROM fixture_order_detail_actual WHERE fixture_key='INFRA-DATA-01';
DELETE FROM fixture_order_detail_expected WHERE fixture_key='INFRA-DATA-01';
INSERT INTO fixture_order_detail_expected
  (fixture_key,item_id,order_id,order_no,user_id,username,goods_id,goods_name,qty,unit_price,item_amount,order_status,pay_channel,pay_amount,order_date)
VALUES
  ('INFRA-DATA-01',910000000101,910000000001,'FX202610200001',910001,'fixture_alice',910001,'Fixture 机械键盘',1,199.00,199.00,'PAID','alipay',377.00,'2026-10-20'),
  ('INFRA-DATA-01',910000000102,910000000001,'FX202610200001',910001,'fixture_alice',910002,'Fixture 无线鼠标',2, 89.00,178.00,'PAID','alipay',377.00,'2026-10-20'),
  ('INFRA-DATA-01',910000000103,910000000002,'FX202610210001',910002,'fixture_bob',  910003,'Fixture 扩展坞',  2,259.00,518.00,'DONE','wechat',518.00,'2026-10-21'),
  ('INFRA-DATA-01',910000000104,910000000003,'FX202610220001',910001,'fixture_alice',910002,'Fixture 无线鼠标',1, 89.00, 89.00,'CREATED',NULL,NULL,'2026-10-22');
