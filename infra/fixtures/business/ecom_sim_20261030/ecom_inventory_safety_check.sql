-- [ECOM-SIM-20261030] Customer core flow: stock availability by warehouse.
-- Safety threshold corresponds to project variable ${project.inventory_safety_stock} (20).
SELECT warehouse_code, COUNT(*) AS sku_count,
       SUM(CASE WHEN qty < 20 THEN 1 ELSE 0 END) AS below_safety_stock,
       SUM(CASE WHEN qty < 0 THEN 1 ELSE 0 END) AS negative_stock
FROM ec_retail.dim_inventory
WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM ec_retail.dim_inventory)
GROUP BY warehouse_code
ORDER BY warehouse_code;
