import React from "react";

import {
  ChartRenderer, DataComponent, DataTable, MetricCard, ReportSection, RichNarrative,
  SortableItem, SortableRegion, useDataApp,
} from "../../data-app-public.jsx";

const sectionOrder = ["report-npl", "report-sql", "report-yoy", "report-pending", "report-methods"];

const nplTrend = {
  type: "bar", x: "month", y: "nonPaidActual", fields: ["nonPaidActual", "nonPaidTarget"],
  stackable: false, showXAxisLabel: false, yLabel: "Leads", showValues: false,
  legend: { labels: { nonPaidActual: "Actual", nonPaidTarget: "Target" } },
};

const sqlTrend = {
  type: "bar", x: "month", y: "sqlActualCurrent", fields: ["sqlActualCurrent", "sqlTarget"],
  stackable: false, showXAxisLabel: false, yLabel: "SQL", showValues: false,
  legend: { labels: { sqlActualCurrent: "Actual（成熟 Cohort）", sqlTarget: "Target" } },
};

const sqlRateTrend = {
  type: "bar", x: "period", y: "sqlRate", fields: ["sqlRate"],
  showXAxisLabel: false, yLabel: "SQL rate", showValues: true,
};

const pendingColumns = [
  { field: "month", label: "名單月份 Cohort" },
  { field: "sqlActualCurrent", label: "目前累積 SQL" },
  { field: "sqlTarget", label: "Target" },
  { field: "maturityDate", label: "滿 60 天日期" },
  { field: "sqlMaturity", label: "狀態", presentation: "status" },
];

const sum = (rows, field) => rows.reduce((total, row) => total + Number(row[field] || 0), 0);
const fmt = (value) => Number(value).toLocaleString("en-US");
const pct = (value, digits = 1) => `${(Number(value) * 100).toFixed(digits)}%`;
const pp = (value) => `${(Number(value) * 100).toFixed(2)} 個百分點`;

