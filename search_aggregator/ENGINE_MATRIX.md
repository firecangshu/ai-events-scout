# 10 个搜索 Skill 逆向能力矩阵

> 目标：把 10 个搜索/内容检索 Skill 的优点拆出来，形成一个统一入口的聚合搜索引擎，扩大搜索范围和搜索深度。  
> 逆向范围：`SKILL.md`、关键脚本、配置、返回字段定义、调用参数与运行环境。  
> 结论先行：**没有任何单一引擎同时覆盖“网页广度、语义深度、中文社交内容、公众号互动数据、答案式引用、代码/公司/人物专搜”**。必须做统一 schema + 路由 + 降级 + 去重 + 加权排序。

---

## 1. 能力矩阵总表

| 引擎 Skill | 类型 | 调用入口 | 凭证 | 主要覆盖 | 结构化输出 | 互动/引用 | 优点 | 短板 | 聚合定位 |
|---|---|---|---|---|---|---|---|---|---|
| `tavily-search` | AI 优化网页搜索 | HTTP API `https://api.tavily.com/search` | `TAVILY_API_KEY` | 通用网页、研究型检索 | title/url/content/score/published_date | 可返回 answer、raw content | Agent 友好、结果简洁、支持 search_depth / topic / 时间范围 / 域名过滤 | 需 key；Skill 文档偏规格化，运行时细节不足 | 通用网页主引擎之一，深度检索 |
| `web-search-exa` | 神经语义搜索 | Exa API / MCP 工具 | `EXA_API_KEY` 或 MCP | 语义网页、公司、人物、代码、深度研究 | title/url/score/publishedDate/author/summary/text | highlights/text/summary | 语义理解强；有 company/code/people/deep research 专用工具；内容抽取好 | 高级工具需 key；MCP 与本地 CLI 调用形态不统一 | 语义补盲、代码/公司/人物专搜 |
| `aiskill-wechat-search` | 10万+公众号搜索 | `python scripts/fetch_gzh_trends.py --keyword ...` | 本机安全凭证 / `PROXY_API_KEY`，按次计费 | 公众号爆款文章、账号内容 | data.items，标题/摘要/作者/url/发布时间 | 阅读、点赞、在看、评论、分享、收藏、星标 | 公众号生态最深；真实互动数据；正文提取；支持排序、时间窗、补查互动 | 需授权且按次计费；有余额/服务错误状态，不能当空结果；凭证安全红线多 | 公众号深度引擎，默认需显式允许付费 |
| `multi-search-engine` | 多引擎聚合规则 | 无本地脚本；按 URL 模板调用 16 个搜索引擎 | 无 | 国内 7 + 国际 9 | 依赖网页解析 | 无统一互动字段 | 覆盖极广；无需 key；中英文分流；支持 site/filetype/exact/OR/排除词 | Skill 本身是工作流不是代码；受搜索引擎反爬影响；结果解析需自建 | 广度补盲，网页多引擎扇出 |
| `xiaohongshu-notes-search` | 小红书热门笔记 | `python scripts/fetch_xhs_hot_articles.py --keyword ... --output-format json` | `REDFOX_API_KEY` | 小红书热门笔记、趋势词 | items：noteId/title/desc/createTime/noteLink/author... | 点赞、收藏、评论、分享、互动数、三维评分 | 热门内容；相关性+热度+时效评分；拓词；HTML 报告 | 只收互动 1000+；需 key；小众词可能空；数据非实时 | 社交趋势引擎 |
| `perplexity` | 答案式搜索 | `node scripts/search.mjs "query" --json` | `PERPLEXITY_API_KEY` | 带引用的回答、批量查询 | 依赖 API 原始 JSON；常见 results/title/url/snippet | citation | 答案式输出；引用可追溯；支持批量查询 | 需 key；返回结构可能因 API 版本变化；脚本只取 top5 展示 | 答案/摘要引擎，适合快速形成结论 |
| `douyin-data-assistant` | 抖音公开数据 | `node src/douyin/search-cli.js --keyword ...` | `GUAIKEI_API_TOKEN` | 抖音视频/图文、热榜、博主作品、评论 | stdout 纯 JSON：aweme_id/desc/create_time/author/digg_count/share_url 等 | 点赞、评论、分享、收藏 | 抖音公开内容；爆款、评论洞察、热榜；stdout 纯 JSON 易解析 | 需 token；Node 16+；只公开数据；第三方 API | 短视频/热点引擎 |
| `wechat-article-search` | 轻量公众号搜索 | `node scripts/search_wechat.js "关键词" -n 10` | 无 | 搜狗微信公众号文章 | query/total/articles：title/url/summary/datetime/source | 无阅读/点赞，只有时间、来源 | 免费、轻量、零 npm 依赖；可输出 JSON；支持 -n/-d/-o/-r | 搜狗覆盖面有限；可能反爬；无互动数据；时间筛选是客户端过滤 | 公众号免费兜底引擎 |
| `web-search` | 本地免费网页搜索/抓取 | `python scripts/web_search.py search "query" --max 10` | 无 | 百度/Bing CN/ddgs；网页正文抓取 | 文本格式：序号、标题、URL、摘要 | 无 | 免费；中文走百度/Bing，英文走 ddgs；fetch 能抽正文 | 依赖 requests/bs4/ddgs；当前环境缺 bs4/ddgs；HTML 改版易失效 | 免费网页主力；带本地 free fallback |
| `gemini` | 模型联网研究 | Gemini API `generateContent` + `google_search` | `GEMINI_API_KEY` / `GOOGLE_API_KEY` | 实时网页、综合回答、引用 | candidates[].content.parts[].text + groundingMetadata | groundingChunks / groundingSupports / webSearchQueries | 模型理解+联网；能综合多来源；引用结构完整 | 需 key；答案式而非结果列表；搜索建议/引用有使用条款限制 | 综合研究引擎，适合深层摘要与交叉验证 |

