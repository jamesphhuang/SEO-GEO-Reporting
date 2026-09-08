import json
import sqlite3
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent
e = json.loads((ROOT / 'evidence.json').read_text())
pages = json.loads((ROOT / 'pages.json').read_text())
stamp = e['retrievedAt']
title = 'SHOPLINE 台灣 SEO／GEO 月報｜2026 年 8 月'
datasets, blocks, charts, tables, cards, sources = {}, [], [], [], [], []

def source(id, label, path, definition, filters):
    sources.append({'id': id, 'label': label, 'path': path,
                    'query': {'description': definition, 'executed_at': stamp,
                              'filters': filters, 'tables_used': [path]}})

source('business', '正式業務來源｜2026 lead gen distribution',
       'https://docs.google.com/spreadsheets/d/1lfbDAu-YHBiRk9qOFUpKO7y2TFEmzDkaOxzuepJ6Ny8/edit#gid=1999633447',
       'Google Drive MCP get_spreadsheet_cells；讀取 A111:L120。Non-Paid Leads：7 月 C119、8 月 G119；Target：B119、F119。達成率 = Actual / Target，月增率 = August / July - 1。',
       ['TW；all_non_paid；原始數字儲存格；非 SEO 單一渠道', '來源時區 Asia/Shanghai；2026 年 7、8 月'])
source('gsc', 'Google Search Console MCP｜兩站台灣搜尋', 'evidence.json',
       'get_advanced_search_analytics；主站 https://shopline.tw/、部落格 sc-domain:blog.shopline.tw。dimensions=date，每月加總 clicks、impressions；CTR = sum(clicks)/sum(impressions)。平均排名依曝光加權，原始每日排名已四捨五入，僅為近似。',
       ['2026-07-01–07-31 與 2026-08-01–08-31；各 31 天', 'WEB；country=twn；data_state=final；row_limit=100；無分頁剩餘', 'GSC 日界以來源太平洋時間為準'])
for i, host in enumerate(['shopline.tw', 'blog.shopline.tw']):
    prop = ['257016301', '399614424'][i]
    source('ga'+str(i), 'GA4 MCP｜'+host, 'https://analytics.google.com/analytics/web/#/p'+prop,
           'run_report；dimensions=hostName,sessionDefaultChannelGroup；metrics=sessions,engagedSessions,totalUsers。hostname 精確比對、不分大小寫；取 Organic Search、AI Assistant。互動率 = engagedSessions/sessions；保留工作階段渠道歸屬。',
           ['2026 年 7、8 月；Asia/Taipei；未加 country 篩選，包含所有國家', '各 property 分開報告；不跨 property 加總', 'hostName 為事件主機診斷切分，不等同 landing-session 口徑'])
source('geo', 'Workduo MCP｜SHOPLINE 台灣專案', 'evidence.json',
       'get_metrics；projectId=cmp2adkpz000gw209tj6025jc；metric=all；dimension=entity；interval=daily。每日 visibility、sov 取等權算術平均；mentions 逐日加總。這是每日平均監測指標，不是整月去重或按回覆量加權的比率。',
       ['custom；2026 年 7、8 月；region=TW；onlyTrackedEntity=true', 'ignorePagination=true；pageSize=500；各 310 列、10 entities × 31 日；nextPageToken=null', '提示題目與平台組成尚未做固定樣本對齊；僅描述監測樣本，不能推論全市場'])
source('pages', 'Google Search Console MCP｜8 月頁面', 'pages.json',
       'get_advanced_search_analytics；dimensions=page；依 clicks 降序；row_limit=20。頁面 CTR = clicks/impressions；輸出 Top 20 作機會清單，不能用來推算全站總量或月降幅來源。',
       ['2026-08-01–08-31；WEB；country=twn；data_state=final', '主站與部落格各 Top 20；未取得 7 月逐頁對照'])

def md(id, text, src=None):
    b = {'id': id, 'type': 'markdown', 'body': text}
    if src: b['sourceId'] = src
    blocks.append(b)