export function ReportContent() {
  const { reviewedPeriodRows, chartOverrides, chartProps, visible,
    canEdit, mode, appTitle, setAppTitle } = useDataApp();

  const monthly = reviewedPeriodRows("leadgen_monthly");
  const mature = monthly.filter((row) => row.sqlMaturity === "Mature");
  const pending = reviewedPeriodRows("leadgen_pending");
  const yoy = reviewedPeriodRows("leadgen_yoy_mature");

  const nplActual = sum(monthly, "nonPaidActual");
  const nplTarget = sum(monthly, "nonPaidTarget");
  const matureNplActual = sum(mature, "nonPaidActual");
  const matureNplTarget = sum(mature, "nonPaidTarget");
  const sqlActual = sum(mature, "sqlActualCurrent");
  const sqlTarget = sum(mature, "sqlTarget");
  const nplAttainment = nplActual / nplTarget;
  const sqlAttainment = sqlActual / sqlTarget;
  const sqlRate = sqlActual / matureNplActual;
  const sqlTargetRate = sqlTarget / matureNplTarget;
  const sqlRateGap = sqlRate - sqlTargetRate;
  const yoy2025 = yoy.find((row) => row.year === "2025");
  const yoy2026 = yoy.find((row) => row.year === "2026");
  const yoyNplChange = yoy2026 && yoy2025 ? yoy2026.nonPaidActual / yoy2025.nonPaidActual - 1 : null;
  const yoySqlChange = yoy2026 && yoy2025 ? yoy2026.sqlActual / yoy2025.sqlActual - 1 : null;

  const nplChart = chartOverrides["report-npl"] ?? nplTrend;
  const sqlChart = chartOverrides["report-sql"] ?? sqlTrend;
  const rateChart = chartOverrides["report-yoy"] ?? sqlRateTrend;
  const recentNplRows = monthly.filter((row) => row.month >= "2026-07");

  return <article className="report-content" aria-label="SEO / GEO 總覽報告">
    <header className="report-hero report-hero--leadgen">
      <p className="report-kicker">SEO / GEO 總覽報告 · Commercial KPI</p>
      <h1 data-data-app-title contentEditable={canEdit && mode === "edit"} suppressContentEditableWarning
        aria-label={canEdit && mode === "edit" ? "Edit report heading" : undefined}
        onBlur={canEdit && mode === "edit" ? (event) => setAppTitle(event.currentTarget.textContent.trim() || appTitle) : undefined}
        onKeyDown={canEdit && mode === "edit" ? (event) => {
          if (event.key === "Enter") { event.preventDefault(); event.currentTarget.blur(); }
        } : undefined}>{appTitle}</h1>
      <RichNarrative id="report:description" className="report-deck" label="Edit report introduction"
        value="以 2026 lead gen distribution 為基礎，檢視 Non-paid Leads、成熟 SQL（Sales-Qualified Lead）與未成熟 Cohort 的實際進度。資料截止 2026-08-31。" />
      <div className="report-meta-row" aria-label="Report scope">
        <span className="report-meta-chip">截止日 2026-08-31</span>
        <span className="report-meta-chip report-meta-chip--warning">SQL：月結後 60 天成熟</span>
        <span className="report-meta-chip">來源：Excel Actual／Target</span>
      </div>
    </header>

    {visible("report-summary") && <ReportSection id="report-summary" title="本期判讀" queryId="leadgen_monthly"
      sourceRows={monthly} showHeading={false} className="report-summary">
      <RichNarrative id="report-summary:body" className="report-summary-lead" label="Edit finding"
        value={`## Q2 回升，但 7–8 月 Non-paid Leads 再度偏離計畫

2026 年 1–8 月 Non-paid Leads 達成率為 **${pct(nplAttainment)}**（${fmt(nplActual)}／${fmt(nplTarget)}），落後 ${fmt(nplTarget - nplActual)} 筆。成熟 SQL（Sales-Qualified Lead）1–6 月達成率為 **${pct(sqlAttainment)}**（${fmt(sqlActual)}／${fmt(sqlTarget)}）。

成熟 SQL 轉換率為 **${pct(sqlRate, 2)}**，與目標 ${pct(sqlTargetRate, 2)} 相差 ${pp(sqlRateGap)}；目前較像是上游 Non-paid Leads 量不足，而不是 SQL 轉換效率顯著惡化。這是數學拆解，不代表已確認特定渠道或內容的因果。`} />
    </ReportSection>}

    <div className="report-facts report-facts--leadgen" aria-label="Key metrics">
      {visible("report-metric-npl") && <MetricCard id="report-metric-npl" title="Non-paid Leads 達成率"
        queryId="leadgen_monthly" sourceRows={monthly} value={pct(nplAttainment)}
        comparison={`${fmt(nplActual)}／${fmt(nplTarget)} · 落後 ${fmt(nplTarget - nplActual)}`}
        negative={nplAttainment < 1} description="2026 年 1–8 月；Actual／Target 加總。"
        trendValues={monthly.map((row) => row.nonPaidActual)} />}
      {visible("report-metric-sql") && <MetricCard id="report-metric-sql" title="成熟 SQL 達成率"
        queryId="leadgen_monthly" sourceRows={mature} value={pct(sqlAttainment)}
        comparison={`${fmt(sqlActual)}／${fmt(sqlTarget)} · 落後 ${fmt(sqlTarget - sqlActual)}`}
        negative={sqlAttainment < 1} description="僅計 1–6 月、月結後滿 60 天的 Cohort。"
        trendValues={mature.map((row) => row.sqlActualCurrent)} />}
      {visible("report-metric-rate") && <MetricCard id="report-metric-rate" title="成熟 SQL 轉換率"
        queryId="leadgen_monthly" sourceRows={mature} value={pct(sqlRate, 2)}
        comparison={`目標 ${pct(sqlTargetRate, 2)} · 差 ${pp(sqlRateGap)}`}
        deltaTone="neutral" description="成熟 SQL Actual ÷ 同期成熟 Non-paid Leads Actual。"
        trendValues={mature.map((row) => row.sqlActualCurrent / row.nonPaidActual)} />}
      {visible("report-metric-maturity") && <MetricCard id="report-metric-maturity" title="未成熟 SQL 累積"
        queryId="leadgen_pending" sourceRows={pending} value={fmt(sum(pending, "sqlActualCurrent"))}
        comparison="7–8 月 · 暫不納入正式結論" deltaTone="neutral"
        description="未滿月結後 60 天；持續顯示並等待成熟。" />}
    </div>

    <SortableRegion id="report:sections" label="Report sections" variant="stack" authoredOrder={sectionOrder}
      className="report-sortable-sections">
      {visible("report-npl") && <SortableItem id="report-npl" label="Non-paid Leads monthly progress" kind="chart">
        <DataComponent variant="card" id="report-npl" title="Non-paid Leads 月度 Actual／Target"
          queryId="leadgen_monthly" kind="chart" chart={nplChart} displayRows={monthly} sourceRows={monthly}
          description="2026 年 1–8 月；柱狀圖從零開始，便於比較每月實際量與 Target。" className="leadgen-chart-card">
          <ChartRenderer spec={nplChart} rows={monthly} height={280} {...chartProps("report-npl")} />
        </DataComponent>
      </SortableItem>}

      {visible("report-sql") && <SortableItem id="report-sql" label="Mature SQL monthly progress" kind="chart">
        <DataComponent variant="card" id="report-sql" title="成熟 SQL 月度 Actual／Target"
          queryId="leadgen_monthly" kind="chart" chart={sqlChart} displayRows={mature} sourceRows={monthly}
          description="僅繪製 1–6 月成熟 Cohort；7–8 月另列於未成熟清單。" className="leadgen-chart-card">
          <ChartRenderer spec={sqlChart} rows={mature} height={280} {...chartProps("report-sql")} />
        </DataComponent>
      </SortableItem>}

      {visible("report-yoy") && <SortableItem id="report-yoy" label="Mature SQL year-over-year comparison" kind="chart">
        <DataComponent variant="card" id="report-yoy" title="成熟 SQL 轉換率：2025 vs 2026 Jan–Jun"
          queryId="leadgen_yoy_mature" kind="chart" chart={rateChart} displayRows={yoy} sourceRows={yoy}
          description={`2026 轉換率 ${pct(sqlRate, 2)}；2025 轉換率 ${pct(yoy2025?.sqlRate, 2)}。2025 年 6 月含高峰會，解讀需保留活動註記。`} className="leadgen-chart-card">
          <ChartRenderer spec={rateChart} rows={yoy} height={240} {...chartProps("report-yoy")} />
        </DataComponent>
      </SortableItem>}

      {visible("report-pending") && <SortableItem id="report-pending" label="Immature SQL Cohorts" kind="table">
        <DataComponent variant="card" id="report-pending" title="未成熟 SQL Cohort：目前累積但不下正式結論"
          queryId="leadgen_pending" kind="table" sourceRows={pending} displayRows={pending}
          description="成熟日依名單月份月結後加 60 天計算；來源後續更正以追加式快照保留。" className="leadgen-table-card">
          <DataTable rows={pending} columns={pendingColumns} searchable={false} caption="未成熟 SQL Cohort 明細" />
        </DataComponent>
      </SortableItem>}

      {visible("report-methods") && <SortableItem id="report-methods" label="Interpretation and next checks" kind="narrative">
        <ReportSection id="report-methods" title="判讀與下一步" queryId="leadgen_monthly"
          queryIds={["leadgen_monthly", "leadgen_yoy_mature", "leadgen_pending"]}
          sourceRowsByQuery={{ leadgen_monthly: monthly, leadgen_yoy_mature: yoy, leadgen_pending: pending }}
          sourceRows={monthly} showHeading={false} className="report-methods">
          <RichNarrative id="report-methods:body" className="report-caveat" label="Edit implication and evidence notes"
            value={`## 判讀與下一步

**本期最大風險**：7–8 月 Non-paid Leads 合計 ${fmt(sum(recentNplRows, "nonPaidActual"))}／${fmt(sum(recentNplRows, "nonPaidTarget"))}，目前只有 ${pct(sum(recentNplRows, "nonPaidActual") / sum(recentNplRows, "nonPaidTarget"))}。

**建議優先檢查**：先用 GA4／Salesforce 依來源、landing page 與漏斗階段拆解 7–8 月名單量下降；在取得這些證據前，不把變化直接歸因於 SEO、內容或單一渠道。

**成熟期提醒**：7 月 Cohort 將於 2026-09-29 成熟，8 月 Cohort 將於 2026-10-30 成熟；成熟後若來源更正，仍須新增快照並更新判讀。`} />
          {yoyNplChange !== null && <p className="analysis-caption">2026 Jan–Jun vs 2025 Jan–Jun：成熟 Non-paid Leads {pct(yoyNplChange)}、成熟 SQL {pct(yoySqlChange)}；2025 年 6 月含高峰會。</p>}
        </ReportSection>
      </SortableItem>}
    </SortableRegion>
  </article>;
}
