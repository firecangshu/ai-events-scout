# GitHub 免 API 广覆盖搜索引擎调研

> 调研时间：2026-11-19  
> 用户目标：找**不需要接搜索服务商 API key**、覆盖范围广、带新算法/新技巧的开源项目，用于增强「AI赛事百晓生」聚合搜索层。  
> 口径说明：这里的「免 API」指**不需要向 Google/Bing/Tavily/Brave 等申请 key、不按次付费**；但部分项目仍需要 Docker / Chromium / 本地登录 / 自建服务。凡是需要登录或浏览器的，已在表中标注。

---

## 一、结论先行

有，而且不少。按用途分成四类：

| 目标 | 首选 | 理由 |
|---|---|---|
| 直接替代付费搜索 API | **FreeSearch API** | MIT、无 key、RRF 融合、熔断、curl_cffi 指纹、REST/MCP/CLI、还能伪装成 Tavily/Serper/Brave/SearXNG 端点 |
| 最广中文/社交长尾覆盖 | **Agent Reach** | 113k stars、MIT、15+ 渠道、默认渠道零 key、只读、有序 fallback |
| 最深多源研究 | **AutoSearch** | 40 渠道、27 个开箱不用配置、MCP-native、LLM 解耦、MIT |
| 最新反爬/重排技巧 | **DonSeTch** | Rust 单文件、10+ keyless 后端、真实 Chrome TLS、solve-and-bounce、本地 ONNX 语义重排、跨引擎共识 |

稳妥底座仍是 **SearXNG**（39.7k stars，70+ 引擎，AGPL）；轻量包装可选 **ask-search** 和 **one-search-mcp**。

---

## 二、候选项目总表

| 项目 | 仓库 | Stars / 活跃度 | License | 真·免 key | 覆盖范围 | 新算法/新技巧 | 集成建议 |
|---|---|---:|---|---|---|---|---|
| **Agent Reach** | `Panniantong/Agent-Reach` | 113,163 stars / 10,156 forks / 2026-11-08 push | MIT | 默认渠道零 key；部分可选渠道要登录或 Groq key | B站、V2EX、GitHub、YouTube、web；可选小红书、雪球、Boss、LinkedIn、Reddit、X、FB、IG、播客 | 每个渠道 = **首选 + 备选的有序工具列表**；只读；专用浏览器复用单站登录 | 强烈建议接入，补中文/社交长尾 |
| **SearXNG** | `searxng/searxng` | 39,698 stars / 3,622 forks / 2026-11-19 push | AGPL-3.0 | 是，自建即可 | 70+ 搜索服务，通用/新闻/图片/视频/科技/学术 | 匿名代理、引擎权重、JSON 输出、可配 RRF | 作为稳定底座或上游引擎 |
| **AutoSearch** | `0xmariowu/Autosearch` | 56 stars / 12 forks / 2026-11-13 push | MIT | 27/27 always-on 渠道零配置；另有 API-key/login 渠道 | 40 渠道：arXiv、PubMed/OpenAlex/DBLP、GitHub、DDG、HN、Reddit、HF、StackOverflow、Google News、Wikipedia、公众号、36kr、InfoQ、Linux DO 等 | **MCP-native + LLM 解耦**；多源并行、去重排序、每条带 source URL；社区资料提到自 evolve/渠道评分 | 作为 deep research 模式 |
| **FreeSearch API** | `Ethos6/free-search-api` | 4 stars / 2026-11-01 push | MIT | 是，完全无 key | DDG、Brave、Bing、Yahoo、Wikipedia、Bing/Google News RSS、可接自有 SearXNG | **RRF 融合 + 每引擎熔断 + curl_cffi TLS 指纹 + 代理轮换 + trafilatura 正文抽取 + 兼容 Tavily/Serper/Brave/SearXNG 端点** | 最值得做上游引擎，但 star 少，先小流量试点 |
| **DonSeTch** | `dondai44423/donsetch` | 1,110 stars / 2026-11-19 push | AGPL-3.0 | 是，10+ keyless 后端；BYOK 可选 | Brave、Bing、DDG、Mojeek、Yandex、Startpage + GitHub/Wikipedia/HN/Semantic Scholar/arXiv/StackExchange/MDN/Google News | **真实 Chrome TLS（BoringSSL）+ solve-and-bounce + 自改进抓取 + 本地 ONNX cross-encoder 重排 + 跨引擎共识** | 技术最激进；注意 AGPL 与 ToS，先观察/隔离试用 |
| **ask-search** | `ythx-101/ask-search` | 539 stars / 46 forks / 2026-11-12 push | MIT | 是，包装 SearXNG，默认零 key | SearXNG 背后的 70+ 源 | CLI + MCP + OpenClaw skill；`--urls-only` 便于接 web_fetch | 快速接入 SearXNG 的轻量壳 |
| **one-search-mcp** | `dckthulhu/one-search-mcp` | 低 star / 2026-02-03 push | MIT | `local` 与 `duckduckgo` 免 key；其他 provider 需 key | local browser（Bing/Google/Baidu/Sogou）+ SearXNG/DDG 等 | 用本地 Chromium 替代 Firecrawl，`one_search/one_scrape/one_map/one_extract` | 需要 Chromium，适合做浏览器兜底 |
| **free-ai-search** | `HeavenFYouMissed/free-ai-search` | 低 star / 2026-04-02 push | MIT | 是，SearXNG + Redis | SearXNG 聚合源 | Redis 缓存 + 每用户配额，面向 AI Agent | 参考架构，不建议直接依赖 |

