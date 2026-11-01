-- [ECOM-SIM-20261030] Case: reconcile isolated simulation facts against the fixture's expected metrics.
-- Schema/expected values come from the namespaced fixture variables:
--   ${project.ecom_sim_20261030_source_schema}, ${project.ecom_sim_20261030_paid_orders},
--   ${project.ecom_sim_20261030_net_paid_cents}.
-- Read-only SQL for the DBX connection; it never writes to the isolated schema.
WITH succeeded_payments AS (
  SELECT `order`, SUM(amount_cents) AS paid_cents
  FROM ${project.ecom_sim_20261030_source_schema}.payments
  WHERE status = 'succeeded'
  GROUP BY `order`
),
succeeded_refunds AS (
  SELECT SUM(amount_cents) AS refund_cents
  FROM ${project.ecom_sim_20261030_source_schema}.refunds
  WHERE status = 'succeeded'
),
observed AS (
  SELECT
    (SELECT COUNT(*) FROM succeeded_payments) AS paid_orders,
    (SELECT COALESCE(SUM(paid_cents), 0) FROM succeeded_payments)
      - (SELECT COALESCE(refund_cents, 0) FROM succeeded_refunds) AS net_paid_cents,
    (SELECT COUNT(*) FROM ${project.ecom_sim_20261030_source_schema}.quality_anomalies) AS quality_anomalies
)
SELECT
  o.paid_orders AS observed_paid_orders,
  ${project.ecom_sim_20261030_paid_orders} AS expected_paid_orders,
  o.net_paid_cents AS observed_net_paid_cents,
  ${project.ecom_sim_20261030_net_paid_cents} AS expected_net_paid_cents,
  o.quality_anomalies,
  CASE
    WHEN o.paid_orders = ${project.ecom_sim_20261030_paid_orders}
         AND o.net_paid_cents = ${project.ecom_sim_20261030_net_paid_cents}
    THEN 'MATCH'
    ELSE 'MISMATCH'
  END AS verdict
FROM observed AS o;
