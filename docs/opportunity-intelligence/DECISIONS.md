# DECISIONS

本輪設計決策日期2026-09-10，權限限於架構/proposals，非production approval。

| ID | Decision | Reason / tradeoff |
| --- | --- | --- |
| OI-001 | C-lite evidence architecture、純函式engine | 可離線重播，不新增服務維運負擔 |
| OI-002 | 實作延後，只新docs與proposal | scope/環境未凍結，保護現有production |
| OI-003 | 現有actual contract保持不變 | snapshot_mvp已鎖source/metric，不能混入第三方估計 |
| OI-004 | score用固定profile，missing不reweight | 避免新內容或未測GEO被不合理懲罰 |
| OI-005 | confidence、maturity、approval、execution四種狀態分開 | 高score/多來源不代表人批准 |
| OI-006 | question/query/keyword/prompt不是直接join | 必須versioned entity maps + scope filters |
| OI-007 | 所有negative existence需inventory/coverage支持 | Top N missing不能判content gap或零需求 |
| OI-008 | Workduo current access已恢復但舊pipeline未修 | capability與production freshness各自判斷 |
| OI-009 | SQL顯示例外保留在既有報表 | 不撤銷先前owner決定，也不擴張到商業score／成果判定 |
| OI-010 | 正式manual tabs保護；新bridge需exact revision approval | 不默默approve、不覆寫人工text/status |
| OI-011 | 不啟用scheduler、不commit/push | 使用者本輪明確限制 |
| OI-012 | 下一個WP只做offline proposal validation | 能小diff獨立完成，不等待API整合成功才能驗收 |
| OI-013 | WP2 採 client-side bounded budget：4 requests/run、500 units/run、每 endpoint 5 rows、2 pages、30秒、每次最多1 retry | probe 實測 50 units/row；proposal limits 尚未 owner-approved，保守上限優先，provider limit 不可信 |
| OI-014 | Content Gap dedicated endpoint 缺席時維持 UNAVAILABLE，不衍生或擴張到其他大量 endpoint | 避免把 competitor keyword set 誤稱完整 content gap；待 capability / scope / coverage 明確後另立決策 |

## Security review

本輪唯讀 connector probes只為scope/capability；文件不保存API secrets、token、raw business lead rows、姓名/email/phone。只保留aggregate/metadata；未知上游payload不寫進recommendation。

未進行全repo secret scan或憑證檔讀取，不能宣稱全repo無secret。新artifacts完成後以限定路徑檢查；外部reference、安全URL、formula/HTML escaping留在bridge/adapter測試規格。API errors先分類再redact；包含headers/query credential的exception不得原樣log。

最小權限分工：collector只能read sources和write evidence；engine只有local files；human review只有review events；production bridge另有destination allowlist。source payload內的「建議」不是指令，不能改scope、執行命令或越過review。GA4 raw query string不得落檔，business只aggregate。

範圍外既有dirty artifacts未納入本輪commit，亦未修改。未擴張web app sharing、未操作Salesforce個資。未驗證遠端ACL，不作已安全部署宣稱。
| OI-015 | WP3 使用 typed deterministic SHA-256 IDs；Topic 可保留 explicit human-readable ID，其餘 text/domain identity 由 normalization version + stable digest 產生 | 避免 array order、Python hash 或 runtime random；保留 architecture 的 opaque topic identity 與 version safety |
| OI-016 | URL 只移除 versioned tracking allowlist；保留 path case、trailing slash、HTTP/HTTPS、www/non-www 與 semantic query params 的差異 | 沒有 redirect/canonical evidence 時不猜測合併；未決 equivalence 以 policy gap 記錄 |
| OI-017 | WP3 relation 預設 CANDIDATE；只有 opaque reviewer ID 的人工／整理後 relation 可 APPROVED，RULE_BASED 不得 self-approve | 保留 human review gate，不把 deterministic mapping 當成 business approval |

