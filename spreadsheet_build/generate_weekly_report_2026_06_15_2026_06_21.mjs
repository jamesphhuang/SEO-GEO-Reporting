import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");
const workspaceRoot = path.resolve(projectRoot, "..");
const periodStart = "2026-06-15";
const periodEnd = "2026-06-21";
const executedAt = "2026-06-22 09:36:55 CST";
const reportTitle = "SEO 週報｜SHOPLINE｜2026-06-15 至 2026-06-21";
const runId = "weekly-seo-20260615-20260621-20260622-093655";
const outDir = process.env.SEO_GEO_REPORT_OUTPUT_DIR || path.join(workspaceRoot, "90_正式報告");
const outPath = path.join(outDir, `${periodStart}_${periodEnd}_週報.xlsx`);

const weeklyHeaders = [
  "week_start","week_end","summary","top_opportunity","top_risk","organic_clicks_change","organic_sessions_change","conversions_change","recommended_actions","next_review_date","競爭對手比較","競品內容缺口","競品AI搜尋觀察","title","executed_at","data_quality","gsc_summary","ga4_summary","ahrefs_summary","screaming_frog_summary","workduo_summary","competitor_comparison","status","executive_summary","keyword_cluster_summary","search_performance_summary","technical_seo_summary","internal_linking_summary","content_recommendation_summary","competitor_ai_summary","action_count","p1_action_count","validation_status"
];

