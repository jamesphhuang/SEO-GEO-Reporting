# VALIDATION_RESULTS

執行日2026-09-10。只報本輪實际檢查，不將測試計畫寫成已完成實作。

| Check | Result | Scope / limit |
| --- | --- | --- |
| git fetch origin | PASS | 最新main 4e30cec；clean integration branch ancestor已確認；原 dirty worktree未切換 |
| existing unittest suite，system Python 3.9 | FAIL | 47 runner-counted tests，5 errors；不支援type union + framework Node依賴未滿足 |
| existing unittest suite，bundled Python + Node | PASS | **70 tests，1.296s，OK**；fake transport單元測試，非live integration |
| Proposal Draft202012Validator.check_schema | PASS | 兩份schema符合draft 2020-12 meta-schema |
| Synthetic schema fixtures | PASS | 兩份positive shape records；不是business/source完整性驗證 |
| Negative shape fixtures | PASS | 12種變更均被拒絕，見下表 |
| Score weights | PASS | 三profile各總和100；synthetic missing-business例60–90；未實作engine scorer |
| Semantic validation gaps | CONFIRMED | 將evidence_count改999、lower_bound改99，純schema仍接受；WP1要補，不能宣称contract已強制執行 |
| Date-time checker | FIXED IN VALIDATION HARNESS | 首次負例`not-a-date`未被拒，因runtime缺format checker支援；改用datetime/date標準庫explicit callbacks後通過。正式validator仍待WP1 |
| NEXT_TASK headings | PASS | 嚴格只有指定9個heading，ONE NEXT TASK=WP1 |
| Existing dirty artifacts preservation | PASS | 本輪建檔前26個既有檔案SHA-256對照全相同；包括兩個tracked dirty files与兩個untracked目錄 |
| Bounded secret pattern scan | PASS | 僅新docs/examples/proposals；未發現Google API-key、OAuth token、GitHub token或private-key樣式；不是全repo安全稽核 |
| git diff --check | PASS | 已追蹤diff無whitespace error；新未追蹤檔另做JSON解析與文字檢查 |
| Final artifact audit | PASS | 23個新檔：19 Markdown、2 proposals、2 synthetic JSON；relative links全可解析、無trailing whitespace；4 JSON皆可解析 |
| Branch lineage audit | PASS | 7個本機branch tips皆為fetch後origin/main ancestor；未刪除或移動branch |

## Negative shape cases

Ahrefs scope：錯source_class、estimation_flag=false、environment=production、APPROVED但approval_ref=null。

Opportunity：environment=production、duplicate evidence_refs、band=5、額外raw_payload、未滿條件卻status=APPROVED、review_state=APPROVED但status不符、evidence不足卻status=VALIDATED、非法created_at。共12 cases。

schema positive/negative harness執行於`../97_Runtime/gsc-mcp/bin/python3.12`（有jsonschema）；bundled Python無該library。自訂date callback用`date.fromisoformat`與長度10；date-time callback要求`T`與timezone-aware `datetime.fromisoformat`。未安裝或修改任何runtime dependency。

## 可重現基本檢查

從repo root（下列只檢schema meta-schema與shape；完整semantic tests是WP1）：

```sh
PYTHONDONTWRITEBYTECODE=1 '../97_Runtime/gsc-mcp/bin/python3.12' - <<'PY'
import json
from pathlib import Path
from jsonschema import Draft202012Validator
for schema_name, example_name in [
    ('ahrefs_scope.v1.proposal.json', 'ahrefs_scope.synthetic.json'),
    ('opportunity_contract.v1.proposal.json', 'opportunity.synthetic.json'),
]:
    schema = json.loads((Path('contracts') / schema_name).read_text())
    example = json.loads((Path('docs/opportunity-intelligence/examples') / example_name).read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(example)
    print(schema_name, 'schema and shape OK; formats/semantics require explicit checks')
PY
```

既有70-test suite的確切命令見TEST_STRATEGY。WP1正式保留可重跑的positive/negative/semantic suite；本輪臨時harness未加入production code。

## Not verified

沒有opportunity engine、ingestion pipeline、review身份/bridge、UI、outcome implementation，所以未跑這些實作測試；沒有production activation。Ahrefs probes不是全歷史、全國別、全mode、全export上限測試；Google live AIO/PAA capture尚未驗。Workduo只小量sample，不代表Core全覆蓋。CrUX本輪未live query；Apps Script遠端runtime/ACL未重驗。

