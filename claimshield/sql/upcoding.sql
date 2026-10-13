-- A service billed at a higher complexity tier than is typical for the bill's procedure.
SELECT
  li.line_no, li.code, li.description, li.qty, li.unit_price, li.amount,
  rp.family, rp.tier, pb.max_expected_tier, pb.expected_code, pb.rationale,
  ex.description AS expected_description, ex.p90_unit_price AS expected_p90
FROM {line_items} AS li
JOIN {reference_pricing} AS rp ON rp.code = li.code
JOIN {procedure_benchmarks} AS pb
  ON pb.family = rp.family
 AND LOWER(@procedure) LIKE '%' || pb.procedure_key || '%'
JOIN {reference_pricing} AS ex ON ex.code = pb.expected_code
WHERE li.case_id = @case_id
  AND rp.tier > pb.max_expected_tier
ORDER BY li.line_no