const weeklyRow = [
  periodStart,
  periodEnd,
  "本週未能取得新的 GSC、GA4、Ahrefs、Screaming Frog、Workduo AI 週資料；目前唯一可驗證的事實是所有 MCP connector 在握手階段逾時，故本列為 blocked fallback 報告而非完整數據週報。",
  "最高優先機會不是新增策略，而是先恢復 Google Drive、Ahrefs、Workduo 與 GA4 的 MCP 可讀性，否則無法對 2026-06-15 至 2026-06-21 形成可驗證洞察。",
  "最大風險是用舊洞察冒充新週結論，因此本週嚴格不做新數據臆測；所有業務與競品判斷僅能保留為上次已驗證 run 的 carry-forward。",
  "Current-week GSC unavailable because connector handshake timed out before any query could run.",
  "Current-week GA4 unavailable because connector handshake timed out before any query could run.",
  "Current-week conversion data unavailable; no organic keyEvents or revenue could be validated.",
  "P1 restore Google Drive write/read access; P1 restore Ahrefs MCP handshake; P1 restore Workduo AI MCP handshake; P1 restore native GA4 connector; P2 rerun weekly extraction for 2026-06-15 to 2026-06-21 after connectors recover; P2 replay Weekly_Report/SEO_Actions/Insight_Evidence/MCP_Run_Log writes; P2 validate Screaming Frog availability else Ahrefs Site Audit fallback; P2 recheck competitor snapshot after Ahrefs restore; P2 backfill current-week evidence for every P1 SEO action; P2 close connector monitoring gap with preflight health checks.",
  "2026-06-29",
  "競品比較本週無法刷新：Ahrefs Site Explorer 與 batch analysis 在 MCP handshake 前即失敗。上次已驗證基線仍顯示 91APP 流量領先、Cyberbiz 關鍵字廣度與 refdomains 領先、Shopify TW 以工具頁勝出，但這不是本週新資料。",
  "競品內容缺口本週無法刷新；僅保留上次已驗證方向作 carry-forward：比較頁、工具/生成器、社群素材尺寸、AI 解釋與 FAQ 引用友善頁。",
  "競品 AI 搜尋觀察本週無法刷新：Workduo AI connector 未能完成握手，因此 citation share、visibility、sentiment theme 都無法取得新週資料。",
  reportTitle,
  executedAt,
  "FAIL: Google Drive metadata read retried 2x and both timed out during MCP handshake. FAIL: Ahrefs management/site-audit/GSC/web-analytics calls timed out during MCP handshake. FAIL: Workduo AI calls timed out during MCP handshake. FALLBACK: local workbook generated only. NOTE: no fresh 2026-06-15..2026-06-21 source rows were available, so any persistent SEO issues below are carry-forward from the last validated run on 2026-06-08 and must be revalidated after connectors recover. Screaming Frog status unknown; cannot verify fallback condition with fresh data.",
  "GSC current-week summary unavailable. No page, query, CTR, impression, position, decline-page or cannibalization rows could be collected because the connector failed before query execution.",
  "GA4 current-week summary unavailable. Organic Search sessions, users, engaged sessions, keyEvents and landing-page conversion rate are all missing because no GA4-capable connector was available this run.",
  "Ahrefs current-week summary unavailable. No fresh GSC proxy, Web Analytics, Site Audit, Site Explorer, competitor snapshot or content gap rows could be collected.",
  "Screaming Frog MCP was not reachable and could not be tested. Ahrefs Site Audit fallback also could not run because Ahrefs MCP itself failed to start, so technical issue counts and sample URLs are unavailable for this week.",
  "Workduo current-week summary unavailable. No AI visibility, citation share, competitor mention or sentiment-theme data could be collected.",
  "Competitor comparison not refreshed this week due to full MCP outage. Use previous validated benchmark only as backlog context, not as current-week evidence.",
  "blocked",
  "最大問題：本週不是單一 SEO issue，而是資料層全面失效，造成週報無法建立。最大機會：恢復 connector 後可立刻重跑同一週期，不需重新定義報表。最大風險：若沿用 2026-06-08 前的洞察當作 2026-06-15 至 2026-06-21 新結論，會污染決策。P1 4 項、P2 6 項、P3 0 項；本週建議以資料恢復與重跑為唯一主軸。",
  "Top organic queries unavailable. Top non-brand queries unavailable. Rising/declining queries unavailable. Long-tail opportunities unavailable. Carry-forward only: existing strategic clusters still include 電商平台/開店平台/網站架設 intent=Commercial, POS/OMO intent=Commercial, AI/零售 AI intent=Informational+Commercial, 社群導購/直播 intent=Commercial, 品牌信任/定價/客服 intent=Navigational+Commercial. These cluster notes come from the 2026-06-08 validated run and require fresh-week revalidation.",
  "High-impression low-CTR pages unavailable for current week. Position 4-20 opportunities unavailable. Click/impression decline pages unavailable. Query cannibalization unavailable. GA4 Organic Search sessions/users/engaged sessions/keyEvents/conversion rate unavailable. Validation requirement for GA4 metrics is therefore not met.",
  "Core Web Vitals / speed: unavailable. Crawl / indexability: unavailable. Robots / noindex / canonical: unavailable. Duplicate title/meta/H1/content: unavailable. 404 / redirect / broken links: unavailable. Structured data / hreflang / sitemap: unavailable. Because both Screaming Frog and Ahrefs MCP were unreachable, this module cannot provide affected URL counts or sample URLs for the current week.",
  "Current-week internal-linking recommendations cannot be refreshed. Carry-forward context only from the last validated run: /ai, CSR, payments news and crowdfunding pages were weakly linked or sitemap-missing and should remain first candidates for recheck once crawl data returns.",
  "Current-week low-efficiency page classification unavailable. Carry-forward only: likely refresh targets previously included /about, /showcase, /faq/about and /online-store/features; comparison pages and AI proof pages previously required expansion. None of these should be treated as current-week confirmed recommendations until data is rerun.",
  "Current-week competitor and AI summary unavailable because both Ahrefs and Workduo connectors failed before query execution. Carry-forward context only: prior validated competitor angles were free tools/generators, social-media template assets, and citation-friendly AI/retail explainers.",
  10,
  4,
  "fail"
];

const actionHeaders = [
  "created_date","priority","category","url","query_or_keyword","issue","evidence","recommendation","expected_impact","status","owner","due_date","done_date","result_note","problem","impact","expected_outcome_range","how_to","priority_score","business_impact","traffic_opportunity","conversion_relevance","technical_risk","effort","confidence"
];