def chart(id, name, subtitle, dataset, x, y, src, series=None, fmt='number'):
    enc = {'x': {'field': x, 'type': 'ordinal', 'label': '站點' if x=='siteLabel' else '月份'},
           'y': {'field': y, 'type': 'quantitative', 'label': '筆' if y=='leads' else ('%' if y=='visibilityPct' else '次'), 'format': fmt}}
    if series: enc['color'] = {'field': series, 'type': 'nominal', 'label': '系列'}
    charts.append({'id': id, 'title': name, 'subtitle': subtitle, 'headerMarkdown': name+'\n\n'+subtitle, 'type': 'bar',
                   'dataset': dataset, 'sourceId': src, 'encodings': enc})
    blocks.append({'id': id+'-block', 'type': 'chart', 'chartId': id})

def table(id, name, dataset, columns, src, sort):
    tables.append({'id': id, 'title': name, 'dataset': dataset, 'sourceId': src,
                   'columns': [{'field': f, 'label': l, 'format': fmt} for f,l,fmt in columns],
                   'defaultSort': {'field': sort, 'direction': 'desc'}})
    blocks.append({'id': id+'-block', 'type': 'table', 'tableId': id})

business_cells = e['business']['sheets'][0]['data'][0]['rowData'][8]['values']
july, august, target = [business_cells[i]['userEnteredValue']['numberValue'] for i in [2,6,5]]
assert (july, august, target) == (477,450,620)
datasets['business'] = [{'month': '7 月', 'series': 'Actual', 'leads': july},
                        {'month': '7 月', 'series': 'Target', 'leads': 537},
                        {'month': '8 月', 'series': 'Actual', 'leads': august},
                        {'month': '8 月', 'series': 'Target', 'leads': target}]
datasets['headline'] = [{'actual': august, 'target': target, 'attainment': august/target,
                         'mom': august/july-1, 'gap': target-august}]
cards.append({'id':'npl', 'dataset':'headline', 'sourceId':'business',
              'description':'全 Non-paid 業務名單；與 SEO、GEO 流量分開判讀。',
              'metrics':[{'label':'8 月 Non-paid Leads','field':'actual','format':'number'},
                         {'label':'目標','field':'target','format':'number'},
                         {'label':'達成率','field':'attainment','format':'percent'},
                         {'label':'較 7 月','field':'mom','format':'percent'}]})
md('title', '# '+title)
md('summary', '## Executive Summary\n\n- **Non-paid 名單未達標。** 8 月 450 筆，達成率 72.58%，較 7 月減少 5.66%，距目標 620 筆尚差 170 筆。\n- **自然搜尋量下降。** GA4 主站 Organic Search 工作階段較 7 月減少 10.83%，部落格減少 9.37%；GSC 台灣搜尋兩站曝光均下滑，CTR 則提高。\n- **AI 導流與品牌可見度不同步。** 主站 AI Assistant 工作階段成長 27.86%，但 Workduo SHOPLINE 每日平均可見度下降 6.60 個百分點。\n- **9 月優先恢復搜尋曝光，並查證轉換。** 先檢視重點頁面的查詢結構與搜尋結果，再追蹤導流品質；尚未確認的 SQL 與成功轉換不作成果宣稱。')
blocks.append({'id':'headlines','type':'metric-strip','cardIds':['npl']})
md('business-text', '## 名單缺口 170 筆，先以正式業務數據追蹤\n\n8 月 Non-paid Leads 為 **450 筆**，7 月為 **477 筆**，減少 27 筆；目標由 537 筆提高至 620 筆，達成率由 88.83% 降至 72.58%。目標提高與 Actual 下降共同擴大缺口。\n\n此指標涵蓋全部非付費渠道，不能直接視為 SEO 或 AI 帶來的名單，也不能將 GA4 工作階段當成此漏斗的分母。舊報表快照曾記為 347，本次 MCP 重讀正式來源 G119 為 450；差異原因未解，不覆寫歷史快照。', 'business')
chart('leads', 'Non-paid Leads：Actual 與 Target', '2026 年 7、8 月｜單位：筆；TW 全非付費渠道', 'business','month','leads','business','series')
md('scope', '## 閱讀範圍：搜尋、導流與業務成果分開衡量\n\n比較期間為 7 月 1–31 日與 8 月 1–31 日，兩者皆 31 天。GSC 限台灣 WEB 搜尋；GA4 依既有合約只限制主機，涵蓋所有國家，因此兩者不能逐筆對帳。GA4 主站與部落格使用不同 property，以下不跨 property 加總。\n\nGA4 sessions 是指定 hostname × session channel 的診斷切分；engagedSessions / sessions 為互動率。Workduo 指標限台灣監測專案，反映樣本中的品牌出現情況。')
datasets['search'] = []
for r in e['gscSummary']:
    datasets['search'].append({**r, 'siteLabel':'主站' if r['site'].startswith('https:') else '部落格', 'period':r['month']+' 月'})