## Git result / preservation

本輪新增只在`docs/opportunity-intelligence/`、`contracts/ahrefs_scope.v1.proposal.json`、`contracts/opportunity_contract.v1.proposal.json`；`9376711` 是 architecture foundation，`692f475` 是 handoff baseline，後續僅有 handoff clarification docs commits。既有tracked兩個modified path與兩個untracked output目錄保持。沒有scheduler、正式Sheets寫入或Apps Script部署；remote architecture branch已推送，原工作樹仍由最終回報核對。

## WP1 implementation validation

| Check | Result | Scope / limit |
| --- | --- | --- |
| WP1 tests | PASS | 20 deterministic unittest cases；synthetic context only |
| Full regression | PASS | 90 tests，包含既有70 tests |
| Structural + explicit format | PASS | 兩份 proposal schemas、date、timezone-aware date-time、URL、period、identifier |
| Semantic + cross-field | PASS | evidence refs/count/families/source classes、score profiles/bounds、confidence、freshness、action、revision/content hash、mock human approval |
| Positive fixtures | PASS | Ahrefs scope、DISCOVERED/CANDIDATE、SEO_NEW、GEO、VALIDATED、mock human APPROVED |
| Negative semantic fixtures | PASS | 16 named cases；含 missing != zero、stale/conflict、approval/hash、CREATE_NEW conflict |
| Offline boundary | PASS | validator 只接受 payload/context；未呼叫 live APIs、Drive、Sheets 或 Apps Script |
| Security | PASS | synthetic fixtures；scoped secret/PII pattern scan為0 |
| Production mutation | PASS | 0；兩份 contracts仍為 proposal，沒有正式 writer 或 scheduler |
| WP1 readiness | READY | 下一個唯一任務依 ROADMAP 為 WP2 Ahrefs read-only ingestion |

## WP2 — bounded Ahrefs read-only ingestion（2026-09-10）

| Check | Result | Scope / limit |
| --- | --- | --- |
| Runtime capability discovery | PASS | Organic Keywords、Organic Competitors tools 與 `doc` schemas 可用；沒有 dedicated Content Gap tool |
| Organic Keywords live smoke | PASS | TW、domain、`limit=1`；1 row、50 observed units；未保存 raw row |
| Organic Competitors live smoke | PASS | TW、domain、`limit=1`；1 row、50 observed units；未自動批准 competitor registry |
| Content Gap | CAPABILITY_GAP | Dedicated endpoint unavailable；未用其他 endpoint 擴張 scope |
| Offline WP2 tests | PASS | 17 deterministic unittest cases；fake transport，無 live calls |
| Full regression | PASS | 107 tests（既有90 + WP2 17） |
| Budget guard | PASS | 4 requests/run、500 units/run、5 rows/endpoint、2 pages、30秒、1 retry；manifest記錄 cap |
| Normalization | PASS | Organic/competitor typed estimate evidence；optional missing 保留 null；unknown fields不進 normalized |
| Failure semantics | PASS | 403不重試；429/5xx bounded retry；schema drift、budget、stale、capability gap 可見 |
| Manifest / artifacts | PASS | run_manifest + raw/normalized 分離；raw sanitizer 移除 credential/header keys |
| Deterministic hash | PASS | normalized semantic hash 排除 retrieved_at；相同 semantic input 結果一致 |
| Source semantics | PASS | `source=AHREFS`、`source_class=THIRD_PARTY_ESTIMATE`、`estimation_flag=true` |
| Production mutation | PASS | 0；沒有 Sheets、Apps Script、Recommendations、Next Steps、scheduler writer |
| Security | PASS | fixtures 與 artifact audit 無 Authorization/Bearer/api_key/access_token/client_secret |

### WP2 not verified / limits

沒有 owner-approved live scope、competitor registry、production budget 或 Content Gap entitlement；因此未做 full discovery、全量 pagination、production write 或 Opportunity Engine。provider 的 full export upper bound、歷史 coverage、其他 country/database 與 Content Gap derivation 仍是 UNKNOWN/UNAVAILABLE。
## WP3 — canonical entity registry（2026-09-10）