---

## 三、逐个项目要点

### 1. Agent Reach — 覆盖面最猛

- 默认渠道：`bilibili`、`v2ex`、`github`、`youtube`、`web`，零 key。
- 可选渠道：小红书、雪球、Boss直聘、小宇宙、LinkedIn、Reddit、X、Facebook、Instagram。
- 实验渠道反爬更严，可能失效。
- 关键设计：**每个平台/动作 = 有序工具列表**，首选失败自动换备选；这让平台改版时不用改 Agent 用法。
- 安全：只读；不替用户登录、不要密码；复用单站登录；建议小号。
- 适合我们：补小红书、B站、V2EX、雪球、Reddit、X 等通用搜索覆盖差的中文/社交长尾。

### 2. SearXNG — 最稳的元搜索底座

- 70+ 引擎聚合，匿名化查询，JSON 输出。
- AGPL-3.0：如果我们的程序要闭源分发，要评估合规；内部自用/自建一般可接受。
- 缺点：JSON API 默认不开放，需要改 `settings.yml`；自建需要 Docker/资源。
- 适合我们：作为 `multi_search` 的稳定替代或上游之一，而不是唯一入口。

### 3. AutoSearch — 多源深度研究

- 40 个渠道，27 个开箱可用、无需 key。
- 学术：arXiv、PubMed、OpenAlex、DBLP、Semantic Scholar（部分）。
- 中文：公众号、36kr、InfoQ、Linux DO、知乎/微博/抖音等部分需 `TIKHUB_API_KEY` 或登录。
- MCP-native、LLM 解耦：返回索引后的多源结果，不绑定具体 LLM。
- 适合我们：作为 `--mode deep` 的独立深度研究引擎。

### 4. FreeSearch API — 最像「免费 Tavily」

- 无 key、无限额（软件层面），REST / MCP / CLI / Python library 四种用法。
- 并行查询 DDG、Brave、Bing、Yahoo、Wikipedia、新闻 RSS。
- **RRF（Reciprocal Rank Fusion）**：多个引擎都排前面的结果优先；天然尺度无关，比简单加权平均稳。
- 每引擎 **circuit breaker**：被限流/CAPTCHA 自动冷却，其他引擎继续服务。
- `curl_cffi` 复制真实浏览器 TLS/HTTP2 指纹，支持代理轮换。
- `/extract` 用 trafilatura 把任意 URL 转干净 Markdown，带 SSRF 防护。
- 可直接兼容 Tavily / Serper / Brave / SearXNG 的请求响应格式。
- 风险：**只有 4 stars**，很新；不能作为唯一搜索源，适合试点。

### 5. DonSeTch — 技巧最前沿

- Rust 单文件，零 key、零账号；AGPL-3.0。
- 10+ keyless 后端并行：Brave、Bing、DDG、Mojeek、Yandex、Startpage + 垂直源。
- 真实 Chrome TLS：直接驱动 BoringSSL，而非伪造指纹表。
- solve-and-bounce：浏览器只解 JS challenge/渲染，拿 cookies 后交回高速 HTTP 层。
- 自改进抓取：按域名学习 cookie 生命周期，逐步减少浏览器升级次数。
- 本地 ONNX cross-encoder（`ms-marco-MiniLM-L-6-v2`）做语义重排，60/40 混合 RRF+BM25+consensus。
- 跨引擎共识：同一 URL 多引擎命中加分；`weak=true` 标注低共识。
- 注意：README 自报 benchmark，作者自己也说「take with a grain of salt」；不解 interactive captcha；避免用于 mass scraping；AGPL 合规需评估。

### 6. ask-search / OneSearch MCP — 快速包装

- `ask-search`：SearXNG 的 CLI/MCP 壳，`--urls-only` 很适合喂给我们的 link checker。
- `one-search-mcp`：`SEARCH_PROVIDER=local` 时用本地 Chromium 搜 Bing/Google/Baidu/Sogou，免 key；提供 `one_search / one_scrape / one_map / one_extract`。
- 两者都 MIT；适合快速验证，但不要把它们当成独立索引源。

---

## 四、值得吸收的新算法/新技巧