md('search-text', '## 搜尋曝光收縮，CTR 上升尚未補回點擊\n\n主站台灣搜尋點擊由 9,146 降至 **8,283（−9.44%）**，曝光由 105,840 降至 **90,703（−14.30%）**；CTR 由 8.64% 升至 9.13%。部落格點擊由 11,453 降至 **10,989（−4.05%）**，曝光由 1,119,300 降至 **1,007,621（−9.98%）**；CTR 由 1.02% 升至 1.09%。\n\n兩站皆是曝光下降、CTR 上升。曝光加權近似排名也略有改善，尚不支持「全站排名全面惡化」的結論；搜尋需求、查詢組合與頁面能見度變化仍需拆解。這是月度比較，不代表已證實原因。', 'gsc')
chart('search-clicks','台灣搜尋點擊','2026 年 7、8 月｜WEB、country=twn；單位：次','search','siteLabel','clicks','gsc','period')
table('search-detail','搜尋明細（排名為近似值）','search', [('siteLabel','站點','text'),('period','月份','text'),('clicks','點擊','number'),('impressions','曝光','number'),('ctr','CTR','percent'),('position','平均排名≈','number')], 'gsc','clicks')
for i, host in enumerate(['shopline.tw','blog.shopline.tw']):
    data = e['ga4'][i]
    rows = []
    for r in data['rows']:
        h,ch,m = [d['value'] for d in r['dimension_values']]
        if ch not in ['Organic Search','AI Assistant']: continue
        sessions,engaged,users = [int(v['value']) for v in r['metric_values']]
        rows.append({'host':h,'channel':ch,'period':{'July':'7 月','August':'8 月'}[m],
                     'sessions':sessions,'engaged':engaged,'users':users,'engagementRate':engaged/sessions})
    datasets['ga'+str(i)] = rows
    texts = [
      '## 主站：自然搜尋減少，AI 流量規模仍小\n\nOrganic Search 工作階段由 **13,957 降至 12,446（−10.83%）**，互動率由 39.51% 升至 39.77%。AI Assistant 則由 **323 升至 413（+27.86%）**，互動工作階段由 135 升至 228，互動率由 41.80% 升至 55.21%。\n\nAI 工作階段增加 90，與自然搜尋減少 1,511 的規模有落差。應追蹤 AI 訪客的後續行為，但互動率提高不等於成功轉換增加。',
      '## 部落格：自然搜尋仍是主要流量來源\n\nOrganic Search 工作階段由 **17,139 降至 15,533（−9.37%）**，互動率由 44.87% 升至 46.52%。AI Assistant 由 **187 升至 208（+11.23%）**，互動率由 38.50% 降至 36.06%。\n\nAI 工作階段僅增加 21，且互動率未同步成長；內容工作優先支持搜尋需求與通往產品資訊的路徑，再觀察 AI 導流品質。兩站的 AI 品質走勢不同，不宜合併成一個「AI 成效成長」結論。']
    md('ga-text'+str(i),texts[i],'ga'+str(i))
    # Separate channels to avoid hiding the small AI series on an organic scale.
    for channel,suffix in [('Organic Search','organic'),('AI Assistant','ai')]:
        ds='ga'+str(i)+suffix
        datasets[ds] = [r for r in rows if r['channel']==channel]
        chart(ds,host+'｜'+channel+' 工作階段','2026 年 7、8 月｜所有國家；主機診斷口徑；單位：次',ds,'period','sessions','ga'+str(i))
    table('ga-table'+str(i),'渠道互動明細', 'ga'+str(i), [('channel','渠道','text'),('period','月份','text'),('sessions','工作階段','number'),('engaged','互動工作階段','number'),('engagementRate','互動率','percent')], 'ga'+str(i),'sessions')
