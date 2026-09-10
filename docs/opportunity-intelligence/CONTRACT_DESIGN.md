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
