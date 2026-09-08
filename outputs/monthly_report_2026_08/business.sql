WITH cells AS (
 SELECT json_extract(payload, '$.business.sheets[0].data[0].rowData[8].values[6].userEnteredValue.numberValue') AS actual,
 json_extract(payload, '$.business.sheets[0].data[0].rowData[8].values[5].userEnteredValue.numberValue') AS target,
 json_extract(payload, '$.business.sheets[0].data[0].rowData[8].values[2].userEnteredValue.numberValue') AS prior
 FROM mcp_evidence)
 SELECT actual, target, 1.0*actual/target AS attainment, 1.0*actual/prior-1 AS mom, target-actual AS gap FROM cells;
