from pathlib import Path
from html import escape


OUT_DIR = Path("Technical SEO AI Agent/seo_visual_2026-06-15_2026-06-21")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / "seo_visual_report_2026-06-15_2026-06-21.html"


def pct(value):
    return f"{value:.2f}%"


def bar_chart(title, rows, value_key, label_key="label", color="#0F766E", suffix=""):
    max_v = max(row[value_key] for row in rows) or 1
    h = 38 * len(rows) + 54
    parts = [
        f'<section class="card"><h2>{escape(title)}</h2>',
        f'<svg viewBox="0 0 900 {h}" role="img" aria-label="{escape(title)}">',
    ]
    for i, row in enumerate(rows):
        y = 38 * i + 38
        width = max(2, row[value_key] / max_v * 520)
        label = escape(str(row[label_key]))
        value = f"{row[value_key]:,.0f}{suffix}" if isinstance(row[value_key], int) else f"{row[value_key]:,.2f}{suffix}"
        parts.append(f'<text x="0" y="{y + 18}" class="axis">{label}</text>')
        parts.append(f'<rect x="280" y="{y}" width="{width:.1f}" height="22" rx="6" fill="{color}"></rect>')
        parts.append(f'<text x="{290 + width:.1f}" y="{y + 17}" class="value">{escape(value)}</text>')
    parts.append("</svg></section>")
    return "\n".join(parts)


def grouped_competitor_chart(rows):
    max_v = max(max(r["traffic"], r["keywords"], r["refdomains"]) for r in rows) or 1
    h = 72 * len(rows) + 70
    colors = {"traffic": "#0F766E", "keywords": "#D97706", "refdomains": "#2563EB"}
    parts = [
        '<section class="card"><h2>Ahrefs 競品比較：Traffic / Keywords / Refdomains</h2>',
        '<div class="legend"><span><b class="dot green"></b>Organic traffic</span><span><b class="dot amber"></b>Keywords</span><span><b class="dot blue"></b>Refdomains</span></div>',
        f'<svg viewBox="0 0 980 {h}" role="img" aria-label="Competitor benchmark">',
    ]
    for i, row in enumerate(rows):
        base_y = 46 + i * 72
        parts.append(f'<text x="0" y="{base_y + 22}" class="axis strong">{escape(row["label"])}</text>')
        for j, key in enumerate(["traffic", "keywords", "refdomains"]):
            y = base_y + j * 18
            width = max(2, row[key] / max_v * 560)
            parts.append(f'<rect x="220" y="{y}" width="{width:.1f}" height="13" rx="4" fill="{colors[key]}"></rect>')
            parts.append(f'<text x="{230 + width:.1f}" y="{y + 11}" class="mini">{row[key]:,}</text>')
    parts.append("</svg></section>")
    return "\n".join(parts)


def line_chart(title, series, color_map):
    w, h = 920, 360
    x0, y0, plot_w, plot_h = 60, 42, 800, 250
    values = [point["value"] for points in series.values() for point in points if point["value"] is not None]
    max_v = max(values) if values else 1
    min_v = min(values) if values else 0
    if max_v == min_v:
        max_v += 1
    parts = [
        f'<section class="card"><h2>{escape(title)}</h2>',
        '<div class="legend">' + "".join(
            f'<span><b class="dot" style="background:{color_map[name]}"></b>{escape(name)}</span>'
            for name in series
        ) + '</div>',
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">',
        f'<line x1="{x0}" y1="{y0 + plot_h}" x2="{x0 + plot_w}" y2="{y0 + plot_h}" class="grid"></line>',
        f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0 + plot_h}" class="grid"></line>',
    ]
    labels = [p["date"] for p in next(iter(series.values()))]
    for i, label in enumerate(labels):
        x = x0 + i * (plot_w / (len(labels) - 1))
        parts.append(f'<text x="{x - 22:.1f}" y="{y0 + plot_h + 28}" class="mini">{escape(label[5:])}</text>')
    for name, points in series.items():
        coords = []
        for i, point in enumerate(points):
            if point["value"] is None:
                continue
            x = x0 + i * (plot_w / (len(points) - 1))
            y = y0 + plot_h - ((point["value"] - min_v) / (max_v - min_v) * plot_h)
            coords.append((x, y))
        path = " ".join(("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}" for i, (x, y) in enumerate(coords))
        parts.append(f'<path d="{path}" fill="none" stroke="{color_map[name]}" stroke-width="4" stroke-linecap="round"></path>')
        for x, y in coords:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color_map[name]}"></circle>')
    parts.append("</svg></section>")
    return "\n".join(parts)


