-- [ECOM-SIM-20261030] Customer core flow: refund must not exceed captured payment.
-- Isolated fixture schema ecom_sim_20261030 is written literally; ${...} variables would be
-- bound as JDBC values by DolphinScheduler and cannot qualify a table. Returns offending
-- business keys only; no personal fields.
WITH succeeded_payments AS (
  SELECT `order`, SUM(amount_cents) AS paid_cents
  FROM ecom_sim_20261030.payments
  WHERE status = 'succeeded'
  GROUP BY `order`
), succeeded_refunds AS (
  SELECT `order`, SUM(amount_cents) AS refund_cents
  FROM ecom_sim_20261030.refunds
  WHERE status = 'succeeded'
  GROUP BY `order`
)
SELECT r.`order` AS order_id,
       COALESCE(p.paid_cents, 0) AS paid_cents,
       r.refund_cents,
       r.refund_cents - COALESCE(p.paid_cents, 0) AS excess_cents
FROM succeeded_refunds AS r
LEFT JOIN succeeded_payments AS p ON p.`order` = r.`order`
WHERE r.refund_cents > COALESCE(p.paid_cents, 0)
ORDER BY excess_cents DESC, order_id
LIMIT 100;
