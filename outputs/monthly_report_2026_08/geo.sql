SELECT json_extract(day.value,'$.dimensionValue') AS entity, month.key||' 月' AS period,
 COUNT(DISTINCT json_extract(day.value,'$.date')) AS days,
 AVG(json_extract(day.value,'$.visibility')) AS visibility, AVG(json_extract(day.value,'$.sov')) AS sov
 FROM mcp_evidence, json_each(payload,'$.geo') month, json_each(month.value,'$.data') day
 GROUP BY month.key, entity;
