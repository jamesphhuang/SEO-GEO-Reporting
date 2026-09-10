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

## Next single task

WP5：SEO engine v1（Ahrefs + GSC + SF）。只可從 WP4 immutable validated evidence
產生 deterministic SEO candidates 與可解釋 scoring；不得在下一輪加入 GA4、SERP、
Workduo、UI、production activation 或把 evidence store 改成 mutable。

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
