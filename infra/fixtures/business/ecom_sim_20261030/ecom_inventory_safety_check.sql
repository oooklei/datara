-- [ECOM-SIM-20261030] Customer core flow: stock availability by warehouse.
-- Isolated fixture schema ecom_sim_20261030 is written literally: DolphinScheduler binds
-- ${...} as a JDBC value placeholder, so variables carry values only.
-- Safety threshold is the value of project variable ${project.ecom_sim_20261030_safety_stock}.
SELECT i.sku,
       i.warehouse,
       i.on_hand,
       i.reserved,
       i.available,
       i.damaged,
       CASE
         WHEN i.available <= 0 THEN 'STOCKOUT'
         WHEN i.available < ${project.ecom_sim_20261030_safety_stock} THEN 'BELOW_SAFETY'
         ELSE 'OK'
       END AS stock_state
FROM ecom_sim_20261030.inventory AS i
WHERE i.biz_date = (SELECT MAX(biz_date) FROM ecom_sim_20261030.inventory)
ORDER BY i.sku, i.warehouse;
