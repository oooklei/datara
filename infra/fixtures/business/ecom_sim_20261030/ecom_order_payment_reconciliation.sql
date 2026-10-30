-- [ECOM-SIM-20261030] Customer core flow: order to payment reconciliation.
-- Snapshot date corresponds to project variable ${project.biz_date} (2026-10-14).
-- Read-only SQL for the ec_retail DBX connection.
WITH paid AS (
  SELECT order_id, SUM(pay_amount) AS paid_amount
  FROM ec_retail.ods_payment
  GROUP BY order_id
)
SELECT o.order_date,
       COUNT(*) AS order_count,
       SUM(o.amount) AS order_amount,
       SUM(COALESCE(p.paid_amount, 0)) AS paid_amount,
       SUM(CASE WHEN p.paid_amount IS NULL THEN 1 ELSE 0 END) AS orders_without_payment
FROM ec_retail.ods_order AS o
LEFT JOIN paid AS p ON p.order_id = o.id
WHERE o.order_date = '2026-10-14'
GROUP BY o.order_date;
