# TEST_STRATEGY

unit tests只用synthetic fixtures與fake transport，不能依live MCP、Google credentials或真實business raw rows。資料與時間全部顯式傳入；相同input hash/version輸出相同。下列是**後續實作驗收計畫**，不是已通過的engine tests。

| ID | Fixture | Expected |
| --- | --- | --- |
| T01 | Ahrefs capability missing/403 | NOT_AVAILABLE；candidate insufficient、無query volume補零 |
| T02 | Ahrefs stale/last_update old | STALE；score所需dimension null、不得VALIDATED |
| T03 | GSC missing | missing evidence，不當0 impressions；需要GSC的類型不過gate |
| T04 | GSC exact bucket complete zero | 0保留；不能算CTR除0；可能有市場gap但需inventory |
| T05 | duplicate keyword across pulls | source logical key去重；不重複計demand |
| T06 | duplicate topic/merge revision | identity conflict可見、history保留、membership不double count |
| T07 | same keyword multiple URLs | 保留多URL；不能直接CONSOLIDATION |
| T08 | intent相同、多期URL互替且SF可執行 | consolidation候選；survivor/redirect需人工批准 |
| T09 | SERP intent mismatch | SERP_CONFLICT + CONFLICTING_EVIDENCE；擋CREATE_NEW/UPDATE批准 |
| T10 | Workduo stale | old snapshot context；current confidence降低，不是0 visibility |
| T11 | SF critical noindex/5xx | TECHNICAL_FIX precedence；UPDATE記dependency不先執行 |
| T12 | GA4 missing | diagnostics unknown；不是無價值；非required SEO候選不必全面消失 |
| T13 | Ahrefs/GSC scope/country conflict | 不join、不跨母體ratio；human review |
| T14 | missing business value/override expired | business_score=null、score=null、不能APPROVED |
| T15 | score fixtures | B各weights=100；0/4/null、round half up、range與missing不reweight |
| T16 | confidence fixtures | 5筆同source不等於5families；required missing高score仍LOW |
| T17 | sufficient no-action evidence | DO_NOTHING帶理由/review_at；evidence不足不假作DO_NOTHING |
| T18 | complete inventory no matching asset + >=2competitors +intent | CREATE_NEW；只有Top25缺失不能成立 |
| T19 | relevant existing URL +traction+demand+SERP+SF | UPDATE_EXISTING；不得另建重複文章 |
| T20 | fixed matched GEO sample +answer gap | GEO_ENHANCE；無citation資料不冒稱citation gap |
| T21 | score/profile choice immutable | 缺GEO不可自選SEOprofile；primary action改變需新revision |
| T22 | approved record changed evidence hash | 新revision NEEDS_REVISION、旧approval不可沿用 |
| T23 | engine submits APPROVED | 無authenticated human event拒絕；state字串無法繞過 |
| T24 | preview/uat destination=production或framework ID | write前拒絕；無network dispatch |
| T25 | retry timeout after successful append | readback reconcile、不重複row、不覆寫manual改動 |
| T26 | non-ready latest revision +old Ready | 不fallback為formal Ready；context明示stale |
| T27 | query string/HTML/formula content | reject或安全literal escaped；credentials/PII不落檔 |
| T28 | outcome +clicks但guardrail惡化 | 不WON；LOST/PARTIAL按predefined plan+review |
| T29 | CrUX origin fallback +SF URL issue | origin僅context，不能假造URL因果或每頁獨立sample |
| T30 | future timestamps/NaN/negative counts/invalid enums | contract拒絕；invalid不變0 |
| T31 | crawl config/prompt version/country drift | comparison不成立；保留reason，不任意MoM |
| T32 | SERP top_positions 1回6列 | explicit count/truncation/budget metadata；不假設row cap |

## Test layers

1. Proposal schema shape與semantic invariants（WP1）：正反synthetic records；不生production data。
2. Unit（WP2–8/11）：fake time/transport、detector、scorer、freshness、entity joins。
3. Contract compatibility：既有三份formal contracts與snapshot tests不變；new fields不塞raw payload到recommendation。
4. Render/bridge（WP9/10）：fixtures、HTML escaping、empty/partial state、375/1280px；人工tabs保護與sourceRef。
5. Integration/smoke：opt-in、明確source/environment/cost；只讀live source或isolated UAT，不成為unit必要條件。
6. Production gate（WP12）：bounded approved artifact、destination identity、readback、rollback。未授權不能執行。

## 本輪實際結果

- 第一次 `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`：系統Python 3.9，47 tests被runner計數，5 errors（4個import failures + framework setup）；不能宣稱通過。
- 用bundled Python與Node重跑：**70 tests，OK**。Node是framework generator manifest test的依賴。
- 檢查環境時bundled Python沒有jsonschema；這不是已完成schema validation。WP1必須把validator依賴/執行方式固定，不能skip後假報green。
- 本輪docs/proposals專屬檢查與最終git保存結果見VALIDATION_RESULTS.md。
- 未執行engine、UI、review bridge、outcome實作測試（尚未實作）；未驗遠端Apps Script runtime/ACL。

## WP1 實際結果

- 新增 `tests/test_opportunity_proposals.py`：**20 tests，OK**；完整既有套件加總 **90 tests，OK**。
- positive synthetic records：Ahrefs scope、DISCOVERED/CANDIDATE existing page、SEO_NEW、GEO、VALIDATED、mock human APPROVED。
- semantic negatives：invalid date/date-time、source class/estimate conflict、score/profile/bounds、duplicate/missing/count refs、stale/conflicting evidence、missing-is-not-zero、approval revision/hash、CREATE_NEW existing URL、unsafe URL、future timestamps。
- schema 2/2、shape fixtures 2/2、JSON parse 4/4、Python AST 27 files、Node syntax 5 files、`git diff --check` 與 scoped security scan 均 PASS；沒有 live API 或 production mutation。

