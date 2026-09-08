"""Core Web Vitals field data: metric catalogue, Google's thresholds and rating logic.

Core Web Vitals are a field measurement — Google assesses an origin on the 75th
percentile of real Chrome users over a rolling 28-day window, not on a lab run — so the
source that matches how Search Console reports them is the Chrome UX Report (CrUX),
which is what Search Console's own Core Web Vitals report is built from. The Search
Console API does not expose that report, so the report pulls CrUX directly.

Both pull_cwv.py and build_report_data.py import this, so the thresholds and the
good/needs-improvement/poor boundaries are defined exactly once.
"""

ORIGINS = [
    ("https://shopline.tw", "主站 shopline.tw"),
    ("https://blog.shopline.tw", "部落格 blog.shopline.tw"),
]

# Google assesses each form factor separately, and Search Console splits its Core Web
# Vitals report the same way, so the report never merges the two.
FORM_FACTORS = [("PHONE", "行動裝置"), ("DESKTOP", "電腦")]

GOOD, NEEDS, POOR = "良好", "需改善", "不佳"
RATING_ORDER = {POOR: 0, NEEDS: 1, GOOD: 2}

# (CrUX metric id, report label, short label, display unit, good boundary, poor boundary, is a Core Web Vital)
# Boundaries are Google's published thresholds in the metric's raw unit — milliseconds for
# everything except CLS — and good is <= the first, poor is > the second. The display unit
# travels with the row so the renderer formats seconds, milliseconds and the unitless CLS
# score correctly without knowing any metric by name.
METRICS = [
    ("largest_contentful_paint", "LCP 最大內容繪製", "LCP", "s", 2500, 4000, True),
    ("interaction_to_next_paint", "INP 互動到下次繪製", "INP", "ms", 200, 500, True),
    ("cumulative_layout_shift", "CLS 累積版面位移", "CLS", "score", 0.1, 0.25, True),
    ("first_contentful_paint", "FCP 首次內容繪製", "FCP", "s", 1800, 3000, False),
    ("experimental_time_to_first_byte", "TTFB 首位元組時間", "TTFB", "ms", 800, 1800, False),
]
BY_ID = {m[0]: m for m in METRICS}
CORE_IDS = [m[0] for m in METRICS if m[6]]

# CrUX returns numbers for millisecond metrics and decimal strings for CLS.
def value(raw):
    if raw is None or raw == "":
        return None
    return float(raw)


def rate(metric_id, p75):
    """Google's three-way assessment for one metric's 75th percentile."""
    if p75 is None or metric_id not in BY_ID:
        return None
    _, _, _, _, good, poor, _ = BY_ID[metric_id]
    if p75 <= good:
        return GOOD
    return NEEDS if p75 <= poor else POOR


def histogram(metric):
    """The three density bins CrUX reports, in good / needs-improvement / poor order."""
    bins = metric.get("histogram") or []
    densities = [b.get("density") for b in bins]
    densities += [None] * (3 - len(densities))
    return densities[:3]


def overall(ratings):
    """An origin passes Core Web Vitals only when all three vitals are rated good."""
    present = [r for r in ratings if r]
    if len(present) < len(CORE_IDS):
        return "資料不足"
    return "通過" if all(r == GOOD for r in present) else "未通過"
