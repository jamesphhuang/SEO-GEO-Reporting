# WORK PACKAGES / ROADMAP

接手模型：GPT-5.6 Luna，極高 reasoning。一次只做一個WP，每包獨立diff與驗收；不需要下一包才能證明本包成功。沒有明確授權不commit/push；取得授權後只stage本包檔案，可獨立commit。以下資料夾是future allowlist，不代表已存在。

## WP0 — Ground truth / capability（本輪完成設計盤點）

- 唯一目標：用repo、Drive、live probes固定可稽核baseline。
- Input：HEAD、contracts、report callers、live tool metadata。
- Output：CURRENT_STATE、CAPABILITY_MATRIX、DECISIONS及本輪proposals/handoff。
- Acceptance：區分已測/未測；dirty檔保留；new architecture無production write。
- Tests：既有70 tests、proposal JSON檢查、文件coverage/link與dirty保存檢查。
- Forbidden：production code、正式sheet、scheduler、credential內容。
- Commit unit（若授權）：`docs(opportunity): design opportunity intelligence layer`；proposals可另包。

## WP1 — Offline contract proposal validation（NEXT SINGLE TASK）

- 唯一目標：為本輪兩份proposal建立離線schema + semantic validator及正反fixtures，不批准contract。
- Input：`contracts/ahrefs_scope.v1.proposal.json`、`opportunity_contract.v1.proposal.json`、CONTRACT_DESIGN/SCORING/CONFIDENCE。
- Output：`reporting/opportunity/proposal_validation.py`、`tests/test_opportunity_proposals.py`、`tests/fixtures/opportunity/`，更新NEXT_TASK/handoff結果。
- Acceptance：缺source refs、錯state、production env、缺score卻approved、score/profile計算不符、duplicate evidence IDs、scope未批准執行皆拒絕；有效synthetic discovery/validated符合；既有contract不變。
- Tests：pure unittest；不得依live API；schema library若無則明確依賴策略，不能悄悄skip驗證。
- Forbidden：ingestion、engine detection、bridge、舊reporting modules、production sheets、正式contract promotion、改weight。
- Commit unit：`test(opportunity): validate contract proposals offline`。

## WP2 — Ahrefs scope / ingestion adapter

- 唯一目標：scope-approved request→typed estimate evidence+manifest。
- Input：WP1 schemas、owner scope/competitor/budget approval、已測tool docs。
- Output：`reporting/sources/ahrefs.py`、local evidence adapter、sanitized request manifest與fixtures。
- Acceptance：explicit modes/country/select/limit；source_class=THIRD_PARTY_ESTIMATE；duplicate/retry/no data/quota/schema drift有狀態；coverage可證；不寫正式rows。
- Tests：fake transport的成功、403/429、stale、truncated、invalid metric、history metadata；live smoke opt-in並另列cost。
- Forbidden：crawl competitors全站、SERP批掃、topic scoring、production publish。
- Dependencies：WP1；scope/budget沒批只能fixture路徑。
- Commit unit：`feat(opportunity): ingest scoped Ahrefs evidence`。

## WP3 — Canonical entity registry

- 唯一目標：保守且版本化的query/keyword/prompt/URL/topic mappings。
- Input：WP1 schema、URL/brand/prompt registry完整核對後的sanitized exports、兩站scope。
- Output：`reporting/opportunity/entities.py`、registry fixtures、mapping revision manifest。
- Acceptance：繁簡不自動合併；semantic URLs保留；duplicate keyword/topic deterministically處理；same keyword multiple URLs保留；parent/child competitor不double count。
- Tests：unicode、tracking query、path case、www/redirect conflict、alias歧義、split/merge、版本回放。
- Forbidden：自動批准semantic mappings、改正式Brand Dictionary、數據量評分。
- Dependencies：WP1；可使用fixture不等WP2 live資料。
- Commit unit：`feat(opportunity): add versioned entity mappings`。

## WP4 — Evidence / candidate immutable store

- 唯一目標：把新層record/revision存成可重播artifact。
- Input：WP1 proposals、WP3 IDs、現有snapshot實作作參考。
- Output：`reporting/opportunity/evidence.py`、`candidate_store.py`、run manifest與tests。
- Acceptance：相同inputs no-op，修訂supersedes最新hash；最新FAILED不得回舊READY；approval不跟到新revision；production入口不存在。
- Tests：idempotency、tamper、duplicate、stale、out-of-order revision、time travel、nonfinite numbers。
- Forbidden：放寬既有snapshot_mvp supported_metrics、改actual contract、live storage migration。
- Dependencies：WP1/3。
- Commit unit：`feat(opportunity): store immutable evidence and candidates`。

## WP5 — SEO engine v1（Ahrefs + GSC + SF）

