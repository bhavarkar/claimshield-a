-- Lines where quantity x rate does not equal the amount charged.
SELECT line_no, code, description, qty, unit_price, amount, qty * unit_price AS expected_amount
FROM {line_items}
WHERE case_id = @case_id
  AND ABS(qty * unit_price - amount) > 0.5
ORDER BY line_no
