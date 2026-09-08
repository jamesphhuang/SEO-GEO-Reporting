SELECT site.key AS site, json_extract(page.value,'$.page') AS page,
 json_extract(page.value,'$.clicks') AS clicks, json_extract(page.value,'$.impressions') AS impressions,
 1.0*json_extract(page.value,'$.clicks')/json_extract(page.value,'$.impressions') AS ctr
 FROM mcp_pages, json_each(payload) site, json_each(site.value,'$.rows') page;