- 唯一目標：從離線validated evidence產SEO候選與可解釋分數。
- Input：WP2/3/4；GSC query×page完整scope fixtures、SF URL issues；business overlay proposals。
- Output：`reporting/opportunity/rules_seo.py`、`scoring.py`、`confidence.py`。
- Acceptance：10個types用規則gate（GEO只產缺evidence狀態）；CREATE_NEW需完整inventory；technical precedence；INSUFFICIENT/CONFLICT/DO_NOTHING分開；scores無missing imputation。
- Tests：TEST_STRATEGY中的T01–T21與profile bounds；至少A–F fixtures（GEO待補）；不同request順序結果相同。
- Forbidden：用現有Top25推content gap、live calls、真實recommendation、把Business Actual按URL分攤。
- Dependencies：WP2/3/4；資料不足仍能完成deterministic engine驗收。
- Commit unit：`feat(opportunity): detect and score SEO candidates`。

## WP6 — GA4 quality diagnostics

- 唯一目標：在候選上加landing-quality evidence。
- Input：GA4 scope、WP4/5、approved property/hostname；landing dimensions compatibility smoke。
- Output：`reporting/sources/ga4_quality.py` + candidate diagnostic projection。
- Acceptance：同grain engagement rates；CTA只diagnostic；threshold/missing不補零；不跨property合計。
- Tests：landing path、host filter、session/event差異、sampling、threshold、GA4 missing仍可保留SEO candidate。
- Forbidden：建立success mapping、GA4 admin edits、query string/PII、keyword discovery。
- Dependencies：WP4/5；smoke失敗可用fixtures驗adapter，但標live blocked。
- Commit unit：`feat(opportunity): attach GA4 landing diagnostics`。

## WP7 — SERP validation

- 唯一目標：shortlist才做可追溯intent/feature validation。
- Input：WP5 shortlist、approved provider/locale/device budget。
- Output：`reporting/sources/serp.py`、`reporting/opportunity/serp_validation.py`。
- Acceptance：cap30可設定；observed_at與provider provenance；三種SERP state；AIO/PAA未capture不是absence；intent mismatch擋approval。
- Tests：mixed intent、cache stale、location缺失、feature missing、row count超cap、quota、AIO未知。
- Forbidden：全keyword自動掃Google、cached Ahrefs冒充live、production rows。
- Dependencies：WP4/5；provider未定只offline。
- Commit unit：`feat(opportunity): validate shortlisted SERP intent`。

## WP8 — GEO fixed sample layer

- 唯一目標：Workduo prompt/entity/citation gaps轉GEO候選。
- Input：WP3/4/7、核准prompt_set與entity registry、matched runs。
- Output：`reporting/sources/workduo.py`、`reporting/opportunity/rules_geo.py`。
- Acceptance：Prompt Gap/Entity Gap/Citation Gap/Competitor Winning Prompt/Topic Visibility Gap各有直接evidence；未觀測citation不冒稱缺citation；GEO score profile固定。
- Tests：stale、sample drift、missing platforms、alias contamination、同prompt多run、citation URL domain判定、GEO_ENHANCE。
- Forbidden：改Core題庫、把sample當market share、只有schema markup解法。
- Dependencies：WP3/4/5/7。
- Commit unit：`feat(opportunity): detect fixed-sample GEO gaps`。

## WP9 — Opportunity preview / UAT report

- 唯一目標：新增內容與關鍵字機會preview讀取projection。
- Input：WP4–8 candidates、WORKBOOK_ARCHITECTURE、synthetic fixture。
- Output：`reporting/opportunity/report_projection.py`、獨立preview模板；UAT有ID後才接表。
- Acceptance：四主分組、最多20首屏、evidence日期/estimate/confidence/missing可見；舊詳細/exec視圖無回歸；UAT與production ID不同。
- Tests：render schema、empty/partial/conflict、HTML/formula injection、desktop375px、old schema parity。
- Forbidden：改production Recommendations/Next_Steps、在正式表放假期測試列、改舊UI section枚舉卻不測caller。
- Dependencies：WP4/5；GEO缺時可顯示pending，不能假填data。
- Commit unit：`feat(opportunity): render preview candidate review`。

## WP10 — Human review / recommendation bridge

- 唯一目標：approved exact revision才能產可審查promotion manifest與UAT projection。
- Input：WP9、human identity policy、approved event。
- Output：`reporting/opportunity/review.py`、`review_bridge.py`、UAT readback。
- Acceptance：engine不可自簽；hash invalidation；idempotency；人工改列衝突不覆寫；Next Steps仍人工selection。
- Tests：unapproved/expired/hash mismatch/destination錯誤拒絕、timeout reconciliation、manual text edit、跨期sourceRef、撤回。
- Forbidden：未批准production activation、自动發文、自动寫executive priorities。
- Dependencies：WP4/9；review身份策略未定不能宣布可production。
- Commit unit：`feat(opportunity): bridge approved candidate revisions`。