const actions = [
  ["2026-06-22","P1","Data Pipeline","https://docs.google.com/spreadsheets/d/1YdB3R1JmLjIH1fRhFg1r0fei887sbtVopkBnWbFWCi0/edit","Weekly_Report write","Google Drive connector cannot complete metadata handshake, so the reporting control sheet is unreadable and unwritable","Google Drive metadata read retried twice and both returned MCP startup handshake timeout","Restore Google Drive connector health and re-run metadata read before any row append","Recover reporting control plane and native Sheet writeback","blocked","","2026-06-23","","","The weekly reporting sheet itself is inaccessible through MCP.","Without Sheet access, this automation cannot read MCP_Config or append the canonical weekly record.","Reporting availability +100%; Sheet write success 0->1","Reauthenticate or restart the Google Drive connector, confirm spreadsheet metadata loads, then append Weekly_Report / SEO_Actions / Insight_Evidence / MCP_Run_Log.","14","5","3","4","5","3","0.99"],
  ["2026-06-22","P1","Data Pipeline","MCP_Config","Ahrefs MCP","Ahrefs MCP cannot start, blocking GSC, Web Analytics, Site Audit, Site Explorer and competitor snapshots","Management projects and site audit calls both failed during MCP startup handshake timeout","Restore Ahrefs MCP client startup and validate project 1584843 before rerunning the weekly extraction","Recover the primary SEO dataset for performance, technical and competitor modules","blocked","","2026-06-23","","","The main SEO data source is unavailable before any query executes.","Without Ahrefs, the report loses search, technical and competitor evidence at the same time.","Coverage +60-80%; Evidence completeness +60-80%","Restart/reconnect Ahrefs MCP, validate management_projects and site_audit_projects, then rerun the bounded weekly queries.","15","5","5","3","5","3","0.99"],
  ["2026-06-22","P1","Data Pipeline","MCP_Config","Workduo AI MCP","Workduo AI MCP cannot start, blocking AI visibility, citation share and sentiment-theme monitoring","Workduo sentiment theme call failed during MCP startup handshake timeout","Restore Workduo AI connector and rerun visibility/citation slices for the weekly period","Recover AI-search competitor evidence and GEO monitoring","blocked","","2026-06-23","","","AI-search reporting is fully dark this week.","Without Workduo, competitor citation share and absence-theme trends cannot be validated.","AI insight coverage +100%; GEO monitoring latency -80-100%","Reconnect Workduo MCP, validate project/workspace IDs, then fetch visibility, citations and sentiment themes for 2026-06-15..2026-06-21.","13","4","3","3","5","2","0.98"],
  ["2026-06-22","P1","Measurement","MCP_Config","GA4 Organic Search key events","No GA4-capable connector was available, so organic sessions/users/keyEvents validation failed","This run contains zero GA4 rows and therefore fails the required quality gate","Restore native GA4 Organic Search reporting before the rerun","Recover conversion relevance for action scoring","blocked","","2026-06-23","","","The automation cannot confirm organic conversions or engaged sessions for the target week.","Without GA4 metrics, priority scoring loses conversion grounding and validation cannot pass.","Key events +3-8%; Reporting confidence +20-40%","Reconnect GA4, validate Organic Search filter and key event dimensions, and store only aggregated weekly metrics.","13","4","2","5","3","1","0.97"],
  ["2026-06-22","P2","Operations","MCP_Run_Log","Weekly rerun","The scheduled weekly run completed without source data and needs a bounded replay once connectors recover","All three required external MCP surfaces failed before any source query executed","Replay the exact weekly period 2026-06-15..2026-06-21 after connector recovery","Produce the missing weekly report without shifting the reporting window","open","","2026-06-24","","","The missed week is recoverable if the exact period is rerun promptly.","A bounded replay preserves continuity and avoids data-window drift.","Weekly report completeness +100%","After connector recovery, rerun the full extraction using the same period start and end dates.","10","3","4","3","2","2","0.95"],
  ["2026-06-22","P2","Reporting","Weekly_Report","Weekly_Report append","The canonical weekly row was not appended because the target sheet was inaccessible","No successful Sheet metadata or write response exists for this run","Append exactly one weekly row after read/write access is restored","Restore reporting continuity for dashboards and downstream automation","open","","2026-06-24","","","The weekly log is broken at the control-sheet layer.","Missing the weekly row hides both failure state and later recovery from stakeholders.","Reporting continuity +100%; Auditability +100%","Re-read headers, map current schema, append one row, then verify only one new row was added.","9","3","2","3","3","2","0.94"],
  ["2026-06-22","P2","Reporting","SEO_Actions","Action backfill","No canonical action rows were written to the shared sheet for this run","Current actions exist only in local fallback workbook","Backfill 10 action rows to SEO_Actions after sheet write access returns","Restore execution tracking and ownership visibility","open","","2026-06-24","","","Action tracking is stranded in a local fallback artifact.","Without row-level actions in the sheet, owners cannot manage status or due dates centrally.","Execution visibility +100%; Coordination latency -50-80%","Append the 10 prepared rows, then confirm action count and P1 cap validation.","9","3","2","3","3","2","0.93"],
  ["2026-06-22","P2","Reporting","Insight_Evidence","Evidence backfill","No current-run evidence rows were written to the shared sheet","Evidence exists only as fallback documentation of connector outages and carry-forward context","Backfill evidence rows for the outage plus fresh evidence after rerun","Restore traceability from weekly summary to source evidence","open","","2026-06-24","","","The weekly summary currently has no sheet-native evidence trace.","Without evidence rows, future readers cannot distinguish outage facts from SEO facts.","Traceability +100%; Review time -30-50%","Write outage evidence immediately, then replace/add fresh source-backed evidence after rerun.","8","2","2","3","3","2","0.92"],
  ["2026-06-22","P2","Technical SEO","MCP_Config","Screaming Frog fallback validation","This run could not confirm whether Screaming Frog is unavailable or whether Ahrefs Site Audit fallback is functioning","Both Screaming Frog status and Ahrefs technical fallback were blocked upstream","Revalidate technical-data path explicitly on rerun","Restore confidence in the technical SEO module","open","","2026-06-24","","","The technical module currently fails both primary and fallback paths.","Without explicit fallback validation, future warnings may hide real crawl regressions.","Technical module completeness +100%; False-warning rate -50-80%","Attempt Screaming Frog first; if unavailable, run Ahrefs Site Audit and annotate data_quality with the fallback used.","8","2","2","2","4","2","0.91"],
  ["2026-06-22","P2","Monitoring","MCP_Config","Connector preflight","The automation lacks a preflight guard that would surface connector health before the reporting window closes","This run discovered failures only while already executing the weekly job","Add preflight checks for Google Drive, Ahrefs, Workduo and GA4 connector health","Reduce silent failures and speed up intervention","open","","2026-06-29","","","Connector failure detection happens too late in the current workflow.","Earlier health checks reduce lost weeks and shorten recovery time.","Reporting latency -30-60%; Failure detection +100%","Add a preflight step that pings each connector with one bounded read and logs pass/fail before the weekly extraction starts.","8","2","3","2","3","2","0.9"]
];

