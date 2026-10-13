-- Same service on the same day at the same quantity and price, entered more than once.
-- Quantities and prices are cast to integer paise because BigQuery cannot partition on FLOAT64.
SELECT line_no, service_date, code, description, category, qty, unit_price, amount, dup_key, n
FROM (
  SELECT
    line_no, service_date, code, description, category, qty, unit_price, amount,
    service_date || '|' || COALESCE(NULLIF(code, ''), LOWER(description)) AS dup_key,
    COUNT(*) OVER (
      PARTITION BY service_date, COALESCE(NULLIF(code, ''), LOWER(description)),
                   CAST(ROUND(qty * 100) AS INTEGER), CAST(ROUND(unit_price * 100) AS INTEGER)
    ) AS n
  FROM {line_items}
  WHERE case_id = @case_id
) AS t
WHERE n > 1
ORDER BY dup_key, line_no
