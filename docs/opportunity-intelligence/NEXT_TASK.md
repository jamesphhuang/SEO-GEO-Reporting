## Current baseline

Repo：/Users/pohsunhuang/Library/CloudStorage/GoogleDrive-james.ph.huang@shopline.com/我的雲端硬碟/SEO／GEO Reporting/99_專案程式。
WP4_BASELINE_SHA=28374fd2302685ce5bf060dc9292df3a679cf1e0；WP4 branch
feat/opportunity-immutable-store；WP3 main integration 已完成。原有 dirty
paths 仍在 CURRENT_STATE，與本包分離。

## WP3 result

WP3 已建立 offline、versioned canonical entity registry，支援 TOPIC、KEYWORD、
QUERY、PROMPT、URL、COMPETITOR、BUSINESS_THEME。Keyword、Query、Prompt 保留
不同 source grain；registry 只保存 identity、relations、provenance、review
state 與 deterministic semantic hash，不保存 volume、clicks、impressions、
position 等 evidence metrics。

URL normalization 只移除 versioned tracking allowlist，保留 semantic query、
path case、trailing slash、www/non-www 與 scheme 差異；不做 redirect、HTTP fetch
或 Screaming Frog crawl。競品不依文字相似度合併；繁簡、同義詞與 parent/child
brand 都需 explicit relation 和 review。

Registry schema 為 contracts/canonical_registry.v1.proposal.json，synthetic
fixture 為 tests/fixtures/opportunity_registry/synthetic_registry.json。Relation
預設 CANDIDATE，RULE_BASED 不得 self-approve；approved relation 必須有 opaque
reviewer ID。

WP3_CANONICAL_REGISTRY_READINESS = READY。

## WP4 result

WP4_BASELINE_SHA=`28374fd2302685ce5bf060dc9292df3a679cf1e0`。乾淨 branch
`feat/opportunity-immutable-store` 已建立 offline append-only Evidence Store、
Candidate Store 與 local run manifest。Evidence/Candidate 分開保存；revision
只能 append，candidate refs 必須固定 evidence revision 與 content hash，不會
implicit resolve latest。WP3 registry refs、source semantics、freshness、missing
vs zero、date/date-time、hash、idempotency、collision、gap、supersedes、tamper
與 deterministic replay 均有 synthetic tests。

`WP4_IMMUTABLE_STORE_READINESS = READY`；proposal schema 仍為
`contracts/opportunity_store.v1.proposal.json`，沒有正式 contract promotion。

## WP5 result

`WP5_BASELINE_SHA=202c41e88a54e0805158f41523acbb430934078b`。在
`feat/seo-opportunity-engine-v1` 完成 offline deterministic engine、preview、
synthetic fixtures、WP1 validator integration 與 WP4 Candidate Store integration。
完整 regression **166 tests，OK**（既有 149 + WP5 17）；2 schemas、AST、explicit
date/date-time、`git diff --check`、scoped security/production-boundary scan 均
PASS。沒有 live source query 或 production mutation；contracts 仍是 `*.proposal.json`。

`WP5_SEO_ENGINE_READINESS = READY`。

## Previous next single task (before WP10)

WP9 — Opportunity preview / UAT report。只記錄下一個工作；本輪不要開始 WP9。

## WP4 files allowed

- 新增 reporting/opportunity/evidence.py
- 新增 reporting/opportunity/candidate_store.py
- 新增必要的 local run manifest utilities
- 新增 tests/fixtures 與 WP4 validation docs

## WP4 files forbidden

