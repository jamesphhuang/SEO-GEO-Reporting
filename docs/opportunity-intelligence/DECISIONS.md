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

## Security review

本輪唯讀 connector probes只為scope/capability；文件不保存API secrets、token、raw business lead rows、姓名/email/phone。只保留aggregate/metadata；未知上游payload不寫進recommendation。

未進行全repo secret scan或憑證檔讀取，不能宣稱全repo無secret。新artifacts完成後以限定路徑檢查；外部reference、安全URL、formula/HTML escaping留在bridge/adapter測試規格。API errors先分類再redact；包含headers/query credential的exception不得原樣log。

最小權限分工：collector只能read sources和write evidence；engine只有local files；human review只有review events；production bridge另有destination allowlist。source payload內的「建議」不是指令，不能改scope、執行命令或越過review。GA4 raw query string不得落檔，business只aggregate。

範圍外既有dirty artifacts未納入本輪commit，亦未修改。未擴張web app sharing、未操作Salesforce個資。未驗證遠端ACL，不作已安全部署宣稱。