| Check | Result | Scope / limit |
| --- | --- | --- |
| Entity model | PASS | TOPIC、KEYWORD、QUERY、PROMPT、URL、COMPETITOR、BUSINESS_THEME；identity 與 evidence metrics 分離 |
| Stable IDs | PASS | typed deterministic SHA-256 IDs；explicit Topic IDs 可保留；無 array position、Python hash 或 random ID |
| Text normalization | PASS | Unicode NFC、full-width ASCII/space、trim/collapse whitespace、Latin casefold；不做繁簡/同義詞自動合併 |
| URL normalization | PASS | host lowercase、default port、fragment/tracking allowlist；保留 semantic query、path case、trailing slash、www 與 scheme 差異 |
| Relations | PASS | 六種 Topic edges、URL canonical candidate、keyword alias relation；typed endpoints、version、provenance、review state |
| Provenance / review | PASS | MANUAL/CURATED/RULE_BASED/IMPORTED；CANDIDATE/APPROVED/REJECTED；RULE_BASED 不得 self-approve |
| Referential integrity | PASS | dangling refs、invalid endpoint、self relation 均 fail closed |
| Duplicate protection | PASS | duplicate ID 與 conflicting canonical value 分開回報 |
| Deterministic serialization/hash | PASS | input order 與 runtime timestamps 不改 semantic hash；UTF-8、sorted compact JSON |
| Registry schema | PASS | canonical_registry.v1.proposal.json；Draft 2020-12、proposal-only、synthetic fixture 可驗證 |
| Synthetic fixtures | PASS | 兩個 Topic、keyword/query/prompt/URL/competitor/business theme；fixture-only、無 metrics/PII |
| WP3 tests | PASS | 20 deterministic unittest cases；全 offline |
| Existing regression | PASS | 107 baseline tests；WP3 後總數 127 |
| Security | PASS | scoped credential/PII pattern scan；無 token、header、customer data |
| Production mutation | PASS | 0；無 live source、writer、Brand Dictionary、scoring、join、WP4 |
| WP3 readiness | READY | policy gaps 明確記錄，未猜測 URL/brand equivalence |

### WP3 policy gaps

HTTP/HTTPS、www/non-www、trailing slash、redirect/canonical equivalence 沒有在本包
自動合併；它們以 metadata policy gaps 留存。這不是把兩個 URL 當成相同 identity，
也不是 live redirect resolution。未來若需要合併，必須有 explicit relation、evidence
與 human review revision。

## WP4 — immutable evidence / candidate store（2026-09-10）

| Check | Result | Scope / limit |
| --- | --- | --- |
| Clean baseline | PASS | `WP4_BASELINE_SHA=28374fd2302685ce5bf060dc9292df3a679cf1e0`; original dirty worktree未觸碰 |
| Existing regression before change | PASS | 127 tests |
| Evidence store | PASS | local append-only `evidence.jsonl`，continuous revisions/history，no update/overwrite |
| Candidate store | PASS | separate `candidates.jsonl`，candidate revision append-only |
| Exact evidence pinning | PASS | `evidence_id + revision + content_hash`；rev1 candidate在evidence rev2後仍解析rev1 |
| Idempotency / collision | PASS | same logical revision+hash no-op；different hash `REVISION_CONFLICT` |
| Revision / supersedes | PASS | gap、forward/incorrect supersedes、duplicate persisted revision fail closed |
| Entity integrity | PASS | WP3 registry TOPIC/KEYWORD refs；dangling refs `UNRESOLVED_ENTITY` |
| Freshness / missing semantics | PASS | READY/PARTIAL/STALE/FAILED/NOT_AVAILABLE；null missing不轉0 |
| Source semantics | PASS | AHREFS 保留 `THIRD_PARTY_ESTIMATE`，source mismatch拒絕 |
| Date / date-time | PASS | explicit ISO date、timezone-aware timestamp與順序檢查 |
| Schema | PASS | `opportunity_store.v1.proposal.json` Draft 2020-12；proposal-only |
| Run manifest | PASS | local append-only `run_manifest.jsonl`，run collision fail closed |
| WP4 tests | PASS | 22 deterministic synthetic tests；無 live API |
| Full regression | PASS | **149 tests，OK** |
| AST / JSON / diff | PASS | 新增 Python AST、JSON parse/schema、`git diff --check` |
| Security | PASS | scoped credential/PII/production-writer scan；無 secrets、live calls或production mutation |
| Production mutation | PASS | 0；未修改 outputs、正式 contracts、Sheets、Apps Script、scheduler或UI |
| WP4 readiness | READY | 下一個唯一工作為 WP5 SEO engine v1 |