outputs/**、既有正式 contracts、production Sheets、Apps Script、Recommendations、
Next_Steps、scheduler、live bulk ingestion、UI、Opportunity Engine、WP5 scoring、
跨來源 business attribution。

## Stop conditions

新 UNKNOWN dirty、需要 business policy、需要 live/production access、需要修改
正式 contract 或既有 production path 時停止 mutation。不得把 failure/stale/missing
靜默轉成 READY、零值或舊 revision fallback。

## Git

WP3 branch 只 stage 本包 allowlist，正常 non-force push 到
feat/opportunity-canonical-registry；不直接 push main、不 force push、不使用
git add .。本輪完成後停止，不開始 WP4。

## Latest handoff — WP6 complete（2026-09-10）

`WP6_BASELINE_SHA=cb01dc032e9c89313e6997b3d65327c7f777e9f1`。WP6 branch
`feat/opportunity-ga4-quality-diagnostics` 完成 offline GA4 quality diagnostics，
並以 WP3 exact URL join、WP4 EvidenceStore / diagnostic append-only history 與 WP5
candidate identity 作為邊界。GA4 僅是 first-party behavior diagnostic；CTA 不代表
conversion，sitewide 不推論 page quality，missing/stale/conflict 不轉零或 fallback，
Score / Confidence 與 WP5 score 均不被改寫。

WP6 regression 為 **181 tests PASS**（既有 166 + WP6 15）；schema、fixtures、AST、
explicit date/date-time、`git diff --check`、scoped security 與 production-boundary
checks PASS。`contracts/ga4_quality_diagnostics.v1.proposal.json` 維持 proposal-only。

`WP6_GA4_QUALITY_READINESS = READY`。下一個唯一任務是 **WP7 — SERP validation**；
沒有建立 WP7 branch，未開始 WP7。Push 尚未授權，沒有 push 或 merge。

## Current handoff — WP7 complete

`WP7_BASELINE_SHA=16c6c74248a0d96f8357b21d9eca45e3668d16eb`。在 `feat/opportunity-serp-validation` 完成 offline shortlist-only SERP normalizer、bounded injected collection boundary、deterministic intent/page-type validation、preview、proposal schemas、synthetic A–N fixtures 與 append-only validation history。所有 query identity、scope、feature availability、owned/competitor mapping、freshness 與 `evidence_id + revision + content_hash` pinning 都保留；SERP 不改 WP5 score/confidence，也不自動 APPROVED。

WP7 targeted **9 tests PASS**，full regression **190 tests PASS**；schema/fixture/AST/date-time、`git diff --check`、scoped security 與 production-boundary checks PASS。沒有 live provider、production mutation、PR、push 或 merge。下一個唯一任務是 **WP8 — GEO fixed sample layer**；本輪停止，不開始 WP8。

## Latest handoff — WP8 complete

`WP8_BASELINE_SHA=da1f5e53a446bbe903d49291de9c27d8eb0d44ca`。branch `feat/opportunity-geo-fixed-sample` 完成 offline GEO fixed sample layer、Workduo normalizer、diagnostics、preview、proposal schemas、synthetic A–P fixtures 與 append-only diagnostic history。21 WP8 tests、full regression 211 tests、schema/AST/JSON/date-time、`git diff --check`、security 與 production-boundary checks PASS；production mutation=0，沒有 live provider、push 或 merge。

`WP8_GEO_FIXED_SAMPLE_READINESS = READY`。依 ROADMAP 的下一個唯一工作是 **WP9 — Opportunity preview / UAT report**；本輪只記錄，不開始 WP9，也不建立 WP9 branch。

## WP9 result

`WP9_BASELINE_SHA=4188fe631c1f6368fe64cf964a97d518c1a5382d`。在
`feat/opportunity-preview-uat` 完成 offline read-only opportunity report projection、
proposal schema、A–P synthetic UAT fixture、四組首屏分組、20 筆 cap、candidate detail
traceability、JSON/Markdown/HTML deterministic renderer 與 governance checks。所有
candidate 保留 exact evidence pin；score、confidence、SERP、GA4、GEO、missing/stale/
conflict 與 policy/capability gap 不被壓成新分數或 recommendation。UAT IDs 與 source IDs
分離，沒有 production writer。

WP9 targeted **23 tests PASS**；full regression **234 tests PASS**；schema/fixture/AST/
explicit date/date-time、`git diff --check`、scoped security/PII/live-call 與 production
boundary checks PASS，production mutation=0。`WP9_OPPORTUNITY_PREVIEW_READINESS = READY`。

## Previous next single task (before WP10)

**WP10 — Human review / recommendation bridge**。只記錄下一個工作；本輪不要開始 WP10、
建立 WP10 branch、push 或 merge。

## WP10 result（2026-09-11）

`WP10_BASELINE_SHA=356285f80a1a4bd4a98425a0bc561e7b65141455`。本輪完成 offline
append-only human review records、exact Candidate/evidence revision pinning、UAT-only
recommendation bridge 與 read-only review projection。26 個 WP10 tests 與完整 **260 tests
PASS**；兩份 proposal schema 維持 Draft 2020-12、`DRAFT_NOT_APPROVED`、production
activation false。Score、Confidence、GA4、SERP、GEO、conflicts、DO_NOTHING 與
NEEDS_MORE_EVIDENCE 語義均保持獨立；Recommendations、Next Steps、Sheets、Apps Script
與 scheduler mutation=0。

`WP10_HUMAN_REVIEW_BRIDGE_READINESS = READY`。下一個唯一正式任務是 **WP11 — Outcome
tracking**。本輪未開始 WP11，也未建立 WP11 branch。

## Current state after WP11（2026-09-14）

`WP11_BASELINE_SHA=83745d36ff59b9dfa45313c43c125f3a014f8b94`；branch
`feat/opportunity-outcome-tracking`；clean worktree `/private/tmp/seo-geo-wp11-outcomes`。
WP11 targeted 21/21、fresh full regression 281/281 PASS；proposal schemas、fixtures、AST、
JSON、date/date-time、`git diff --check`、security/PII/live-call/production-boundary checks
均 PASS，production mutation=0。`WP11_OUTCOME_TRACKING_READINESS = READY`。

下一個唯一正式任務：**WP12 — Production hardening（最後gate）**。

## Current state after WP12 initial implementation — before consistency probe（2026-09-14）

`WP12_BASELINE_SHA=6415c9e086f6afe419076461fa486d2c457f89a6`；branch
`feat/opportunity-production-hardening`；clean isolated worktree。WP12 targeted **30/30**、
fresh full regression **311/311 PASS**；兩份 production hardening proposal、A–T synthetic
fixture、schema/JSON/AST/date-time、`git diff --check`、security/PII/live-call/production-
boundary checks 均 PASS，production mutation=0。

正式 readiness 是 `WP12_PRODUCTION_HARDENING_READINESS = READY`。這只代表 offline/UAT
hardening implementation ready；`PRODUCTION_ACTIVATION = NOT_AUTHORIZED`，不是 production
ready 或 production active。Activation proposal 與 release manifest 仍為
`DRAFT_NOT_APPROVED`、`x-production-activation=false`；scheduler、writer、Recommendations、
Next Steps、production workbook、Apps Script 與 live source collection 均未啟用。

ROADMAP 已完成目前列出的最後 hardening gate，沒有自動開始的 WP13。下一步若要 promotion，
必須由 owner 另行提供明確 production activation authorization；本輪不執行該 gate。

WP12 已完成 hardening implementation；本輪不執行 production promotion、scheduler、
Recommendations、Next Steps、Sheets、Apps Script 或任何 live source query。

## WP12 repair handoff（2026-09-15）

第一次 consistency probe 的 `BLOCKED_HANDOFF_INCONSISTENCY` 已保留；follow-up repair 補齊 required gates、kill switch/terminal states、revision/hash lineage、audit、cross-run idempotency、recursive redaction、manifest required fields 與 structured rollback。原始 WP12 commit 不 amend，production mutation 維持 `0`。`WP12_PRODUCTION_HARDENING_READINESS` 只有在 repair 後 targeted 與 fresh full regression 都通過時才可標示 `READY`；下一個正式工作仍不是自動啟用 production，也不建立 WP13。
Repair 後 WP12 targeted **40/40**、fresh full regression **321/321 PASS**；schema、AST、JSON、date/date-time、`git diff --check`、security/PII/live-call/production-boundary checks 均 PASS。