geo = []
for month, payload in e['geo'].items():
    assert payload['nextPageToken'] is None
    for entity in sorted({r['dimensionValue'] for r in payload['data']}):
        rows = [r for r in payload['data'] if r['dimensionValue']==entity]
        assert len({r['date'] for r in rows}) == 31
        geo.append({'entity':entity,'period':month+' 月','days':31,
                    'visibility':mean(r['visibility'] for r in rows),
                    'sov':mean(r['sov'] for r in rows)})
datasets['geo'] = geo
datasets['geo-shopline'] = [r for r in geo if r['entity']=='SHOPLINE']
md('geo-text','## GEO：品牌可見度走弱，需回到固定題目檢查\n\nSHOPLINE 的 **每日平均可見度由 77.45% 降至 70.85%（−6.60 個百分點）**，每日平均 SOV 由 25.02% 降至 23.70%（−1.32 個百分點）。每月均取得 31 天、10 個實體的監測列。\n\n這裡對每天比率做等權平均，並非整月回覆量加權的可見度；來源未提供本次比率的底層分母，也未核對兩月提示題目、模型與平台是否完全相同。因此可描述監測數值下降，不能直接推論品牌在所有 AI 搜尋中的占比下降，更不能與 GA4 AI Assistant 導流畫上等號。','geo')
chart('geo-visibility','SHOPLINE 每日平均可見度','2026 年 7、8 月｜TW 監測樣本、每日等權平均；單位：%；非整月加權比率','geo-shopline','period','visibilityPct','geo')
table('geo-comparison','監測品牌比較｜每日等權平均','geo',[('entity','品牌','text'),('period','月份','text'),('visibility','每日平均可見度','percent'),('sov','每日平均 SOV','percent'),('days','天數','number')],'geo','visibility')
datasets['pages'] = [dict(r,site=site,ctr=r['clicks']/r['impressions']) for site,p in pages.items() for r in p['rows']]
md('page-text','## 優先檢視高曝光頁面的搜尋意圖\n\n部落格 Threads 行銷文章取得 **340,056 次曝光、1,088 次點擊，CTR 0.32%**；主站定價頁取得 **20,747 次曝光、319 次點擊，CTR 1.54%**。前者可檢查查詢意圖與摘要，後者可確認價格與方案資訊是否清楚對應搜尋需求。\n\n這是 8 月依點擊排序的 Top 20 頁面機會清單，沒有逐頁 7 月對照，不能宣称它們造成全站下滑。不同查詢、裝置與搜尋結果版位的 CTR 不宜直接套用同一基準；頁面曝光也不可加總後與 property 曝光對帳。','pages')
table('page-detail','8 月頁面機會清單｜各站 Top 20','pages',[('page','頁面 URL','text'),('clicks','點擊','number'),('impressions','曝光','number'),('ctr','CTR','percent')],'pages','clicks')
md('actions','## 9 月行動順序\n\n1. **先診斷搜尋曝光流失。** 建議 SEO 負責人於 9 月 11 日前，按頁面 × 查詢 × 裝置比較 7、8 月；拆分品牌與非品牌，找出曝光損失最大的組合，才決定修改內容或標題。\n2. **檢視重點頁面資訊。** 建議內容與產品行銷負責人於 9 月 18 日前檢查 Threads 行銷文與定價頁，確認資料時效、摘要及產品資訊路徑；完成後用相同查詢組追蹤曝光與 CTR。\n3. **固定 GEO 樣本。** 建議 GEO 負責人於 9 月 11 日前核對提示題目、平台、模型及成功回覆數，建立可比較的題目組，定位下降發生在哪些品牌比較題。\n4. **驗證成功轉換。** 建議分析與 Sales Ops 負責人釐清諮詢成功事件、跨網域與去重，再對帳正式名單；未確認前不以 CTA 點擊替代成功轉換。\n\n以上為建議時程與角色，尚未派工或承諾完成。')
md('questions','## 尚待釐清的問題\n\n- 曝光下降主要來自需求減少、查詢組合變化，或特定頁面流失？目前總量只能縮小方向。\n- GEO 兩月是否使用相同提示題目與平台組合？需固定樣本後再解讀月變化。\n- Non-paid Leads 450 與舊快照 347 的差異何時產生？目前無法判定為延遲修正或舊快照錯誤。\n- 正式 SQL 與成功轉換的來源、範圍及成熟規則何時能完成確認？')
md('caveats','## 資料限制與假設\n\n本報表為 2026 年 9 月 6 日擷取的 8 月最新來源快照，不代表 8 月 31 日當時凍結的數字。SQL 與成功轉換依既有資料合約維持未確認，不顯示推測值。未納入 Ahrefs 估算流量或當月 Screaming Frog 技術稽核，故本報表不判斷技術問題是否於 8 月修復。\n\nGA4 回傳無抽樣 metadata、data_loss_from_other_row=false；這不等同保證事件埋設、同意模式或渠道歸因完整。GSC 各月均有 31 天最終資料，CTR 以總點擊除以總曝光重新計算，未平均每日 CTR。\n\n月增率 = 8 月值 / 7 月值 − 1；比率變化以百分點表示。沒有因果實驗或跨渠道名單歸因，因此流量變化不能視為名單差異的已證實原因。')
# SQL derives reviewed datasets directly from the MCP response snapshot.
db = sqlite3.connect(':memory:')
db.row_factory = sqlite3.Row
db.execute('CREATE TABLE mcp_evidence (payload TEXT)')
db.execute('INSERT INTO mcp_evidence VALUES (?)', (json.dumps(e),))
db.execute('CREATE TABLE mcp_pages (payload TEXT)')
db.execute('INSERT INTO mcp_pages VALUES (?)', (json.dumps(pages),))
queries = {
 'business': '''WITH cells AS (
 SELECT json_extract(payload, '$.business.sheets[0].data[0].rowData[8].values[6].userEnteredValue.numberValue') AS actual,
 json_extract(payload, '$.business.sheets[0].data[0].rowData[8].values[5].userEnteredValue.numberValue') AS target,
 json_extract(payload, '$.business.sheets[0].data[0].rowData[8].values[2].userEnteredValue.numberValue') AS prior
 FROM mcp_evidence)
 SELECT actual, target, 1.0*actual/target AS attainment, 1.0*actual/prior-1 AS mom, target-actual AS gap FROM cells''',
 'gsc': '''SELECT site.key AS sourceKey,
 CASE WHEN json_extract(site.value,'$.site_url') LIKE 'https:%' THEN '主站' ELSE '部落格' END AS siteLabel,
 substr(json_extract(site.value,'$.date_range.start'),6,2)||' 月' AS period,
 SUM(json_extract(day.value,'$.clicks')) AS clicks,
 SUM(json_extract(day.value,'$.impressions')) AS impressions,
 1.0*SUM(json_extract(day.value,'$.clicks'))/SUM(json_extract(day.value,'$.impressions')) AS ctr,
 SUM(json_extract(day.value,'$.position')*json_extract(day.value,'$.impressions'))/SUM(json_extract(day.value,'$.impressions')) AS position
 FROM mcp_evidence, json_each(payload,'$.gsc') site, json_each(site.value,'$.rows') day GROUP BY site.key''',
 'geo': '''SELECT json_extract(day.value,'$.dimensionValue') AS entity, month.key||' 月' AS period,
 COUNT(DISTINCT json_extract(day.value,'$.date')) AS days,
 AVG(json_extract(day.value,'$.visibility')) AS visibility, AVG(json_extract(day.value,'$.sov')) AS sov
 FROM mcp_evidence, json_each(payload,'$.geo') month, json_each(month.value,'$.data') day
 GROUP BY month.key, entity''',
 'pages': '''SELECT site.key AS site, json_extract(page.value,'$.page') AS page,
 json_extract(page.value,'$.clicks') AS clicks, json_extract(page.value,'$.impressions') AS impressions,
 1.0*json_extract(page.value,'$.clicks')/json_extract(page.value,'$.impressions') AS ctr
 FROM mcp_pages, json_each(payload) site, json_each(site.value,'$.rows') page'''
}
for i in range(2):
    queries['ga'+str(i)] = f'''SELECT json_extract(r.value,'$.dimension_values[0].value') AS host,
 json_extract(r.value,'$.dimension_values[1].value') AS channel,
 CASE json_extract(r.value,'$.dimension_values[2].value') WHEN 'July' THEN '7 月' ELSE '8 月' END AS period,
 CAST(json_extract(r.value,'$.metric_values[0].value') AS INTEGER) AS sessions,
 CAST(json_extract(r.value,'$.metric_values[1].value') AS INTEGER) AS engaged,
 CAST(json_extract(r.value,'$.metric_values[2].value') AS INTEGER) AS users,
 1.0*json_extract(r.value,'$.metric_values[1].value')/json_extract(r.value,'$.metric_values[0].value') AS engagementRate
 FROM mcp_evidence, json_each(payload,'$.ga4[{i}].rows') r
 WHERE json_extract(r.value,'$.dimension_values[1].value') IN ('Organic Search','AI Assistant')'''
