-- Unit prices well above the 90th-percentile reference price for the same code.
SELECT
  li.line_no, li.code, li.description, li.qty, li.unit_price, li.amount,
  rp.p50_unit_price, rp.p90_unit_price, rp.source,
  li.unit_price / rp.p90_unit_price AS ratio
FROM {line_items} AS li
JOIN {reference_pricing} AS rp ON rp.code = li.code
WHERE li.case_id = @case_id
  AND li.unit_price > rp.p90_unit_price * @outlier_ratio
ORDER BY ratio DESC
