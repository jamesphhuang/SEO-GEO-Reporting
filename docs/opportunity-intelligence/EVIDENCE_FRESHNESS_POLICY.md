# EVIDENCE_FRESHNESS_POLICY

提案 policy_version=`freshness-proposal-1`。以run的decision_at計算，不以「這次讀檔時間」刷新舊資料。

每筆 evidence envelope：`evidence_id, revision, supersedes_evidence_id, source, source_class, metric, value, unit, denominator, scope_id, grain, entity_keys, period_start/end, as_of, retrieved_at, source_updated_at, source_timezone, coverage, collection_status, freshness_state, status_reason, content_hash, source_reference, contract_version`。

collection_status指抓取；freshness_state指適用時點：FRESH / STALE / UNKNOWN。最新抓取失敗時，旧 snapshot可做historical context，但current view=STALE，保留最新failure record；不能fallback後宣稱READY。沒有snapshot則FAILED或NOT_AVAILABLE。抓到部份endpoint→PARTIAL，不能默默補缺列。

| Source | Monthly comparison | Candidate validation（提案max age） | 降級條件 |
| --- | --- | --- | --- |
| Ahrefs | scope+database+modes相同的dated snapshots，不稱calendar-month actual | as_of≤decision_at且≤30日；keyword last_update另標；必要SERP field age≤7日 | last_update缺或過舊的SERP不能替代live validation；retrieved新不代表metric新 |
| GSC | 完整final month、相同filter/query dimensions；最近28日window作shortlist | final period_end距decision_at≤7日；final cutoff另記 | daily final未齊→PARTIAL；TopN/匿名queries明確not-observed |
| GA4 | 完整月與同property/hostname/channel/timezone | 28日window end≤7日；thresholding/sampling明確 | dimension scope不符直接invalid；consent/data quality未知降低confidence |
| SF | 同crawl_config才能比較；crawl_id不可用export time取代 | crawl_completed_at≤14日；無近期改版證據才可沿用；月inventory≤35日 | 關鍵頁改動後舊crawl→STALE；indexability關鍵檢查需新證據 |
| Workduo | fixed prompt_set_version×platform×region，以matched runs對照 | 最近完整28日，period_end≤7日；retrieved≤7日 | denominator/model/prompt版本不同→CONFLICT/INSUFFICIENT，不能算MoM |
| Google SERP | 不代表月actual | observed_at≤7日；批准時再查freshness | locale/device不可知、抓取feature不全→PARTIAL；不能以未見AIO判定absence |
| CrUX | 28-day windows，盡量選不重疊對照 | window end≤14日且retrieved≤7日，記provider lag | origin fallback獨立scope；無樣本=NOT_AVAILABLE，非0或fail性能 |
| Business Actual | latest revision、approved metric scope、cohort maturity | 最近月actual read≤35日；owner overlay valid_until未過期 | 未確認source mapping不能作formal outcome；SQL maturity與retrieval freshness分開 |

這些初始SLA需owner確認；歷史CONTENT_DECAY的6個月資料不因月份老而STALE，應驗它是否為本輪要求的歷史範圍、final版本與最近重取/修訂政策。反之拿舊8月Workduo回答9月短期gap就是STALE。Freshness必須有用途 context。

## Coverage / joins

coverage：COMPLETE_WITHIN_SCOPE / TRUNCATED / SAMPLED / SUPPRESSED / UNKNOWN，加 requested_rows/returned_rows、pagination_complete、filters、sampling_threshold flags。GSC FULL coverage仍可能有匿名query，需 separate anonymous_query_limitation，不能改寫為所有搜尋詞已知。

來源country code明確映射：Ahrefs `tw`/`TW`→canonical TW；GSC `twn`→TW，保留source code。language/region/device未知不能用預設值假裝匹配。origin evidence只向origin relation掛載，不複製成每URL獨立證據。

數值finite、非負count、ratio須有單位與範圍。0、null、not observed三態分清；錯誤message先redact再分類。事件/metric revision append-only；舊修訂即使READY，也不能蓋掉最新FAILED狀態來產formal結論。

## Budget and failure handling

Collect manifest記每source的expected/received scopes、error_code、retry count、provider cost；沒有live access仍可從immutable fixtures重播。schema drift quarantine該source，不接受未知欄位默默進正式row。新來源壞掉時原報表可用，但涉及它的candidate降confidence並停止promotion。
