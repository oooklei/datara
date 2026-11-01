-- [ECOM-SIM-20261030] Customer core flow: order to payment reconciliation.
-- Isolated fixture schema ecom_sim_20261030 is written literally: DolphinScheduler binds
-- ${...} as a JDBC value placeholder, so a variable can never be a schema/table qualifier.
-- Cutoff date is the value of project variable ${project.ecom_sim_20261030_biz_date}.
WITH succeeded_payments AS (
  SELECT `order`, SUM(amount_cents) AS paid_cents
  FROM ecom_sim_20261030.payments
  WHERE status = 'succeeded'
  GROUP BY `order`
), order_lines AS (
  SELECT o.id AS order_id, o.biz_date, o.qty * o.unit_cents AS expected_cents
  FROM ecom_sim_20261030.orders AS o
  WHERE o.biz_date <= '${project.ecom_sim_20261030_biz_date}'
)
SELECT l.order_id,
       l.biz_date,
       l.expected_cents,
       COALESCE(p.paid_cents, 0) AS paid_cents,
       COALESCE(p.paid_cents, 0) - l.expected_cents AS variance_cents,
       CASE
         WHEN p.paid_cents IS NULL THEN 'UNPAID'
         WHEN p.paid_cents = l.expected_cents THEN 'MATCH'
         ELSE 'MISMATCH'
       END AS verdict
FROM order_lines AS l
LEFT JOIN succeeded_payments AS p ON p.`order` = l.order_id
ORDER BY l.order_id;