### WP4 deterministic error codes

`INVALID_RECORD_TYPE`, `INVALID_SOURCE_SEMANTICS`, `INVALID_REVISION`,
`REVISION_GAP`, `INVALID_SUPERSEDES`, `REVISION_CONFLICT`, `HASH_MISMATCH`,
`UNRESOLVED_ENTITY`, `MISSING_EVIDENCE_REFERENCE`, `MISSING_EVIDENCE_REVISION`,
`CANDIDATE_EVIDENCE_DRIFT`, `INVALID_FRESHNESS_STATE`, `INVALID_VALUE`,
`INVALID_DATE`, `INVALID_DATETIME`, `NAIVE_DATETIME`, `NONFINITE_NUMBER` 與
`STORE_CORRUPTION` 均在離線測試中有明確 fail-closed 行為。

### WP4 limits / policy gaps

本包不定義 review event、human approval identity、scoring、推薦或 outcome
business policy；Candidate 的 `status/review_state` 只作 immutable payload 保存，
真正 review bridge 留給 WP10。未提供 registry 時，帶 entity refs 的 append 會
以 `UNRESOLVED_ENTITY` 拒絕，不自動建立 entity。JSONL 是 local replay backend，
不是 live multi-writer database 或 production migration。

## WP5 — SEO Opportunity Engine v1（2026-09-10）

| Check | Result | Scope / limit |
| --- | --- | --- |
| Clean WP5 baseline | PASS | `WP5_BASELINE_SHA=202c41e88a54e0805158f41523acbb430934078b`; branch `feat/seo-opportunity-engine-v1` |
| Evaluation input | PASS | frozen normalized `OpportunityEvaluationInput`；preview/UAT only |
| Source roles | PASS | AHREFS=`THIRD_PARTY_ESTIMATE`、GSC=`FIRST_PARTY_SEARCH_ACTUAL`、SF=`TECHNICAL_CRAWL_EVIDENCE` |
| Cross-source join | PASS | registry topic/URL + explicit evidence refs；不以 source grain 相減或把 row count 當 metric |
| Rules | PASS | QUICK_WIN、CTR_OPPORTUNITY、CONTENT_DECAY、TECHNICAL_UNLOCK、DO_NOTHING；每筆保留 rule id、matched/failed/missing trace |
| Scoring | PASS | fixed SEO_EXISTING/SEO_NEW profiles；missing 不轉 zero，score 與 confidence 分離 |
| Confidence / freshness / conflict | PASS | family count、stale、mapping、conflicting evidence fail closed；不升格 VALIDATED/APPROVED |
| Existing URL behavior | PASS | registry canonical URL 決定 existing asset；UPDATE/TECHNICAL/SERP actions require explicit URL hypothesis |
| Derived Content Gap | PASS | `POLICY_GAP`；OI-014 未批准前不衍生 competitor gap、不發 candidate |
| Technical unlock | PASS | 必須有 URL-specific HIGH/CRITICAL SF issue 與 search demand intersection；issue volume alone 不足 |
| DO_NOTHING | PASS | current evidence 不滿足 rule 時保留 DO_NOTHING/MONITOR 與 review date |
| WP1 integration | PASS | 65-field proposal 經 `validate_opportunity`；invalid proposal 不進 store |
| WP4 integration | PASS | append-only Candidate Store；每個 candidate pin `evidence_id + revision + content_hash`，rev2 不漂移 rev1 |
| Synthetic fixtures | PASS | `tests/fixtures/opportunity_engine/scenarios.json`；無 live Ahrefs/GSC/SF |
| WP5 tests | PASS | **17 tests，OK** |
| Full regression | PASS | **166 tests，OK**（既有 149 + WP5 17） |
| Schema / JSON / AST / dates | PASS | 2 schemas、2 fixtures、8 Python AST；explicit date/date-time 與 format checker |
| `git diff --check` | PASS | no whitespace errors |
| Security / production boundary | PASS | scoped secret/credential/PII、live-call、production-writer scan；production mutation=0 |
| Readiness | READY | 下一個唯一工作為 WP6；本輪停止 |