gsc_ctr = [
    {"label": "/online-store/features", "ctr": 0.24},
    {"label": "/faq/about", "ctr": 0.31},
    {"label": "/about", "ctr": 0.95},
    {"label": "/showcase", "ctr": 0.99},
    {"label": "/about/pricing", "ctr": 1.83},
    {"label": "/payments", "ctr": 4.41},
]

ga4_sessions = [
    {"label": "/", "sessions": 2998, "events": 66},
    {"label": "/users/sign_in", "sessions": 1229, "events": 9},
    {"label": "(not set)", "sessions": 1095, "events": 32},
    {"label": "/about/pricing", "sessions": 191, "events": 1},
    {"label": "/payments", "sessions": 78, "events": 0},
    {"label": "/about", "sessions": 53, "events": 0},
    {"label": "/showcase", "sessions": 42, "events": 0},
]

competitors = [
    {"label": "SHOPLINE", "traffic": 37479, "keywords": 2447, "refdomains": 1527},
    {"label": "91APP", "traffic": 42089, "keywords": 1819, "refdomains": 4373},
    {"label": "Cyberbiz", "traffic": 33992, "keywords": 3463, "refdomains": 6632},
    {"label": "meepShop", "traffic": 7431, "keywords": 813, "refdomains": 2600},
    {"label": "BVSHOP", "traffic": 39822, "keywords": 1078, "refdomains": 1209},
]

tech = [
    {"label": "Structured data rich result errors", "count": 97},
    {"label": "Not compressed", "count": 97},
    {"label": "x-default hreflang missing", "count": 83},
    {"label": "Meta description too short", "count": 68},
    {"label": "Slow pages", "count": 23},
    {"label": "Multiple H1", "count": 9},
    {"label": "Robots inaccessible", "count": 2},
]

dates = [f"2026-06-{d:02d}" for d in range(15, 22)]
visibility = {
    "Google AI Overview": [84.62, 92.59, 92.00, 93.10, 85.19, 78.57, 92.59],
    "ChatGPT": [73.08, 70.97, 83.87, 58.06, 74.19, 58.06, 61.29],
    "Gemini": [92.31, 100.00, None, 100.00, 33.33, 93.33, 93.55],
}
visibility_series = {
    name: [{"date": d, "value": values[i]} for i, d in enumerate(dates)]
    for name, values in visibility.items()
}

