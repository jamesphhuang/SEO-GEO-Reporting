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

## Next single task

WP6 — GA4 quality diagnostics。只可另行以明確授權開始；本輪不要開始 WP6。

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
