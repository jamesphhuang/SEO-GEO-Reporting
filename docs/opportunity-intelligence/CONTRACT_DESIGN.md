# CONTRACT DESIGN

本輪兩份 `contracts/*.proposal.json` 是JSON Schema draft 2020-12提案，定義record形狀，不是已核准scope instance，不是已接入production的validator。`x-proposal-status=DRAFT_NOT_APPROVED`、`x-production-activation=false`；新入口只允許preview/uat。正式批准、production env支援都需新版本與WP12 gate。

## AHREFS CONTRACT DESIGN

`contracts/ahrefs_scope.v1.proposal.json` 包含domain/subdomain/mode、country/database、language、snapshot/retrieved、metrics、estimate flag、history semantics、competitor scopes、keyword/row/unit budgets、freshness與capability refs。

初始建議兩個domain mode分取 `shopline.tw`、`blog.shopline.tw`；TW database。`language=zh-Hant` 是目標內容語言，不表示provider已篩掉所有其他語言的query。`x-proposed-defaults` 中limits=null、competitors=[]是未決設定，不能直接餵進live collector。scope instance須用有值budget及approval_ref，否則只可probe。

metrics enum是跨endpoint的欄位catalog，request必須用當次`doc`證明該endpoint的select合法。不同endpoint currency原始單位如USD cents須由adapter明確normalize並保留unit；不能把CPC當formal business value。估計的monthly volume、average volume、adaptive/static traffic不可混同；history只有provider snapshot語義，date不等於該月實際流量。

## OPPORTUNITY CONTRACT DESIGN

`contracts/opportunity_contract.v1.proposal.json` 定義65個candidate欄位：identity/period/topic/intent/funnel/theme、existing/target asset、taxonomy/action、7類source首要ref與完整evidence_refs、business evidence、6 bands、profile/score/bounds/explanations、confidence/evidence_count、status/review/validation、時間/版本/依赖/measurement plan。

`*_evidence_ref` 是該source的首要索引，可null；`evidence_refs` 是完整關聯，不能只把首要ref算進count。business額外保留ref以免formal source責任消失。多source或多period不能用raw payload塞進一個欄位；Opportunity_Evidence投影負責展開。

`*_score` 都是0..4 ordinal band，非weighted points。score_profile weights在schema的`x-score-profile-weights`和SCORING_MODEL相同；stored score integer或null。JSON Schema可驗type、enum、必填、unique array、部分state guards；**不能單獨保證score計算、引用存在、approved human identity或revision chain**。WP1補semantic validator，WP10補authenticated review。

## Semantic gates（WP1本包應覆蓋的範圍）

- 每筆candidate refs唯一，`evidence_count`等於去重後有效resolved refs；per-source refs與score explanation refs都必須在完整refs集合且source匹配。
- profile固定：CREATE_NEW→SEO_NEW、GEO_ENHANCE→GEO、其他execution→SEO_EXISTING；weight=0的band=null，active缺值→score=null，lower/upper依公式。
- profile所有weight加總100；confidence NOT_ASSESSABLE不可VALIDATED；conflict/missing不可APPROVED；非nullactiveband要有evidence。
- unknown business overlay、scope未批准、measurement plan未定、缺human event或hash mismatch：拒絕APPROVED。離線fixtures用明確mock reviewer identity，不把字串當真實驗證。
- candidate logical identity：`hash(project_scope_id, topic_cluster_id, primary_intent, primary_action, target_asset_key)`作穩定機器key；期間/revision另存。target尚無URL時用人工批准的asset proposal ID；不得每次run random ID造成重複。
- content_hash proposal：UTF-8 JSON、sort_keys、compact separators、ensure_ascii=False、reject NaN；數值integral float canonicalize為int（與snapshot digest慣例相同）。排除 `content_hash, created_at, updated_at, status, review_state, review_event_ref` 六欄，其餘欄都納入。review event綁revision+此hash；revision chain另驗，不得藉排除review欄逃避approval身份检查。
- 時間：timezone-aware ISO8601，created≤updated；scope as_of/snapshot≤retrieved本地日期，history compared<requested；reject future time travel。

URL/PII、scope overlap、source envelope完整性與funnel/intent規則由後续WP3/4/5深化；WP1只對必要unsafe URL輸入拒絕，不能聲稱已完成source系統。schema所列`x-semantic-invariants`是規範文字，不是JSON Schema會自動執行的validation keywords。

## Evidence / review / outcome contracts拆分

本輪不新增一套巨大總schema。Evidence envelope欄位/coverage/freshness在EVIDENCE_FRESHNESS_POLICY；Topic edges在OPPORTUNITY_MODEL；Review event在CONFIDENCE_MODEL；Action/outcome在OUTCOME_TRACKING。由WP3/4/10/11各自機器化，先對應proposal fixtures，不能擅自改現有actual contract。

contract promotion條件：scope owner、business owner對各自語義批准；deterministic正反fixture、schema drift拒絕、UAT readback；版本immutable。尚缺正式scope/weights批准不是理由把`proposal`字樣刪掉。

## WP1 離線 validator result

`reporting/opportunity/proposal_validation.py` 將 structural schema errors、explicit format errors、semantic evidence/score/confidence/freshness gates 與 cross-field action/review gates 分層回傳。輸入只接受 proposal payload 與本地 immutable synthetic context；不呼叫任何 source adapter，也不接受 production environment。

`ValidationError` 固定包含 `code`、`field`、`message`、`severity`，不回傳 raw payload。`ValidationResult` 提供 `is_valid`、`errors`、`warnings` 與 deterministic `as_dict()`。content hash、revision chain、source class、evidence count、profile bounds、human review revision/hash 都在 WP1 實際檢查；兩份 proposal 仍維持 `DRAFT_NOT_APPROVED` 與 `x-production-activation=false`。
## WP3 CANONICAL REGISTRY PROPOSAL