| 技巧 | 原理 | 来自 | 我们聚合器可怎么用 |
|---|---|---|---|
| **RRF 倒数排名融合** | `score = Σ w_e / (k + rank_e)`，只用排名不用分数，尺度无关 | FreeSearch / SearXNG | 把现有线性打分改成「RRF 主排序 + 现有分数做 rerank」 |
| **每引擎熔断器** | 引擎被限流/CAPTCHA 后自动冷却，其他引擎继续 | FreeSearch | `aggregate_search.py` 的 `skipped/error` 可升级为带冷却状态的 engine registry |
| **curl_cffi TLS 指纹** | 复制真实浏览器 ClientHello/h2 指纹，降低被识别概率 | FreeSearch | 用于 Bing/Google/Brave 的免费 HTML 入口；需评估 ToS |
| **HTTP-first + browser escalation** | 先高速 HTTP；被墙才升级 headless browser | DonSeTch / OneSearch | 作为 web_search/multi_search 失败时的最后兜底 |
| **solve-and-bounce** | 浏览器只解挑战拿 cookies，内容仍由 HTTP 层抓 | DonSeTch | 思路可借鉴；实现成本高，先不作为第一步 |
| **本地 cross-encoder 语义重排** | 小 ONNX 模型对 query+title+snippet 做 full attention 重排 | DonSeTch | 解决我们当前「关键词命中但 topic 不相关」的误判 |
| **跨引擎共识加分** | 同一 URL 被多个引擎召回 → 提升排序 | DonSeTch / FreeSearch | 我们已有 `engines[]` 合并，可把 consensus 作为显式排序因子 |
| **有序 fallback 工具列表** | 每个来源维护首选→备选，平台改版只换列表不改接口 | Agent Reach | 用于 10 引擎适配器的降级链 |
| **渠道自学习评分** | 按主题/语言记录哪个渠道更有效 | AutoSearch | 赛事检索可学习「公众号/官网/海外」各渠道命中率 |
| **MCP-native + LLM 解耦** | 搜索层只返回结构化结果，不让搜索服务绑定具体模型 | AutoSearch / FreeSearch | 与我们统一 schema 思路一致，可继续坚持 |

---

## 五、对我们聚合器的建议

### 建议优先级

1. **先做 FreeSearch API 适配器（试点）**  
   它是唯一一个「免 key + API-first + RRF + 熔断 + 兼容 Tavily 格式」的项目，最适合作为我们现有付费引擎的免费替代。  
   但 star 极少，先用 Docker 本地跑，小流量验证，不设为主源。

2. **接入 Agent Reach 补中文/社交长尾**  
   它解决的是我们现有 10 引擎里最弱的一块：B站、小红书、V2EX、雪球、Reddit、X、YouTube。默认渠道零 key，只读，成熟度高。

3. **把 AutoSearch 接成 deep research 模式**  
   40 渠道、27 个零配置，和赛事检索的「广撒网」高度契合。尤其适合我们做海外赛事、学术赛、开发者社区赛的补盲。

4. **观察 DonSeTch，暂不直接依赖**  
   技术上最先进，但 AGPL、反爬边界、benchmark 自报、交互验证码限制都要评估。可以作为「浏览器兜底」的独立可选工具，隔离部署。

5. **SearXNG 作为稳定底座**  
   如果我们愿意维护 Docker 服务，SearXNG 是最稳的 70+ 引擎底座。FreeSearch / ask-search / OneSearch 都能把它当上游。

### 我们当前聚合器已具备 vs 缺失

- 已有：统一 schema、并发扇出、状态审计、去重合并、付费门禁、加权排序。
- 缺失：RRF、引擎熔断、TLS 指纹、浏览器升级、语义重排、跨引擎共识、渠道自学习。

建议下一轮迭代先补三样：**RRF + 熔断 + 跨引擎共识**，成本低、收益最大。

---

## 六、风险与合规

1. 多数 keyless 项目是抓公开搜索页，**可能违反具体搜索引擎 ToS**；控制频率、只用于个人/内部研究。
2. 需要登录的平台一律用**小号**，不要复用主账号；Agent Reach 明确不替用户登录、不要密码。
3. DonSeTch 的反爬/绕过能力最强，也最容易踩 ToS；不要用于 mass scraping。
4. AGPL 项目（SearXNG、DonSeTch）若进入闭源商业产品，需做许可证评估。
5. 低 star 新项目（FreeSearch API、ask-search 以外的几个）接口可能突变，适配器要做隔离和降级。
6. 所有 README 中的性能/准确率数字均为作者自报，未做独立复现；本调研只核实仓库元数据与 README 声明。

---

## 七、核实来源

- GitHub REST API 仓库元数据（stars/forks/license/pushed_at），核实时间 2026-11-19。
- 各项目 README 原文：
  - `https://github.com/Panniantong/Agent-Reach`
  - `https://github.com/searxng/searxng`
  - `https://github.com/0xmariowu/Autosearch`
  - `https://github.com/Ethos6/free-search-api`
  - `https://github.com/dondai44423/donsetch`
  - `https://github.com/ythx-101/ask-search`
  - `https://github.com/dckthulhu/one-search-mcp`