### WP5 policy and dependency gaps

`AHREFS_CONTENT_GAP_UNAVAILABLE` 與 `DERIVED_COMPETITIVE_GAP_POLICY_UNAPPROVED` 維持
明示 policy gap。SERP intent 不在 WP5 source scope，因此 Quick Win 只保留為
insufficient-evidence candidate；GA4、Business Actual、SERP、Workduo、CrUX 與
production approval 仍是 dependency gaps，不以 synthetic score 或 confidence
填補。

## WP6 — GA4 quality diagnostics（2026-09-10）

| Check | Result | Scope / limit |
| --- | --- | --- |
| Clean baseline / branch | PASS | `WP6_BASELINE_SHA=cb01dc032e9c89313e6997b3d65327c7f777e9f1`; `feat/opportunity-ga4-quality-diagnostics`; original dirty worktree untouched |
| GA4 source role | PASS | `FIRST_PARTY_BEHAVIOR_DIAGNOSTIC`; offline rows only; no live GA4 or credential access |
| Scope and normalization | PASS | approved property/hostname/channel, timezone, coverage, sampling/thresholding and freshness retained |
| Exact URL join | PASS | WP3 normalized URL and exact `url_id`; unresolved URL, host mismatch and PII-like query fail closed |
| Page/sitewide boundary | PASS | page-level Organic Search only; sitewide remains contextual conflict and cannot infer page quality |
| Diagnostic contract | PASS | new `ga4_quality_diagnostics.v1.proposal.json`; Draft 2020-12, proposal-only, production activation false |
| CTA / conversion boundary | PASS | CTA diagnostic signals only; no Lead/SQL/Revenue/CVR or automatic approval |
| Attribution boundary | PASS | GSC clicks and GA4 sessions stay distinct; AI Assistant external population remains unresolved |
| Missing / stale / conflict | PASS | null/missing and STALE stay visible; no zero imputation or stale fallback |
| WP5 score protection | PASS | score and confidence remain separate; original WP5 score is preserved and never recalculated |
| Immutable evidence / diagnostics | PASS | EvidenceStore and GA4DiagnosticStore pin `evidence_id + revision + content_hash`; historical rev1 survives rev2 |
| Synthetic fixtures | PASS | A–L scenarios; no live sources or production artifacts |
| WP6 tests | PASS | **15 tests, OK** |
| Full regression | PASS | **181 tests, OK** (166 pre-WP6 + 15 WP6) |
| Structural checks | PASS | JSON schemas, explicit date/date-time format checker, Python AST and `git diff --check` |
| Security / production boundary | PASS | scoped secret/PII and production-writer scan clean; no Sheets, Apps Script, Recommendations, Next Steps or scheduler mutation |
| WP6 readiness | READY | local commit permitted; push requires a later explicit authorization |

## WP7 SERP validation

| Check | Result | Scope / limit |
| --- | --- | --- |
| Clean baseline / branch | PASS | `WP7_BASELINE_SHA=16c6c74248a0d96f8357b21d9eca45e3668d16eb`; `feat/opportunity-serp-validation`; original dirty worktree untouched |
| Collection boundary | PASS | injected transport only; shortlist/query/result cap 30; 30s timeout; one transient retry; no live provider |
| Query and scope identity | PASS | WP3 exact QUERY/KEYWORD text, locale, country, device and search scope; no invented query |
| Evidence role | PASS | `SERP` / `LIVE_SERP_SNAPSHOT`; observed timestamp, provider provenance, snapshot hash and collection state retained |
| Validation states | PASS | `SERP_VALIDATED`, `SERP_CONFLICT`, `SERP_NOT_CHECKED`; stale/failed/partial never become current success |
| Intent / page type | PASS | deterministic composition rules; mixed intent retained; mismatch produces structured conflict |
| URL / competitor protection | PASS | canonical owned URL exact match; unmapped domains remain UNKNOWN/UNMAPPED_DOMAIN; no entity creation |
| Feature semantics | PASS | AIO/PAA/featured snippets keep OBSERVED/NOT_OBSERVED/NOT_AVAILABLE; unavailable is not false |
| Candidate governance | PASS | candidate refs and SERP refs pin id/revision/hash; WP5 score/confidence and review state preserved; no auto APPROVED |
| Immutable validation history | PASS | local append-only validation store; rev1 survives rev2 and tamper/hash mismatch fails closed |
| Proposal schemas | PASS | `serp_snapshot.v1.proposal.json` and `serp_validation.v1.proposal.json`; proposal-only metadata |
| Synthetic fixtures | PASS | scenarios A–N; no customer, credential, or live source payload |
| WP7 tests | PASS | **9 tests, OK** |
| Full regression | PASS | **190 tests, OK** (181 pre-WP7 + 9 WP7) |
| Schema / AST / JSON / dates | PASS | checked-in JSON schemas, fixture parse, Python AST, explicit date/date-time checks |
| `git diff --check` | PASS | no whitespace errors |
| Security / production boundary | PASS | scoped secret/PII/live-call/production-writer scan clean; production mutation=0 |
| Readiness | READY | local commit permitted; push requires a later explicit authorization; next is WP8 only |

