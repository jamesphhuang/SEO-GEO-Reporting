# CONFIDENCE_MODEL

Confidence 依「該 opportunity type 的必要證據是否可採用」判斷，不能用 source_count≥3 取代。8個 Ahrefs API calls 仍只有同一第三方 evidence family；GSC official 與 Ahrefs GSC mirror 也不是獨立驗證。

## 狀態分工

| Field | Allowed values / authority |
| --- | --- |
| status（evidence maturity） | DISCOVERED / CANDIDATE / VALIDATED / APPROVED |
| validation_state | INSUFFICIENT_EVIDENCE / CONFLICTING_EVIDENCE / PASS |
| confidence | LOW / MEDIUM / HIGH / NOT_ASSESSABLE |
| review_state | NOT_SUBMITTED / PENDING / APPROVED / REJECTED / NEEDS_REVISION |
| action_status | NOT_STARTED / IN_PROGRESS / COMPLETED / CANCELLED；橋接後 Recommendations 的進度為權威 |
| source collection status | READY / PARTIAL / STALE / FAILED / NOT_AVAILABLE；與以上無互換關係 |

DISCOVERED：至少一筆有效scope evidence產假說，可能只有Ahrefs。CANDIDATE：primary topic/asset mapping可用、至少兩個獨立responsibility families支持同假說，business relevance候選已標記；不要求每個類型硬有GSC正值。VALIDATED：type必需evidence全部符合freshness/scope/coverage、無unresolved conflict/disqualifier、SERP必要時PASS、可執行action定義完整。APPROVED：VALIDATED且人工批准精確revision/hash；不是比HIGH更高的Confidence。

## Deterministic confidence rules（依序）

1. ID解析失敗、scope未明、數值格式錯、無有效證據 → NOT_ASSESSABLE / INSUFFICIENT_EVIDENCE。
2. 有未解conflict → LOW / CONFLICTING_EVIDENCE，最高CANDIDATE。
3. 任一required evidence缺失/STALE/PARTIAL（不足以證明所需條件） → LOW / INSUFFICIENT_EVIDENCE，最高CANDIDATE。
4. required全部滿足、至少兩個獨立families且無衝突 → MEDIUM / PASS / VALIDATED。optional evidence缺失不是自動零分。
5. 在4基礎上，全部支持性證據無過期、entity mappings已人工確認、scope充分、且有第二個可比觀測窗口或獨立evidence family排除關鍵替代解釋 → HIGH。required evidence中的SF技術檢查不能被當成排除季節性的獨立驗證。

`evidence_count` = 去重後、candidate實際引用且語義有效的evidence_id數。`independent_family_count` 另列；不把row count、API call count混用。Evidence完整不表示business價值已批准；若business dimension欠批准，score=null，approval不可通過。

## Review / promotion invariants

- Human event：`review_event_id, reviewer_id, reviewed_at, decision, candidate_revision, candidate_hash, rationale, approved_action, approved_target, measurement_plan_id`；reviewer不得是engine identity，身份驗證由review surface承擔，字串有值不算通過。
- APPROVED要求review_state=APPROVED、validation_state=PASS、score非null、confidence至少MEDIUM、required refs新鮮、scope已批准。DO_NOTHING/MONITOR不承諾執行成本，但若要進管理承諾仍需人工批准。
- 改target/action/score evidence/mapping/required snapshot即新revision；舊event仍保留，但新revision回NEEDS_REVISION。approved immutable revision不得in-place update。
- reviewer判斷與engine不一致，存override rationale及版本；critical source/canonical/intent conflicts只能透過新證據或explicit adjudication record解決，不能按一個approve鍵跳過。
- engine不能自行寫Recommendations或Next_Steps。review系統日後要有approved manifest與idempotent bridge，詳見WORKBOOK_ARCHITECTURE。
