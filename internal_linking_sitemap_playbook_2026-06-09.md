# SHOPLINE 內鏈與 Sitemap 補強 Playbook

期間：`2026-06-09`  
對應週報：`SEO 週報｜SHOPLINE｜2026-06-01 至 2026-06-07`

## 先講結論

這題不要當成「38 頁全部平均補 1-2 個連結」來做。  
正確做法是先把 `5 個 sitemap 缺頁` 與 `高商業/高策略價值的弱內鏈頁` 補進核心導流鏈，讓 Google 能更快理解：

1. 這些頁面存在
2. 這些頁面和哪些商業主題強相關
3. 哪些頁是 hub，哪些頁是 supporting page

這次優先順序應該是：

1. `/ai`
2. `/online-store/shop-builder-crowdfunding`
3. `/payments` 與 payments 相關 news
4. `/corp-social-responsibility`
5. 其他 news / CSR / campaign 類弱內鏈頁

## 這題的目標

不是單純多幾條連結，而是同時完成三件事：

1. 補 crawl path：讓弱內鏈頁從首頁、商業頁、hub page 都能被順著點到
2. 補 topic relevance：讓 anchor text 與上下文告訴搜尋引擎「這頁在講什麼」
3. 補 sitemap coverage：讓 indexable 頁不要只靠內鏈被發現

## 先處理的 5 個 sitemap 缺頁

根據這輪 Ahrefs Site Audit，至少先補這 5 頁：

1. `https://shopline.tw/ai`
2. `https://shopline.tw/corp-social-responsibility`
3. `https://shopline.tw/news/shopline-cashback`
4. `https://shopline.tw/news/shopline-payments-mpi`
5. `https://shopline.tw/online-store/shop-builder-crowdfunding`

## 執行順序

### Phase 1：先修 sitemap

先把上面 5 頁加入 XML sitemap。

原則：

1. 只放 canonical、indexable、200 的正式 URL
2. 不要放 `//` 雙斜線版本
3. 若有 hreflang sitemap，也要同步確認對應語系 URL 是 canonical
4. 更新後重新提交到 GSC sitemap

驗收：

1. GSC 可讀取 sitemap
2. Ahrefs 下輪 crawl 不再報 `indexable page not in sitemap`
3. sitemap 中的 URL 與 canonical 完全一致

### Phase 2：先補 4 條主幹內鏈

不要一開始到處塞 link。先補最有權重的來源頁：

1. 首頁 `/`
2. pricing `/about/pricing`
3. solutions hub `/solutions` 或同級 solution landing pages
4. feature / showcase / FAQ 類高曝光頁

原因：

1. 這些頁本來就有 crawl 頻率與權重
2. 從這些頁導出去，對弱頁的訊號最直接
3. 也最符合使用者旅程，不會像硬塞 footer links

### Phase 3：再補同主題 supporting links

等主幹補完，再做頁群內互連：

1. AI 主題頁互連
2. payments / logistics / FAQ 主題頁互連
3. news 與對應商業頁互連
4. crowdfunding 與開店功能/促購功能頁互連

## 目標頁逐頁怎麼補

### 1. `/ai`

目標：

1. 提升 AI / MCP / 零售 AI 主題權重
2. 讓 `/ai` 不只是孤立活動頁，而是 AI solution hub

優先加連結的來源頁：

1. `/`
2. `/about/pricing`
3. `/solutions/omo`
4. `/shopper-app`
5. `/online-store/features`
6. `/about/press`

建議 anchor：

1. `AI 賦能零售`
2. `AI 開店與營運解決方案`
3. `零售 AI 應用`
4. `AI 商品文案與營運自動化`

文案位置：

1. 首頁 solution 區塊新增一格 AI / automation
2. pricing 頁在模組/加值能力段落連到 AI 頁
3. OMO / shopper-app 頁在提升營運效率段落連到 AI 頁
4. about/press 頁把 AI 相關新聞導回 `/ai`

不要做的事：

1. 全站統一用 `了解更多`
2. 在 footer 一次塞 10 條 AI 連結
3. 只從 press/news 導向 `/ai`，卻沒有商業頁導向

### 2. `/online-store/shop-builder-crowdfunding`

目標：

1. 把眾籌頁跟開店功能主題連上
2. 讓它不是單篇 campaign landing page，而是促購功能群的一部分

優先加連結的來源頁：

1. `/online-store/shop-builder`
2. `/online-store/features`
3. `/group-buying`
4. `/online-store-setup`
5. `/showcase`

建議 anchor：

1. `募資頁功能`
2. `新品預購與眾籌頁面`
3. `SHOP Builder 募資應用`
4. `募資活動頁設計`

文案位置：

1. shop-builder 頁的功能延伸模組區
2. features 頁的促購 / campaign / landing page 模組區
3. group-buying 頁的延伸使用情境區

### 3. `/payments` 與 payments 相關 news

包含：

1. `/payments`
2. `/faq/payments-and-shipping`
3. `/news/shopline-payments-mpi`
4. `/news/shopline-payments-aftee`

目標：

1. 把 payment capability 跟 payment proof 串起來
2. 讓 news 不只是 press release，而是商業信任資產

