SELECT site.key AS sourceKey,
 CASE WHEN json_extract(site.value,'$.site_url') LIKE 'https:%' THEN '主站' ELSE '部落格' END AS siteLabel,
 substr(json_extract(site.value,'$.date_range.start'),6,2)||' 月' AS period,
 SUM(json_extract(day.value,'$.clicks')) AS clicks,
 SUM(json_extract(day.value,'$.impressions')) AS impressions,
 1.0*SUM(json_extract(day.value,'$.clicks'))/SUM(json_extract(day.value,'$.impressions')) AS ctr,
 SUM(json_extract(day.value,'$.position')*json_extract(day.value,'$.impressions'))/SUM(json_extract(day.value,'$.impressions')) AS position
 FROM mcp_evidence, json_each(payload,'$.gsc') site, json_each(site.value,'$.rows') day GROUP BY site.key;