### WP7 policy limits

SERP validation is shortlist-only and observational. It does not claim unbiased market ranking, search volume, click-through causality, Workduo visibility, or conversion. AIO/PAA that was not captured remains `NOT_AVAILABLE`; an unmapped competitor domain is not promoted to a registry entity. Cached Ahrefs SERP context cannot satisfy the live SERP evidence role.

## WP8 GEO fixed sample layer（2026-09-10）

| Check | Result | Scope / limit |
| --- | --- | --- |
| Clean baseline / branch | PASS | `WP8_BASELINE_SHA=da1f5e53a446bbe903d49291de9c27d8eb0d44ca`; `feat/opportunity-geo-fixed-sample`; original dirty worktree untouched |
| Fixed sample registry | PASS | version/revision, prompt population, market/locale/platform/model scope, effective dates and deterministic sample hash |
| Workduo role | PASS | `MONITORED_FIXED_SAMPLE` / `MONITORED_GEO_SAMPLE`; no market share, GA4, GSC, Ahrefs or business outcome semantics |
| Exact canonical joins | PASS | WP3 PROMPT/TOPIC/URL/COMPETITOR mappings only; unknown prompt/topic/domain fail closed or remain explicit |
| Capability semantics | PASS | mention and citation independent; `NOT_AVAILABLE` != false/0; missing, stale and failed remain visible |
| Comparability | PASS | same sample version/population/platform/model/locale/market/provider methodology required; drift is `COMPARABILITY_GAP` |
| Candidate governance | PASS | existing candidate enrichment only; WP5 score/confidence/review state preserved; no auto candidate/approval |
| SERP / GA4 boundary | PASS | signals remain separate; `CROSS_CHANNEL_CONFLICT`/`MIXED_SIGNAL` retained |
| Immutable pinning | PASS | GEO evidence and diagnostics pin `evidence_id + revision + content_hash`; historical revisions remain readable |
| Synthetic fixtures | PASS | A–P; no customer, credential, live provider or production payload |
| WP8 tests | PASS | **21 tests, OK** |
| Full regression | PASS | **211 tests, OK** |
| Schema / JSON / AST / dates | PASS | three WP8 proposal schemas, fixture parse, Python AST, explicit date/date-time checks |
| `git diff --check` | PASS | no whitespace errors |
| Security / production boundary | PASS | scoped secret/PII/live-call/production-writer scan clean; production mutation=0 |
| Readiness | READY | next single task is WP9 only; no push or merge |

## WP9 Opportunity preview / UAT report（2026-09-11）