contracts/canonical_registry.v1.proposal.json 是離線 identity/mapping registry 的
proposal schema，不是正式 production contract。它要求七種 entity collection、
typed stable IDs、relations、mapping version、explicit policy gaps 與
revision manifest、synthetic=true；x-proposal-status=DRAFT_NOT_APPROVED 且
x-production-activation=false。

WP3 的 semantic validator 另外檢查 schema 無法保證的條件：entity ID duplicate /
canonical conflict、relation endpoint 與 dangling reference、provenance/review gate、
URL policy、normalized value、deterministic semantic hash 與 identity/evidence 分離。
Metrics（volume、clicks、impressions、position）不屬於 registry identity。任何
semantic mapping 預設為 CANDIDATE；只有帶 opaque reviewer ID 的人工／整理後
mapping 才可成為 APPROVED，RULE_BASED 不得自行批准。

## OPPORTUNITY STORE DESIGN（WP4）

`contracts/opportunity_store.v1.proposal.json` 是 evidence/candidate record shape
的 proposal schema，仍保留 `DRAFT_NOT_APPROVED` 與
`x-production-activation=false`。Evidence 與 Candidate 分離保存於 local JSONL
append-only logs；每一筆 revision 都有 deterministic `content_hash`，runtime
timestamp/status/review fields 不進 semantic hash。

Evidence revision 只能接續同一 logical `evidence_id` 的前一 revision，並以
`supersedes_evidence_id`、`supersedes_revision` 表示 lineage。Candidate 同理；
Candidate 的完整 `evidence_refs` 必須攜帶 `evidence_id`、revision 與 hash，store
只接受 exact match，從不替 candidate 隱式追到最新 evidence。相同 logical key、
revision、hash 是 idempotent no-op；同 revision 不同 hash、gap、tamper、dangling
WP3 entity ref 都 fail closed。

Store 只保留 source/freshness 語義（例如 Ahrefs=`THIRD_PARTY_ESTIMATE`、
`STALE`、`FAILED`、`NOT_AVAILABLE` 與 null missing），不計算 score、不建立
recommendation，也不執行 review event。run manifest 亦為 append-only local
artifact，供 offline replay 對應 source status、evidence IDs 與 candidate IDs。

## WP5 engine proposal boundary

WP5 engine 的輸入、rule trace、score、confidence 與 proposal 仍維持 offline
proposal semantics；不提升 `contracts/*.proposal.json` 為正式 production contract。
Engine 以 WP3 topic/URL identity 作 join key，將 AHREFS demand、GSC traction、SF
technical observations 分開保留 source grain；它不把 Ahrefs estimates、GSC actuals
或 crawl issue counts 互相相減，也不把 evidence row count 當成 metric。

`CONTENT_GAP` 因 OI-014 只產生 `POLICY_GAP` 結果。其他候選先經 WP1 validator，
再可 append 到 WP4 Candidate Store；proposal 的 string refs 與 store 的 pinned
`evidence_id/revision/content_hash` 分層保存，review state 固定為
`NOT_SUBMITTED`。Engine 可給 `DISCOVERED`/`CANDIDATE` 與 `MONITOR`/`DO_NOTHING`，
不提供 `APPROVED` 路徑。

## WP6 GA4 quality diagnostic proposal

`contracts/ga4_quality_diagnostics.v1.proposal.json` 是獨立的 diagnostic artifact
proposal，不是 Opportunity Type、business conversion contract 或 WP5 score extension。
它要求 `source_role=FIRST_PARTY_BEHAVIOR_DIAGNOSTIC`、candidate revision、exact
canonical URL identity、GA4/candidate evidence refs，以及每一筆 evidence 的 revision
與 content hash。`diagnostic_status` 與 `diagnostic_types` 只表達 quality / traffic /
engagement / CTA behavior；CTA event 不被命名或轉換成 Lead、SQL、Revenue、CVR。

Organic Search page-level evidence 必須和 WP3 `url_id` exact match；GA4 site-wide
rows 只能成為 contextual conflict，不能分攤到單一 page。GSC clicks、GA4 sessions
與 AI Assistant sessions 保持不同母體；外部 chatgpt.com leads/SQL 不可作為 AI
session denominator。`missing_evidence`、`STALE`、`PARTIAL`、`FAILED` 與 conflict 都
保留原語義，不以零、舊 revision 或高 engagement 自動補 confidence。

`GA4DiagnosticStore` 以 diagnostic revision / supersedes chain append，historical
revision immutable。preview 只讀 diagnostic projection，沒有 production destination、
Google Sheets、Apps Script 或 scheduler side effect。

## Production Phase 1 Recommendation canary proposal

`contracts/recommendation_canary_writer.v1.proposal.json` 與
`contracts/google_sheets_target_binding.v1.proposal.json` 描述 offline/UAT canary
boundary，兩者均為 `DRAFT_NOT_APPROVED` 且 `x-production-activation=false`。Target
binding 僅允許 runtime workbook/principal refs 與固定 `Opportunity_Recommendations`
tab；實際 credential、workbook ID、ACL 與 OAuth consent 不在 repository。

Writer 只接受 exact human Review → Recommendation Bridge lineage，保留 candidate/review/
bridge revision/hash pins，產生一筆 allowlisted WriteIntent，強制 readback 與 append-only
audit。Unknown transport result 不會自動 retry；exact readback、absent 或 conflict 分別進入
不同 reconciliation states。Score/Confidence 只是 read-only projection，writer 不改寫
Candidate、Review、Bridge、Next Steps、Recommendations 或既有 production report。