---

## 2. 逆向出的可复用优点

### 2.1 广度层：把“搜得到”做大

- `multi-search-engine`：16 个搜索引擎 URL 模板、中英文分流、site/filetype/exact/OR/排除词。
- `web-search`：国内免 key 的 Baidu / Bing CN 链路，英文 ddgs 兜底，并且有 `fetch` 正文抽取。
- `tavily-search` / `web-search-exa`：带 API 的高质量网页索引，能补搜索引擎抓取不稳定的问题。

**吸收方式**：聚合器默认同时扇出到免费网页 + 多引擎 + 可用 API；每个引擎单独超时，失败不影响整体。

### 2.2 深度层：把“看得深”做厚

- `tavily`：search_depth=advanced、include_raw_content。
- `exa`：contents.text/highlights/summary、deep search、company/code/people 专用工具。
- `perplexity`：答案 + citation。
- `gemini`：google_search grounding，返回 webSearchQueries、groundingChunks、groundingSupports。

**吸收方式**：同一 query 同时保留“结果列表”和“答案摘要”两类产物；答案作为 `source_type=answer` 的 unified item，引用拆成独立 source items。

### 2.3 中文内容层：公众号 / 小红书 / 抖音

- `aiskill-wechat-search`：公众号生态深，互动数据最完整，但按次计费。
- `wechat-article-search`：免费公众号兜底，轻量 JSON。
- `xiaohongshu-notes-search`：热门笔记、互动数、三维评分、拓词。
- `douyin-data-assistant`：抖音公开内容、点赞/评论/分享、热榜、评论分析。

**吸收方式**：按 query 类型路由；社交内容不强行塞进网页结果排序主榜，保留 source_type 与 metrics，既可在统一列表里排序，也可按来源筛选。

### 2.4 可靠性层：失败降级与凭证门禁

- AISkill 明确规定：`balanceExhausted`、`serviceError`、`onboardingPreview` 不能当空结果。
- 抖音明确规定：退出码 3 = auth_required；空结果退出码 0 是正常的。
- 多个 Skill 需要 key，且当前环境未配置。

