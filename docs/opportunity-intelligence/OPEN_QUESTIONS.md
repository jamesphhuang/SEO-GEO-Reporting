# OPEN_QUESTIONS

未決事項在相關WP gate解決；不因這些問題阻塞offline設計與測試。

| ID | 問題 / 決策者 | 提案與影響 | Blocking WP |
| --- | --- | --- | --- |
| Q01 | SEO owner批准的Ahrefs domain/prefix、TW database、兩站是否分取？ | 初始shopline.tw domain、blog.shopline.tw domain；排除support/SSO/其他subdomains；正式approval尚無 | WP2 live ingestion |
| Q02 | 競品清單、brand vs country scopes誰批准？ | Workduo registry只當候選；WACA aliases、Shopify/TW parent-child需review | WP2 full competitor / WP8 |
| Q03 | Ahrefs每月units與最大keyword/export budget？ | 先offline；probe成功不等於full quota任意使用；source limit與local hard cap分開 | WP2 full discovery |
| Q04 | 誰維護business relevance與本月人日分配？ | B profiles是提案；缺批准score=null；需SEO/business owner valid_until | WP5 execution ranking |
| Q05 | Google live SERP provider、地域裝置與AIO/PAA完整性？ | 無已驗adapter；人工browser可能驗shortlist但需capture contract與合法可用access | WP7 |
| Q06 | Workduo 41題Core版本與實際query IDs / platform/run分母如何對齊？ | Framework摘要不等於完整ID mapping；禁止改樣本後算MoM | WP8 |
| Q07 | 誰可approve、身份系統、review event保存方式？ | opaque reviewer id + exact hash；不能engine自簽；必要時人工匯入review manifest | WP10 |
| Q08 | UAT workbook ID及Apps Script綁定在哪？ | 必須與月報/framework不同；本輪不建立，production hard-disabled | WP9 remote UAT / WP12 |
| Q09 | Business topic/URL attribution與SQL來源何時正式批准？ | 未批准可繼續SEO/GEO測量，不能formal revenue/SQL ranking | Business outcome claims |
| Q10 | production部署目前版本與ACL？ | Git紀錄說v2 live、v1 archived，本輪未remote readback | WP12 |
| Q11 | SF歷史crawl的config是否可比？ | DB有08-17 blog等歷史，需config audit；單月counts不當trend | WP5 decay增强 |
| Q12 | 品牌字典62 Approved與GA4 landing session scope如何機讀？ | 完整registry/contract需version hash與smoke；Framework timezone與contract不同需明確adapter | WP3 / WP6 |

不採用的shortcut：Ahrefs endpoint沒測就宣稱可用；missing keyword=0；CTA=formal成功；高CPC=高商業價值；高score自動寫Recommendations；舊production workbook中的測試期別當UAT。