可重現baseline指令（從repo root）：

```sh
PATH='/Users/pohsunhuang/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:'"$PATH" PYTHONDONTWRITEBYTECODE=1 '/Users/pohsunhuang/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest discover -s tests
```

## WP4 實際結果

- `tests/test_opportunity_store.py`：**22 tests，OK**；只用 WP3 synthetic registry、
  固定時間與 local temporary directory。
- 驗證 evidence rev1 → candidate pin rev1 → evidence rev2 後 candidate 仍讀 rev1；
  duplicate/collision、revision gap/supersedes、hash drift、tamper、entity
  dangling、freshness/missing、source class、date/timezone 與 non-finite 均有正反例。
- full regression：**149 tests，OK**；沒有 live API、Drive、Sheets、Apps Script
  或 production writer。

## WP5 engine test layer

`tests/test_opportunity_engine.py` 以 `tests/fixtures/opportunity_engine/scenarios.json`
覆蓋 Quick Win、high-demand insufficient、CTR hypothesis、Content Gap policy gap、
content decay、technical unlock、DO_NOTHING、conflict、stale、mapping review、
deterministic preview、unsupported source、validator fail-closed，以及 Candidate
Store evidence revision/pinning。所有 fixture 都是 synthetic；沒有 live Ahrefs、GSC、
Screaming Frog、GA4、Workduo、Google Search 或 production writer。

WP5 另執行 2 proposal schemas、JSON parse/format checker、Python AST、explicit
date/date-time、`git diff --check` 與限定路徑 secret/production-boundary scan。完整
regression 為 **166 tests，OK**；WP5 新增 **17 tests，OK**。

## WP6 GA4 diagnostic test layer

`tests/test_ga4_quality.py` 的 **15 tests** 使用 `tests/fixtures/opportunity_ga4/scenarios.json`
與 WP3 synthetic registry，覆蓋 exact URL/host/property scope、page/sitewide boundary、
healthy/declining/mixed quality、missing vs zero、STALE、wrong channel、CTA diagnostic
only、GSC-vs-GA4 conflict、AI attribution gap、WP5 score preservation、CandidateStore /
EvidenceStore pinning、diagnostic rev1→rev2 history、tamper/hash fail-closed 與 deterministic
preview。全部使用 fixed timezone-aware dates；沒有 live GA4、GSC、Ahrefs、Screaming Frog、
Workduo、Google Search、CrUX 或 production writer。

WP6 regression 為 **181 tests，OK**；另驗證 proposal schema 的 date/date-time formats、
Python AST、JSON parse、`git diff --check`、scoped secret/PII scan 與 production boundary。

## WP7 SERP validation test layer

`tests/test_serp_validation.py` 使用 `tests/fixtures/opportunity_serp/scenarios.json` 的 A–N synthetic records，覆蓋 exact canonical query/scope、owned URL 與 unmapped competitor、page-type mismatch、mixed intent、AIO/PAA `NOT_AVAILABLE`、feature crowding、stale/missing/partial evidence、row cap/truncation、bounded transient retry、provider failure、no-query shortlist gate、score/review preservation、candidate/SERP evidence pinning、rev1/rev2 history、deterministic replay 與 JSON/Markdown preview。沒有 live Google Search、Ahrefs、GSC、GA4、Screaming Frog、Workduo、CrUX、customer data 或 production writer。

WP7 targeted 為 **9 tests，OK**；加上既有套件 full regression 為 **190 tests，OK**。

## WP9 preview / UAT coverage

WP9 targeted tests use only `tests/fixtures/opportunity_preview/scenarios.json` (synthetic
A–P). They assert proposal schema, four report groups, deterministic persisted-score ordering
and a 20-row first screen, immutable evidence pins, visible missing/stale/estimate/conflict
states, independent Score/Confidence, GA4 diagnostic-only conversion boundary, SERP/GEO state
separation, UAT-only IDs, empty/partial/corrupt inputs, old preview compatibility, HTML escaping
and formula-like cell sanitization, responsive 375px markup, and no production destination writes.
The projection has no store mutation API and does not resolve a candidate to a newer revision.

## WP10 human review / recommendation bridge coverage

`tests/test_opportunity_review.py` 使用 `tests/fixtures/opportunity_review/scenarios.json`
的 A–P synthetic records。測試涵蓋 proposal schema、authenticated HUMAN actor gate、
decision taxonomy、candidate revision/hash pinning、candidate evidence 與 GA4/SERP/GEO
diagnostic pins、invalid actor/reviewer、reject/needs-more-evidence、STALE/missing/
SERP_NOT_CHECKED/policy/capability gates、SERP conflict adjudication、DO_NOTHING、review
rev1/rev2 history、superseded approval、bridge rev1/rev2 immutability、deterministic hash、
human note provenance、AI DRAFT_ONLY boundary、read-only projection、Next Steps boundary、
UAT destination allowlist、Score/Confidence preservation 與 input non-mutation。所有資料
均 offline、synthetic、timezone-aware，沒有 live source、credential、PII 或 production
writer。

WP10 targeted 為 **26 tests，OK**；合併既有 WP1–WP9 suite 後 fresh discovery 為
**260 tests，OK**。另驗證兩份 Draft 2020-12 proposal schema、fixture JSON、Python AST、
explicit date/date-time、`git diff --check`、scoped secret/PII/live-call 與 production
boundary；production mutation=0。下一個唯一工作是 WP11 — Outcome tracking，不能在 WP10
開始 outcome tracking、production rollout 或 Next Steps automation。