html = f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SEO 週報｜SHOPLINE｜2026-06-15 至 2026-06-21</title>
  <style>
    :root {{
      --ink: #17211f;
      --muted: #61706b;
      --paper: #f5f1e8;
      --card: #fffaf0;
      --line: #ded4c4;
      --green: #0f766e;
      --amber: #d97706;
      --blue: #2563eb;
      --red: #b91c1c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-serif, Georgia, "Noto Serif TC", "Songti TC", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(15,118,110,.16), transparent 36rem),
        linear-gradient(135deg, #f8f3e7 0%, #eee2cc 100%);
    }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 42px 22px 64px; }}
    header {{
      border: 1px solid var(--line);
      border-radius: 28px;
      padding: 34px;
      background: rgba(255,250,240,.82);
      box-shadow: 0 20px 60px rgba(54, 42, 24, .12);
    }}
    h1 {{ margin: 0; font-size: clamp(34px, 5vw, 64px); line-height: 1; letter-spacing: -.04em; }}
    h2 {{ margin: 0 0 18px; font-size: 23px; letter-spacing: -.02em; }}
    h3 {{ margin: 0 0 8px; font-size: 18px; }}
    p {{ line-height: 1.68; }}
    .meta {{ margin-top: 14px; color: var(--muted); font-size: 15px; }}
    .scoreboard {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 22px 0 0; }}
    .metric {{ border: 1px solid var(--line); border-radius: 18px; padding: 18px; background: #fffdf6; }}
    .metric b {{ display:block; font-size: 30px; margin-bottom: 6px; }}
    .metric span {{ color: var(--muted); font-size: 14px; }}
    .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-top: 18px; }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 24px;
      background: rgba(255,250,240,.9);
      padding: 24px;
      box-shadow: 0 10px 34px rgba(54, 42, 24, .08);
    }}
    .wide {{ grid-column: 1 / -1; }}
    .pill {{ display:inline-block; padding: 7px 10px; border-radius: 999px; background:#e7f2ef; color:#0f5f59; font-weight:700; margin-right:8px; }}
    .risk {{ background:#fee2d7; color:#9a3412; }}
    .axis {{ font: 14px ui-sans-serif, system-ui, sans-serif; fill: #34423d; }}
    .value, .mini {{ font: 13px ui-sans-serif, system-ui, sans-serif; fill: #34423d; }}
    .strong {{ font-weight: 700; }}
    .grid {{ stroke: #d8cfc0; stroke-width: 1; }}
    .legend {{ display:flex; gap:18px; flex-wrap:wrap; color:var(--muted); font: 14px ui-sans-serif, system-ui, sans-serif; margin-bottom: 10px; }}
    .dot {{ display:inline-block; width:10px; height:10px; border-radius:99px; margin-right:6px; vertical-align:middle; }}
    .green {{ background: var(--green); }}
    .amber {{ background: var(--amber); }}
    .blue {{ background: var(--blue); }}
    ul {{ margin: 10px 0 0; padding-left: 20px; line-height: 1.7; }}
    .actions {{ display:grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
    .action {{ border-left: 5px solid var(--green); padding: 12px 14px; background:#fffdf7; border-radius: 12px; }}
    .action.p1 {{ border-color: var(--red); }}
    @media (max-width: 900px) {{
      .scoreboard, .grid2, .actions {{ grid-template-columns: 1fr; }}
      header {{ padding: 24px; }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <header>
      <div><span class="pill">Weekly SEO Strategy</span><span class="pill risk">Validation: warning</span></div>
      <h1>SEO 週報：SHOPLINE</h1>
      <div class="meta">報告期間：2026-06-15 至 2026-06-21｜執行時間：2026-06-22 11:13 Asia/Taipei｜Run ID: seo_2026-06-15_2026-06-21_20260622T111335</div>
      <div class="scoreboard">
        <div class="metric"><b>11,191</b><span>GA4 Organic Search sessions</span></div>
        <div class="metric"><b>132</b><span>Organic keyEvents</span></div>
        <div class="metric"><b>98</b><span>Ahrefs Site Audit health score</span></div>
        <div class="metric"><b>5 / 12</b><span>P1 actions / total actions</span></div>
      </div>
    </header>

    <section class="grid2">
      <div class="card">
        <h2>本週結論</h2>
        <p><b>最大問題：</b>核心商業頁高曝光、排名佳，但 CTR 與 conversion 偏低，尤其 /about/pricing、/online-store/features、/faq/about。</p>
        <p><b>最大機會：</b>把「電商平台、D2C、POS、直播商務」做成 comparison + citation-ready cluster，承接搜尋與 AI 問答。</p>
        <p><b>最大風險：</b>AI citation 被 EasyStore、BVSHOP 與第三方比較文主導，SHOPLINE 自有內容對 AI 敘事控制不足。</p>
      </div>
      <div class="card">
        <h2>資料品質</h2>
        <ul>
          <li>GSC、GA4、Ahrefs、Workduo 可用；Google Drive 寫入完成。</li>
          <li>Screaming Frog wrapper 已確認 SEO Spider 24.1 licensed，但原生 MCP 本次回傳 IllegalStateException。</li>
          <li>技術 issue count 以 Ahrefs Site Audit fallback；Workduo citation freshness 有 warning。</li>
        </ul>
      </div>
      <div class="wide">
        {bar_chart("GSC CTR 機會：高曝光低 CTR 商業頁", gsc_ctr, "ctr", suffix="%")}
      </div>
      <div class="wide">
        {bar_chart("GA4 Organic landing sessions（商業頁 keyEvents 偏低）", ga4_sessions, "sessions", suffix="")}
      </div>
      <div class="wide">
        {grouped_competitor_chart(competitors)}
      </div>
      <div class="wide">
        {line_chart("Workduo AI Visibility by Platform", visibility_series, {"Google AI Overview": "#0F766E", "ChatGPT": "#D97706", "Gemini": "#2563EB"})}
      </div>
      <div class="wide">
        {bar_chart("Technical SEO issue distribution（Ahrefs fallback）", tech, "count", color="#B91C1C")}
      </div>
      <section class="card wide">
        <h2>Recommended Actions</h2>
        <div class="actions">
          <div class="action p1"><h3>P1 CTR sprint</h3><p>修 /pricing、features、FAQ、about、showcase 的 title/meta/FAQ schema。</p></div>
          <div class="action p1"><h3>P1 Comparison hub</h3><p>建立台灣電商平台比較頁，支援 AI citation 與非品牌商業查詢。</p></div>
          <div class="action p1"><h3>P1 Technical fixes</h3><p>修 structured data、compression、slow pages 三組模板問題。</p></div>
          <div class="action p1"><h3>P1 Conversion path</h3><p>檢查 pricing/payments CTA、表單與 GA4 key event mapping。</p></div>
          <div class="action p1"><h3>P1 Internal links</h3><p>從 hub 與高流量 blog 補 contextual links 到 position 4-20 商業頁。</p></div>
          <div class="action"><h3>P2 Content clusters</h3><p>D2C、POS、直播、團購等場景頁，支援 comparison hub。</p></div>
        </div>
      </section>
    </section>
  </main>
</body>
</html>
"""

OUT_FILE.write_text(html, encoding="utf-8")
print(OUT_FILE.resolve())
