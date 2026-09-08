"""Turn a Screaming Frog "Crawl Overview" export into a curated technical-audit table.

The overview lists every filter Screaming Frog tracks, including many that are healthy
states or known false positives. CATALOGUE is the explicit allow-list of findings worth
putting in a monthly report; EXCLUDED records what was deliberately left out and why, so
the omissions are auditable rather than silent.
"""

import csv
from pathlib import Path

HIGH, MEDIUM, LOW = "高", "中", "低"

# (section, Screaming Frog label, report label, severity, what it means)
CATALOGUE = [
    ("H1", "Missing", "缺少 H1", HIGH,
     "內容頁沒有 H1，主題訊號完全缺失，是本次最值得優先處理的項目。"),
    ("Response Codes", "Internal Redirection (3xx)", "內部連結指向轉址", HIGH,
     "站內連結指到會轉址的網址，浪費爬取預算並稀釋連結權重；應直接改指最終網址。"),
    ("Images", "Over 100 kB", "圖片超過 100 kB", HIGH,
     "大圖直接影響 LCP 與 Core Web Vitals，是可量化的載入速度負擔。"),
    ("Images", "Missing Alt Text", "圖片缺少 alt 文字", MEDIUM,
     "影響無障礙與圖片搜尋能見度。"),
    ("Canonicals", "Non-Indexable Canonical", "canonical 指向不可索引網址", MEDIUM,
     "canonical 指到 noindex 或非 200 的網址，Google 可能忽略該指示或整批不收錄。"),
    ("Canonicals", "Canonicalised", "頁面被 canonical 指到別處", MEDIUM,
     "這些頁面主動放棄自己的索引資格；需確認是刻意去重還是設定錯誤。"),
    ("Page Titles", "Over 561 Pixels", "標題在搜尋結果會被截斷", MEDIUM,
     "超過 561 像素，SERP 顯示會被截掉，影響點閱。與本月 CTR 議題直接相關。"),
    ("Meta Description", "Over 985 Pixels", "描述在搜尋結果會被截斷", MEDIUM,
     "超過 985 像素會被截斷或改由 Google 自行擷取。"),
    ("Response Codes", "External Client Error (4xx)", "連外死連結 4xx", MEDIUM,
     "站上連出去的網址已失效，影響使用者體驗；非站內頁面本身的錯誤。"),
    ("H1", "Duplicate", "H1 重複", MEDIUM,
     "多頁共用相同 H1，主題區隔不明確。"),
    ("H1", "Multiple", "單頁多個 H1", MEDIUM,
     "單頁出現多個 H1，標題層級的主題訊號被分散。"),
    ("Hreflang", "Missing X-Default", "缺少 x-default hreflang", MEDIUM,
     "多語系站台未指定 x-default，未匹配到語系的使用者沒有 fallback 版本。"),
    ("Response Codes", "External Server Error (5xx)", "連外 5xx", LOW,
     "外部網址回傳伺服器錯誤，可能是對方暫時故障，建議複查後再決定是否移除。"),
    ("Page Titles", "Same as H1", "標題與 H1 完全相同", LOW,
     "不是錯誤，但標題與 H1 可分別針對搜尋意圖與版面閱讀優化。"),
    ("Meta Description", "Duplicate", "描述重複", LOW,
     "多頁共用相同描述，Google 較可能改為自行擷取。"),
    ("Page Titles", "Duplicate", "標題重複", LOW,
     "多頁共用相同標題，彼此競爭同一組查詢。"),
    ("H2", "Duplicate", "H2 重複", LOW,
     "多數由版型固定區塊造成，優先度低。"),
    ("Security", "Missing HSTS Header", "缺少 HSTS 標頭", LOW,
     "安全性標頭，對排名影響有限，屬基礎設定建議。"),
    ("Security", "Missing Content-Security-Policy Header", "缺少 CSP 標頭", LOW,
     "安全性標頭，對排名影響有限。"),
    ("Security", "Unsafe Cross-Origin Links", "不安全的跨來源連結", LOW,
     "target=_blank 未搭配 rel=noopener，屬安全性建議。"),
    ("Content", "Low Content Pages", "低內容頁面", LOW,
     "內容量偏少的頁面，需人工判斷是否為功能頁。"),
]

# Deliberately not reported, with the reason, so the exclusions are reviewable.
EXCLUDED = [
    ("Meta Keywords: Missing", "Google 不使用 meta keywords，缺少不是問題。"),
    ("Canonicals: Self Referencing / Contains Canonical", "自我參照 canonical 是正確狀態，非缺陷。"),
    ("H1 / H2: Non-Sequential", "多為版型標籤順序造成，實務上極少影響搜尋表現。"),
    ("Page Titles / Meta Description: Below N Characters", "長度偏短不必然是問題，需看查詢意圖，不列為缺陷。"),
    ("URL: Non ASCII Characters", "中文網址為刻意設計，非錯誤。"),
    ("Security: HTTPS URLs", "全站 100% HTTPS，屬健康狀態。"),
]


def parse_overview(path):
    """Read a crawl_overview.csv into {meta, sections{section:{label:{count,share,total,totalDesc}}}}."""
    rows = list(csv.reader(Path(path).open(encoding="utf-8-sig")))
    meta, sections, section = {}, {}, None
    for row in rows:
        if not row or not row[0]:
            continue
        if len(row) == 1:
            section = row[0]
            sections.setdefault(section, {})
            continue
        label, value = row[0], row[1]
        if len(row) == 2:
            meta[label] = value
            continue
        try:
            count = int(str(value).replace(",", ""))
        except ValueError:
            continue
        share = None
        if len(row) > 2 and str(row[2]).endswith("%"):
            share = float(str(row[2]).rstrip("%")) / 100
        entry = {"count": count, "share": share,
                 "total": row[3] if len(row) > 3 else None,
                 "totalDesc": row[4] if len(row) > 4 else None}
        target = sections.setdefault(section, {}) if section else meta.setdefault("_summary", {})
        target[label] = entry
    return {"meta": meta, "sections": sections}


SEVERITY_ORDER = {HIGH: 0, MEDIUM: 1, LOW: 2}


def audit_rows(site_label, parsed):
    """Apply CATALOGUE to one parsed overview, keeping only non-zero findings."""
    rows = []
    for section, sf_label, label, severity, note in CATALOGUE:
        entry = parsed["sections"].get(section, {}).get(sf_label)
        if not entry or not entry["count"]:
            continue
        rows.append({"siteLabel": site_label, "severity": severity, "issue": label,
                     "count": entry["count"], "share": entry["share"],
                     "scope": entry["totalDesc"], "note": note})
    rows.sort(key=lambda r: (SEVERITY_ORDER[r["severity"]], -r["count"]))
    return rows


def crawl_meta(site_label, parsed):
    meta = parsed["meta"]
    summary = meta.get("_summary", {})
    return {"siteLabel": site_label,
            "siteCrawled": meta.get("Site Crawled"),
            "crawlDate": (meta.get("Last Modified Date", "") + " " + meta.get("Last Modified Time", "")).strip(),
            "elapsed": meta.get("Elapsed"),
            "urlsEncountered": summary.get("Total URLs Encountered", {}).get("count"),
            "urlsCrawled": summary.get("Total URLs Crawled", {}).get("count"),
            "internalUrls": summary.get("Total Internal URLs", {}).get("count"),
            "internalIndexable": summary.get("Total Internal Indexable URLs", {}).get("count"),
            "internalNonIndexable": summary.get("Total Internal Non-Indexable URLs", {}).get("count")}
