SELECT json_extract(r.value,'$.dimension_values[0].value') AS host,
 json_extract(r.value,'$.dimension_values[1].value') AS channel,
 CASE json_extract(r.value,'$.dimension_values[2].value') WHEN 'July' THEN '7 月' ELSE '8 月' END AS period,
 CAST(json_extract(r.value,'$.metric_values[0].value') AS INTEGER) AS sessions,
 CAST(json_extract(r.value,'$.metric_values[1].value') AS INTEGER) AS engaged,
 CAST(json_extract(r.value,'$.metric_values[2].value') AS INTEGER) AS users,
 1.0*json_extract(r.value,'$.metric_values[1].value')/json_extract(r.value,'$.metric_values[0].value') AS engagementRate
 FROM mcp_evidence, json_each(payload,'$.ga4[1].rows') r
 WHERE json_extract(r.value,'$.dimension_values[1].value') IN ('Organic Search','AI Assistant');