const evidenceHeaders = [
  "run_id","evidence_id","source_tool","insight_type","page_url","keyword_or_topic","metric_summary","comparison","source_query","confidence","action_ref","created_at","evidence_date","report_title","source","category","entity","metric","value","evidence","implication","expected_outcome_range","module","priority_score"
];

const evidenceRows = [
  [runId,"E1","Google Drive MCP","Connector outage","https://docs.google.com/spreadsheets/d/1YdB3R1JmLjIH1fRhFg1r0fei887sbtVopkBnWbFWCi0/edit","Weekly_Report write path","2 metadata-read attempts, 0 successes","Same handshake timeout on both retries","get_spreadsheet_metadata x2","0.99","A1","2026-06-22","2026-06-22",reportTitle,"Google Drive","Data Pipeline","Technical SEO AI Agent sheet","metadata_handshake_success","0/2","The Google Drive connector failed before returning spreadsheet metadata.","Sheet access must be restored before any canonical weekly append can happen.","Reporting availability +100%","executive_summary","14"],
  [runId,"E2","Ahrefs MCP","Connector outage","MCP_Config","Ahrefs startup","Management and Site Audit startup both failed before query execution","0 source rows collected for the target week","management_projects + site_audit_projects","0.99","A2","2026-06-22","2026-06-22",reportTitle,"Ahrefs","Data Pipeline","Ahrefs MCP","startup_handshake_success","0","No Ahrefs surface was reachable, so search, technical and competitor evidence are all missing.","Ahrefs recovery is the highest-leverage unblocker for this automation.","Coverage +60-80%","executive_summary","15"],
  [runId,"E3","Workduo AI MCP","Connector outage","MCP_Config","Workduo startup","Sentiment theme startup failed before query execution","0 AI visibility/citation rows collected for the target week","sentiment_themes custom 2026-06-15..2026-06-21","0.98","A3","2026-06-22","2026-06-22",reportTitle,"Workduo","Data Pipeline","Workduo AI","startup_handshake_success","0","The AI-search module is fully unavailable this week.","Connector recovery is required before any citation-share or sentiment conclusion can be made.","AI insight coverage +100%","competitor_ai_summary","13"],
  [runId,"E4","Validation","Quality gate","MCP_Config","GA4 metrics requirement","0 Organic Search sessions/users/keyEvents rows available","Fails the stated GA4 validation requirement","weekly validation check","0.97","A4","2026-06-22","2026-06-22",reportTitle,"Validation","Measurement","GA4 Organic Search","required_metrics_present","false","This run cannot satisfy the required GA4 metrics gate.","Do not mark the report as warning or complete; it must remain fail until rerun.","Reporting confidence +20-40%","search_performance_summary","13"],
  [runId,"E5","Carry-forward context","Prior validated run","/ai","internal linking / sitemap","Last validated run on 2026-06-08 flagged /ai and related pages as weakly linked or sitemap-missing","This is not current-week evidence and must be revalidated","memory.md 2026-06-08 entry","0.62","A9","2026-06-22","2026-06-08",reportTitle,"Memory","Carry Forward","/ai","carry_forward_issue","weakly linked + sitemap-missing previously","Persistent issues may still matter, but they are backlog context only until fresh crawl data returns.","Technical module completeness +100%","internal_linking_summary","8"]
];