for s in sources:
    sql = queries[s['id']]
    result = [dict(row) for row in db.execute(sql)]
    ds = {'business':'headline','gsc':'search'}.get(s['id'],s['id'])
    datasets[ds] = result
    s['query'].update({'sql':sql,'engine':'SQLite JSON1','language':'sql',
                       'tables_used':['mcp_pages' if s['id']=='pages' else 'mcp_evidence']})
    (ROOT/(s['id']+'.sql')).write_text(sql+';\n')
for i in range(2):
    for ch,suffix in [('Organic Search','organic'),('AI Assistant','ai')]:
        datasets['ga'+str(i)+suffix] = sorted([r for r in datasets['ga'+str(i)] if r['channel']==ch],key=lambda r:r['period'])
datasets['geo-shopline'] = [{**r,'visibilityPct':100*r['visibility']} for r in datasets['geo'] if r['entity']=='SHOPLINE']
for b in blocks:
    if 'body' in b: b['body'] = b['body'].replace('宣称','宣稱')
artifact = {'surface':'report','manifest':{'version':1,'surface':'report','title':title,
             'description':'2026 年 8 月對 7 月｜正式業務成果、搜尋表現、AI 導流與品牌監測',
             'generatedAt':stamp,'blocks':blocks,'cards':cards,'charts':charts,'tables':tables,'sources':sources},
            'snapshot':{'version':1,'generatedAt':stamp,'status':'partial','datasets':datasets,
                        'accessIssues':[{'id':'business-definition','message':'SQL 與成功轉換的正式來源／口徑尚未確認；本期不提供這兩項成果。'}]},
            'sources':sources}
(ROOT/'artifact.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2))
print(f'Wrote artifact.json: {len(blocks)} blocks, {len(charts)} charts, {len(tables)} tables')
