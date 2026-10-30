-- [ECOM-SIM-20261030] Customer core flow: refund must not exceed captured payment.
-- Returns offending business keys only; no personal fields.
WITH paid AS (
  SELECT order_id, SUM(pay_amount) AS paid_amount
  FROM ec_retail.ods_payment
  GROUP BY order_id
), refunded AS (
  SELECT order_id, SUM(refund_amount) AS refund_amount
  FROM ec_retail.ods_refund
  GROUP BY order_id
)
SELECT o.order_no, COALESCE(p.paid_amount, 0) AS paid_amount,
       r.refund_amount, r.refund_amount - COALESCE(p.paid_amount, 0) AS excess_amount
FROM refunded AS r
JOIN ec_retail.ods_order AS o ON o.id = r.order_id
LEFT JOIN paid AS p ON p.order_id = r.order_id
WHERE r.refund_amount > COALESCE(p.paid_amount, 0)
ORDER BY excess_amount DESC, o.order_no
LIMIT 100;
