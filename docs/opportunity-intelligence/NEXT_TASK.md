## Current baseline

Repo：/Users/pohsunhuang/Library/CloudStorage/GoogleDrive-james.ph.huang@shopline.com/我的雲端硬碟/SEO／GEO Reporting/99_專案程式。
WP3_BASELINE_SHA=da9f1d6aa6384eba9eb9c463605c8d1aa3875ede；WP3 branch
feat/opportunity-canonical-registry；WP2 main integration 已完成。原有 dirty
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

## Next single task

WP4：建立 evidence / candidate immutable store。只處理可重播 evidence envelope、
candidate revision、supersedes chain、idempotency、stale/failure state 與 local
run manifest；不得在 WP4 開始 scoring、production write 或改正式 actual contract。

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