## WP11 — Outcome tracking

- 唯一目標：對已完成action建立30/60/90d結果評估。
- Input：approved measurement plan、completed_at、baseline/after fixtures。
- Output：`reporting/opportunity/outcomes.py`、checkpoint projection。
- Acceptance：完整period/final gates、相同scope、五種結果、非單metric WON、immutable outcome revisions。
- Tests：日期邊界、partial/final、取消/未完成、seasonality/guardrail、missing attribution、changed prompt cohort。
- Forbidden：scheduler、用CTA代正式轉換、聲稱causal ROI。
- Dependencies：WP4/10。
- Commit unit：`feat(opportunity): track reviewed action outcomes`。

## WP12 — Production hardening（最後gate）

- 唯一目標：驗證一個production promotion的安全可回滾路徑。
- Input：WP1–11、owner環境/activation授權、remote deploy/ACL readback、business規則確認。
- Output：destination allowlist、staging/readback/active_run、runbook、recovery evidence。
- Acceptance：無silent approval、舊report parity、source failures可見、rollback回上一manifest、成本/最小權限/PII tests；human確定要上線才promotion。
- Tests：integration/smoke獨立pipeline、rate limit/cost caps、partial publish、wrong workbook、duplicate retry、permission denied；production smoke只approved rows。
- Forbidden：force push、全面refactor、未授權scheduler或公開分享；不把所有先前未完成WP塞進此包。
- Dependencies：全部required gates通過，任一UNKNOWN停止activation。
- Commit unit：`feat(opportunity): harden controlled production promotion`。

WP12 implementation result（2026-09-14）：offline proposal-only activation/release manifest
hardening 已完成。`WP12_PRODUCTION_HARDENING_READINESS = READY`；production activation 仍是
`NOT_AUTHORIZED`，沒有自動後續 WP。30 targeted tests 與 311 full regression tests PASS；
未啟用 scheduler、writer、Recommendations、Next Steps 或任何 production destination。

Canonical月報搬移另走ARCHITECTURE migration序列：先characterization，再thin wrappers、period injection、template parity；不和WP5 engine或WP10治理混成一個大diff。

## Production Phase 1 — Recommendation canary writer（completed offline/UAT）

- 唯一目標：以 exact human-approved Recommendation Bridge 驗證一筆受控 Recommendation
  的 WriteIntent、synthetic target、mandatory readback、reconciliation 與 audit receipt。
- Output：`reporting/opportunity/canary_writer.py`、兩份 proposal contract、A–V synthetic
  fixture 與 targeted tests。
- Governance：UAT target only；allowlist/protected fields、trusted identity、one operation、
  no automatic retry、kill switch、append-only idempotency/audit 均 fail closed。
- Result：`PHASE1_CANARY_WRITER_READINESS = READY`；`PRODUCTION_ACTIVATION = NOT_AUTHORIZED`；
  production mutation=0。
- Explicitly excluded：real workbook/Google write、OAuth consent/refresh、scheduler、
  Next Steps/outcome automation、live collection、bulk/multi-target publish、Apps Script。
- Promotion gate：logical design decisions are confirmed for target type/tab, authorized-user
  OAuth, project owner/user operational/rollback/kill-switch authority, one operation,
  mandatory readback, no automatic retry and one-business-day observation. The next task is
  environment binding: create the dedicated workbook, verify exact workbook/Drive binding,
  OAuth principal, ACL, trusted-review identity binding and persistent audit binding. This
  remains separate from production activation.


## Production Phase 1 — Canary Environment Binding（completed environment setup）

- Result：`CANARY_ENVIRONMENT_BINDING = READY`。Exact Drive root、dedicated folder chain、
  independent workbook、`Opportunity_Recommendations` tab、canonical header、ACL、empty-target
  readback 與 audit folder binding 均完成。
- Mutation accounting：environment resources created/reused as authorized；structural sheet
  writes = `1`（header only）；`RECOMMENDATION_RECORDS_WRITTEN = 0`；
  `PRODUCTION_AUDIT_RECEIPTS_WRITTEN = 0`；`PRODUCTION_BUSINESS_DATA_MUTATION = 0`。
- Governance：binding metadata 在 external config；不含 credential/token/secret，不把 real IDs
  寫入 Git。Trusted human-review identity/provider 尚未 verified，不能以 OAuth principal 取代。
- Excluded：Recommendation writer、WriteIntent、live source collection、scheduler、Next Steps
  automation、outcome automation、batch expansion、production activation。
- Next single task：**Phase 1 Zero-Write Production-Config Dry Run**。