**吸收方式**：
1. 每个引擎返回 `ok / skipped / error` 状态，而不是静默消失。
2. 付费引擎必须同时满足“凭证存在 + `--allow-paid`”，否则跳过并记录原因。
3. 免费引擎失败时继续跑其他引擎；付费引擎失败不自动重试、不自动激活、不自动支付。

---

## 3. 统一结果 schema

```json
{
  "id": "sha1(normalized_url|title)",
  "engine": "tavily|exa|perplexity|gemini|web_search|multi_search|wechat_article_search|aiskill_wechat_search|xiaohongshu|douyin",
  "engine_group": "web|answer|wechat|xhs|douyin|company|code|people",
  "query": "原始查询词",
  "title": "标题",
  "url": "链接",
  "snippet": "摘要",
  "content": "正文或长摘要",
  "published_at": "发布时间",
  "author": "作者/账号",
  "source": "来源站点或公众号名",
  "source_type": "web|answer|wechat|xhs|douyin|code|company|people",
  "metrics": {
    "read": 0,
    "like": 0,
    "comment": 0,
    "share": 0,
    "interaction": 0,
    "native_score": 0
  },
  "tags": [],
  "engines": ["来源引擎列表，去重合并后填充"],
  "score": 0,
  "score_reasons": [],
  "raw": {}
}
```

---

## 4. 路由策略

| Query 类型 | 默认引擎组合 |
|---|---|
| 通用中文网页 | `web_search`, `multi_search`, `tavily`, `exa`, `perplexity`, `gemini` |
| 英文/国际检索 | `multi_search`, `web_search`, `tavily`, `exa`, `perplexity`, `gemini` |
| site: / filetype: / 精确匹配 | `multi_search`, `web_search`, `tavily`, `exa` |
| 公众号内容 | `wechat_article_search`, `aiskill_wechat_search` |
| 小红书趋势/爆款 | `xiaohongshu` |
| 抖音热点/视频 | `douyin` |
| 答案式总结 | `perplexity`, `gemini`, `tavily` |
| 代码文档 | `exa`（code category / get_code_context） |
| 公司/人物 | `exa`（company/people research） |

当前环境中所有付费凭证均未配置，所以真实验证只能跑免费引擎：`web_search`、`multi_search`、`wechat_article_search`。聚合器已把付费引擎实现为“凭证 + 显式 `--allow-paid` 双门禁”，不会误扣费或误触发授权流程。

---

## 5. 排序与去重

- URL 归一化：去协议差异、www、`utm_*` / `fbclid` 等跟踪参数、末尾斜杠。
- 内容指纹：无 URL 时用标题 + 摘要前 120 字生成 SHA1。
- 合并：同 URL 或同指纹的结果合并为一条，保留所有来源引擎，取更长的 title/snippet/content，合并 metrics。
- 打分：`相关性 60% + 引擎可信度 20% + 时效 10% + 互动/原生评分 10%`。
- 社交内容保留 metrics 和 source_type，不因为互动数据高就无条件压过高相关官方网页。

---

## 6. 当前环境的可用性结论

| 引擎 | 当前是否可真实调用 | 原因 |
|---|---|---|
| `web_search` | 部分可用 | 脚本存在，但当前缺 `bs4` / `ddgs`；聚合器内置 stdlib fallback |
| `multi_search` | 可用（内置实现） | 聚合器按 URL 模板直接请求并解析，不依赖原 Skill 脚本 |
| `wechat_article_search` | 可尝试 | Node 脚本存在、无 key；受搜狗反爬影响 |
| `tavily` | 跳过 | 缺 `TAVILY_API_KEY` |
| `exa` | 跳过 | 缺 `EXA_API_KEY` |
| `perplexity` | 跳过 | 缺 `PERPLEXITY_API_KEY` |
| `gemini` | 跳过 | 缺 `GEMINI_API_KEY` / `GOOGLE_API_KEY` |
| `xiaohongshu` | 跳过 | 缺 `REDFOX_API_KEY` |
| `douyin` | 跳过 | 缺 `GUAIKEI_API_TOKEN` |
| `aiskill_wechat_search` | 跳过 | 无凭证且默认禁止付费；需要显式授权/额度 |