優先加連結的來源頁：

1. `/about/pricing`
2. `/faq/overview`
3. `/payments`
4. `/logistics`
5. `/online-store/features`

建議 anchor：

1. `支付與金流整合`
2. `跨境支付能力`
3. `SHOPLINE Payments`
4. `金物流服務`
5. `新加坡 MPI 執照`

做法：

1. 在 `/payments` 頁新增「相關認證 / 最新支付能力更新」區塊，連回 MPI / AFTEE news
2. 在 `/faq/payments-and-shipping` 補回 `/payments` 主頁與關鍵 news
3. pricing 頁的金流模組段落導向 `/payments`
4. news 頁面正文或延伸閱讀，反向導回 `/payments` 與 FAQ

這一組很重要，因為它同時補：

1. 商業信任
2. 產品能力
3. 搜尋意圖閉環

### 4. `/corp-social-responsibility`

目標：

1. 讓 CSR 頁不是孤立品牌頁
2. 補品牌信任與企業敘事的內鏈脈絡

優先加連結的來源頁：

1. `/about`
2. `/about/press`
3. `/selectedpartners`
4. `/cooperate`

建議 anchor：

1. `企業社會責任`
2. `永續與社會參與`
3. `SHOPLINE CSR`

做法：

1. `/about` 增加品牌責任 / company values 區塊導向 CSR
2. `/about/press` 放入企業里程碑 / CSR 相關導覽
3. 若 partner / cooperate 頁有品牌信任段落，也可帶一條

### 5. `/news/shopline-cashback`

目標：

1. 把 press/news 與商業功能頁接起來
2. 讓這頁不只是新聞，而是「流量返利 / 轉單」的應用證據

優先加連結的來源頁：

1. `/payments`
2. `/solutions/traffic-and-conversion`
3. `/about/press`
4. `/showcase`

建議 anchor：

1. `流量返利合作`
2. `轉單成效解決方案`
3. `CashBack 合作案例`

## 來源頁怎麼安排比較自然

最重要原則：把 link 放在本來就應該出現這個概念的段落，不要做成「相關文章機器區塊」。

建議版位：

1. Hero 下方的 proof / feature / scenario 區塊
2. FAQ 區塊答案內文
3. 延伸閱讀區塊，但要按主題分組
4. 案例 / capability / module 區塊

不建議：

1. 所有頁都加同一組 sitewide links
2. 每段都插錨文字，造成過度最佳化
3. 只從 press/news 互連，沒有主商業頁導流

## Anchor text 規則

用這三種比例來控：

1. `60%` 描述型 anchor
2. `30%` 品牌 + 主題 anchor
3. `10%` 泛用 anchor

例子：

好：

1. `了解 SHOPLINE AI 如何提升零售營運效率`
2. `查看 SHOPLINE Payments 的跨境支付能力`
3. `認識新品預購與募資頁功能`

不好：

1. `點這裡`
2. `更多`
3. `了解更多`
4. 同一頁出現三次完全一樣的 `SHOPLINE AI`

## 跟 sitemap 一起要順手檢查的東西

因為前面已有 `//`、hreflang、canonical 歷史問題，這次補內鏈時一起檢查：

1. 內鏈是否全部指向單斜線 canonical URL
2. 目標頁 canonical 是否自指
3. hreflang 是否指向 canonical URL，不是 `//` 版本
4. sitemap 是否收錄同一個 canonical URL

如果不一起看，會出現：

1. 你加了 link，但指到錯的 URL 版本
2. sitemap 有頁，但 canonical 指到別處
3. hreflang 還在送錯訊號

## 兩週內的實際排程

### 第 1 週

1. 補 sitemap 的 5 頁
2. 補首頁、pricing、solutions、features 的主幹內鏈
3. 先完成 `/ai`、`/payments`、`/online-store/shop-builder-crowdfunding`

### 第 2 週

1. 補 CSR 與 news 反向導流
2. 補 FAQ / showcase / press 的 supporting links
3. 清查是否還有 `one dofollow incoming internal link` 的頁面仍在清單中

## 驗收方式

你做完後，不要只看「有沒有上線」，要看這 5 個驗收點：

1. sitemap 缺頁是否從 `5 -> 0`
2. `/ai`、crowdfunding、payments/news 頁的 incoming internal link 數量是否增加
3. 這些頁是否開始出現在 crawl path / internal link reports
4. 下輪 crawl 的 `one dofollow incoming internal link` 數是否下降
5. 2-4 週內，這些頁的 impressions / clicks / indexed status 是否改善

## 最後的判斷標準

這題做得好，不是因為你加了很多連結。  
而是因為你把弱頁接回：

1. 商業主題鏈
2. 品牌信任鏈
3. 功能與證據鏈

如果你要最務實地開始，今天先做這 3 件事：

1. 把 5 個缺頁補進 sitemap
2. 從首頁與 `/about/pricing` 補到 `/ai`、`/payments`、`/online-store/shop-builder-crowdfunding`
3. 把 `/news/shopline-payments-mpi`、`/news/shopline-cashback` 反向連回對應商業主頁