| Check | Result | Scope / limit |
| --- | --- | --- |
| Clean baseline / branch | PASS | `WP9_BASELINE_SHA=4188fe631c1f6368fe64cf964a97d518c1a5382d`; `feat/opportunity-preview-uat`; original dirty worktree untouched |
| Projection boundary | PASS | WP4–WP8 pinned records only; read-only copy; no score/confidence recompute, approval, recommendation or production writer |
| Four report groups | PASS | Quick Wins, Content Gaps, GEO Gaps, Content Decay / Technical Unlock |
| First-screen cap | PASS | deterministic persisted-score ordering; maximum 20 visible candidates; full candidate details retained |
| Evidence traceability | PASS | candidate revision and `evidence_id + revision + content_hash`; evidence dates, freshness, estimate flag and missing visible |
| Cross-channel governance | PASS | GA4 diagnostic only, SERP states retained, GEO mention/citation/comparability separate, conflicts preserved |
| UAT isolation | PASS | deterministic `UAT_PREVIEW_` and `UAT_` IDs; no production report or Recommendations / Next Steps writes |
| Render safety | PASS | canonical JSON, escaped Markdown/HTML, formula-like text sanitized, responsive 375px stylesheet |
| Proposal schema | PASS | `contracts/opportunity_preview.v1.proposal.json`; Draft 2020-12, proposal-only, production activation false |
| Synthetic fixtures | PASS | `tests/fixtures/opportunity_preview/scenarios.json`; A–P, synthetic only |
| WP9 tests | PASS | **23 tests, OK** |
| Full regression | PASS | **234 tests, OK** (211 pre-WP9 + 23 WP9) |
| Structural checks | PASS | JSON schema/fixture parse, Python AST, explicit ISO date/date-time checks, `git diff --check` |
| Security / production boundary | PASS | scoped secret/PII/live-call/production-writer scan clean; production mutation=0 |
| Readiness | READY | local commit permitted; push/PR/merge and WP10 require a later explicit authorization |

## WP10 Human review / recommendation bridge（2026-09-11）

| Check | Result | Scope / limit |
| --- | --- | --- |
| Clean baseline / branch | PASS | `WP10_BASELINE_SHA=356285f80a1a4bd4a98425a0bc561e7b65141455`; `feat/opportunity-human-review-bridge`; original dirty worktree untouched |
| Human actor gate | PASS | authenticated HUMAN actor required; SYSTEM/AI/LLM/AUTO/RULE_ENGINE identities rejected; minimal opaque actor ref only |
| Decision taxonomy | PASS | APPROVE/REJECT/NEEDS_MORE_EVIDENCE/DEFER/RETURN_FOR_REVIEW distinct from DO_NOTHING/MONITOR Candidate actions |
| Candidate revision pinning | PASS | review and bridge require exact candidate id, revision and content hash; newer revision never inherits old approval |
| Evidence / diagnostics | PASS | candidate evidence refs plus optional GA4/SERP/GEO and preview semantic hash retained; no latest fallback |
| Review immutability | PASS | local JSONL append-only review revisions; supersedes chain, idempotency, collision and tamper checks |
| Recommendation bridge | PASS | exact human APPROVE only; UAT/PREVIEW allowlist; existing Candidate Action enum; proposal-only artifact |
| Bridge immutability | PASS | append-only bridge revisions; rev1 remains readable after rev2; superseded review cannot be reused |
| Fail-closed gates | PASS | no review, invalid actor, hash/revision mismatch, missing/STALE, SERP_NOT_CHECKED, policy/capability gap and unadjudicated conflict blocked |
| Evidence semantics | PASS | Score, Confidence, GA4, SERP and GEO are preserved; conflict context is retained; approval does not mean truth or guarantee |
| AI draft boundary | PASS | DRAFT_ONLY text remains draft-only and still needs explicit human review; no AI approval path |
| DO_NOTHING / reject | PASS | DO_NOTHING can be approved as a human workflow decision; REJECT preserves Candidate history and creates no bridge |
| UAT projection | PASS | read-only review status projection; Recommendations, Next Steps and production destinations are untouched |
| Proposal schemas | PASS | `human_review.v1.proposal.json` and `recommendation_bridge.v1.proposal.json`; Draft 2020-12, proposal-only, activation false |
| Synthetic fixtures | PASS | `tests/fixtures/opportunity_review/scenarios.json`; A–P, synthetic only |
| WP10 tests | PASS | **26 tests, OK** |
| Full regression | PASS | **260 tests, OK** (234 pre-WP10 + 26 WP10) |
| Structural checks | PASS | JSON schema/fixture parse, Python AST, explicit date/date-time, `git diff --check` |
| Security / production boundary | PASS | scoped secret/PII/live-call/production-writer scans clean; production mutation=0 |
| Readiness | READY | local commit only; no push, PR, merge or WP11 |

## Current handoff — WP11 outcome tracking complete（2026-09-14）