const runLogHeaders = [
  "run_id","run_datetime","period_start","period_end","source_tool","query_type","query_summary","limit","status","rows_returned","error_or_note"
];

const runLogs = [
  [runId,executedAt,periodStart,periodEnd,"Google Drive MCP","spreadsheet_metadata","Read target spreadsheet metadata before config discovery","1","fail","0","Retried twice; both attempts failed with MCP startup handshake timeout."],
  [runId,executedAt,periodStart,periodEnd,"Ahrefs MCP","management_projects","Resolve Ahrefs project IDs before weekly extraction","20","fail","0","MCP startup failed: timed out handshaking with MCP server after 30s."],
  [runId,executedAt,periodStart,periodEnd,"Ahrefs MCP","site_audit_projects","Resolve latest technical crawl and fallback readiness","20","fail","0","MCP startup failed: timed out handshaking with MCP server after 30s."],
  [runId,executedAt,periodStart,periodEnd,"Workduo AI MCP","sentiment_themes","Check AI visibility/sentiment availability for custom weekly period","5","fail","0","MCP startup failed: timed out handshaking with MCP server after 30s."],
  [runId,executedAt,periodStart,periodEnd,"GA4 MCP","organic_search_metrics","Expected native Organic Search sessions/users/keyEvents","20","fail","0","No callable GA4 connector was available in this run."],
  [runId,executedAt,periodStart,periodEnd,"Local workbook","fallback_output","Generate blocked weekly fallback workbook in workspace","1","success","1","Created local fallback report because all external connectors were unavailable."]
];

const payload = {
  outPath,
  weeklyHeaders,
  weeklyRow,
  actionHeaders,
  actions,
  evidenceHeaders,
  evidenceRows,
  runLogHeaders,
  runLogs,
};

async function buildWorkbook() {
  const { SpreadsheetFile, Workbook } = await import("@oai/artifact-tool");
  const wb = Workbook.create();
  const weekly = wb.worksheets.add("Weekly_Report");
  const actionsWs = wb.worksheets.add("SEO_Actions");
  const evidenceWs = wb.worksheets.add("Insight_Evidence");
  const logWs = wb.worksheets.add("MCP_Run_Log");

  for (const ws of [weekly, actionsWs, evidenceWs, logWs]) {
    ws.showGridLines = false;
  }

  weekly.getRange("A1:AG1").values = [weeklyHeaders];
  weekly.getRange("A2:AG2").values = [weeklyRow];
  actionsWs.getRange("A1:Y1").values = [actionHeaders];
  actionsWs.getRange(`A2:Y${actions.length + 1}`).values = actions;
  evidenceWs.getRange("A1:X1").values = [evidenceHeaders];
  evidenceWs.getRange(`A2:X${evidenceRows.length + 1}`).values = evidenceRows;
  logWs.getRange("A1:K1").values = [runLogHeaders];
  logWs.getRange(`A2:K${runLogs.length + 1}`).values = runLogs;

  const xlsx = await SpreadsheetFile.exportXlsx(wb);
  await xlsx.save(outPath);
}

await fs.mkdir(outDir, { recursive: true });
if (process.argv.includes("--json")) {
  console.log(JSON.stringify(payload));
} else {
  await buildWorkbook();
  console.log(outPath);
}