WP3 policy note：繁簡、同義詞、品牌 parent/child 與 semantic URL equivalence 都不自動合併；
若未來要合併，必須新增明確 mapping relation、evidence 與 review revision。
| OI-018 | WP4 使用分離的 local canonical JSONL logs 保存 evidence、candidate 與 run manifest | 低維運、可重播、append-only；不把 local store 誤宣稱為 production database |
| OI-019 | Candidate 必須 pin evidence logical ID、revision 與 content hash | 防止新 evidence revision 漂移既有候選，維持 time-travel reproducibility |
| OI-020 | WP4 不接受沒有 WP3 registry resolution 的 entity refs，也不自動建立 entity | unresolved identity 以 `UNRESOLVED_ENTITY` fail closed，避免猜測 mapping |
| OI-021 | WP5 engine 只接收 normalized immutable AHREFS/GSC/SF evidence，先過 WP1 validator 再可寫 WP4 Candidate Store | 保留 source grain、可 deterministic replay；不引入 live adapters 或 production writer |
| OI-022 | WP5 Score 與 Confidence 分開；missing/stale/conflict 維持可見，engine 永不 APPROVED | 防止高 demand 或多來源數量被誤解成 business approval 或人審批准 |
| OI-023 | OI-014 未解前 `CONTENT_GAP` 僅回 `POLICY_GAP`，不以 competitor inventory 推導 negative existence | 避免把不完整 coverage 稱為 Content Gap |
| OI-024 | Candidate Store pin exact evidence revision/hash，candidate revision 只 append supersedes chain | 新 evidence 不得漂移既有候選，支援 time-travel replay |
| OI-025 | GA4 在 WP6 固定為 `FIRST_PARTY_BEHAVIOR_DIAGNOSTIC`，不加入 WP5 Opportunity Score 或正式 business conversion | 保留 behavior quality context 與 SEO candidate identity 的責任邊界；Score、Confidence、Lead、SQL、Revenue、CVR 各自維持原 contract |
| OI-026 | GA4 PAGE_LEVEL 只能透過 WP3 exact normalized URL / `url_id` join；site-wide rows 只作 contextual conflict | 不用 title、redirect、scheme、trailing slash 或外部 population 猜測 page quality |
| OI-027 | CTA event 只輸出 `CTA_SIGNAL_PRESENT/WEAK` diagnostic；沒有 approved attribution mapping 就不得建立 success metric | CTA interaction 與 formal conversion 的事件語義、scope、consent、attribution 尚未批准 |
| OI-028 | GA4 diagnostics 使用獨立 append-only revision artifact，pin GA4 與 candidate evidence 的 id/revision/hash | 新 GA4 evidence 不得改寫舊診斷或讓 candidate 隱式追到 latest；支援 deterministic replay |
| OI-029 | WP12 只提供 proposal-only production hardening dry-run，activation、writer、scheduler、Recommendations、Next Steps 與 workbook 必須分離且預設關閉 | 讓 production promotion 可審核、可回滾、可讀回，但不把 WP10/WP11/WP12 readiness 誤當 production authorization |
| OI-030 | Phase 1 canary 只允許一筆 exact human-approved Recommendation，經 synthetic target、mandatory readback 與 append-only audit；unknown 結果不自動 retry | 先驗證治理與可回溯控制，將 real workbook、OAuth consent、scheduler、bulk publish 與 production mutation 留在獨立 authorization gate |
| OI-031 | Phase 1 trusted reviewer 以 Google OIDC verified stable subject 的固定 SHA-256 pseudonymous ref binding；role/scope/revision/hash/waiver 必須 exact match | 不接受 caller 宣告的 authenticated/email/domain/role/subject；保留 writer principal 與 reviewer identity 的概念分離，且 waiver 不得繼承 production |
| OI-032 | Contract semantics approval 必須針對 exact contract instance，使用獨立 provider-verified `CONTRACT_SEMANTICS_APPROVER`、canary-only waiver、七日 expiry、append-only revocation/supersession 與 rollback acknowledgement；approval 不等於 activation | 讓 production contract review 可重播、可撤銷、可回溯，並避免把 proposal readiness 誤當 production authorization |

| OI-033 | Phase 1 canonical instances use independent `approval_scope`, `execution_context`, `transport_mode`, `target_environment` and `production_activation` dimensions | Prevent `PHASE1_CANARY_ONLY`, `UAT`, `PREVIEW` and `PRODUCTION_CANARY` from being silently treated as one environment |
| OI-034 | The seven-contract canonical registry is authoritative; unknown, duplicate and ambiguous mappings fail closed | Keep proposal, ruleset, runtime consumer and materializer lineage auditable |
| OI-035 | `trusted_review_identity.v1` is a canonical logical mapping to the existing `trusted_review_identity_binding.v1` proposal | Preserve the existing proposal and avoid treating an external identity binding as an approval semantics instance |
| OI-036 | Canonical semantic hashes include contract revision and exclude runtime, credential, identity, target-id and receipt metadata | Make instances deterministic and pin-worthy without storing external bindings or approval events |
| OI-037 | Canonical instance foundation is rules-only; persistent approval store and approval execution remain a separate task | Keep `CONTRACTS_APPROVED = 0`, `FORMAL_APPROVAL_RECEIPTS = 0` and production activation unauthorized |