| Check | Result | Scope / limit |
| --- | --- | --- |
| Clean baseline / branch | PASS | `WP11_BASELINE_SHA=83745d36ff59b9dfa45313c43c125f3a014f8b94`; `feat/opportunity-outcome-tracking`; original dirty worktree untouched |
| Implementation anchor | PASS | exact Candidate / human Review / UAT Bridge revision and hash; APPROVE alone never means IMPLEMENTED |
| Measurement windows | PASS | Asia/Taipei; baseline and each 30/60/90D checkpoint use 28 complete days; execution day excluded |
| Outcome taxonomy | PASS | `WON`, `PARTIAL_WIN`, `NO_CHANGE`, `LOST`, `INSUFFICIENT_DATA`; no causal claim |
| Source semantics | PASS | GSC search actual, GA4 behavior diagnostic, GEO fixed sample, SERP snapshot, SF/CrUX and Business remain separate grains |
| Missing / freshness | PASS | missing/null, FAILED, STALE and NOT_AVAILABLE never become zero/current |
| Comparability | PASS | exact scope/entity/population/methodology; GEO version and SERP observation constraints retained |
| Guardrails / mixed signal | PASS | independent support is required for WON; guardrail breach is LOST; mixed signals remain visible as PARTIAL_WIN/conflict |
| Review / bridge protection | PASS | outcome never changes Candidate revision, WP5 Score, Confidence, Review or Bridge; new revision does not inherit old approval |
| Append-only persistence | PASS | implementation and outcome JSONL stores support contiguous revisions, supersedes, idempotency and tamper rejection |
| Proposal contracts | PASS | `implementation_event.v1.proposal.json` and `outcome_tracking.v1.proposal.json`; Draft 2020-12, no production activation |
| Synthetic fixtures | PASS | A–P metadata fixture; offline-only, no live source or production rows |
| WP11 targeted | PASS | **21 tests, OK** |
| Full regression | PASS | **281 tests, OK** with bundled Python and Node runtime |
| Schema / AST / dates | PASS | proposal schema validation, fixture JSON, Python AST, explicit date/date-time and `git diff --check` |
| Security / production boundary | PASS | scoped credential/PII/live-call scan clean; production mutation=0 |
| Readiness | READY | 下一個唯一工作為 **WP12 — Production hardening（最後gate）** |

## WP12 Production hardening（2026-09-14）

| Check | Result | Scope / limit |
| --- | --- | --- |
| Clean baseline / branch | PASS | `WP12_BASELINE_SHA=6415c9e086f6afe419076461fa486d2c457f89a6`; `feat/opportunity-production-hardening`; original dirty worktree untouched |
| Activation proposal | PASS | Draft 2020-12; `DRAFT_NOT_APPROVED`; `x-production-activation=false`; activation state remains offline-only |
| Writer / target allowlist | PASS | unknown writer, target, environment and production destinations fail closed |
| Authorization boundary | PASS | Candidate APPROVE, WP11 READY and WP12 PASS never imply production activation; explicit separate authorization required |
| Idempotency | PASS | deterministic key; same key/hash is idempotent; same key/different hash is conflict |
| Partial failure | PASS | write/audit/source failure remains `PARTIAL`, `FAILED` or `BLOCKED`; never silently COMPLETE |
| Rollback / kill switch | PASS | disable-new-writes and readback; immutable history is superseded, never deleted |
| Dry-run / release manifest | PASS | planned and blocked operations plus semantic hash; actual writes = 0 |
| Observability | PASS | structured run/write/blocked/partial/completed events; no credentials, tokens or PII |
| Scheduler boundary | PASS | scheduler state `DISABLED`; no cron, trigger, Actions schedule or n8n schedule |
| Live-source boundary | PASS | no GSC, GA4, Workduo, Google Search, Ahrefs, Screaming Frog or CrUX calls |
| Synthetic fixtures | PASS | `tests/fixtures/opportunity_hardening/scenarios.json`; A–T, offline-only |
| WP12 targeted | PASS | **30 tests, OK** |
| Full regression | PASS | **311 tests, OK** (281 pre-WP12 + 30 WP12) |
| Schema / JSON / AST / dates | PASS | both proposal schemas, fixture JSON, Python AST, explicit date/date-time and `git diff --check` |
| Security / PII / production boundary | PASS | scoped secret/PII/live-call/writer scan clean; production mutation=0 |
| Readiness | READY | hardening implementation ready; production activation remains `NOT_AUTHORIZED` |
