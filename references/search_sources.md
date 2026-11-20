# 搜索来源矩阵（ai-events-scout · 搜索层）

> 本 skill 不重复造搜索引擎，而是**优先调用统一聚合入口** `search_aggregator/aggregate_search.py`；它已封装 10 个搜索 skill / API 的优点，做路由、并发扇出、失败降级、去重合并和加权排序。
> 搜索范围直接决定结果质量——务必按本矩阵**扇出（fan-out）覆盖全部来源**，缺一类就可能漏掉合适赛事。
> 执行检索前，先跑 `scripts/search_plan.py` 生成"身份约束 + 日期"对应的检索清单，再把清单中的 query 交给聚合入口执行。

## 一、可用搜索 skill / 工具与适用来源

| 搜索能力 | skill / 工具 | 最擅长覆盖的来源 | 何时用 |
|---|---|---|---|
| 微信公众号文章 | **aiskill-wechat-search**（10万+公众号文章搜索与正文提取） | 公众号推文、机构官宣、高校/政府通知 | 找"XX大赛 报名"类公众号长尾信息、验证官网未列入口的赛事 |
| 小红书热门笔记 | **xiaohongshu-notes-search** | 小红书热点、参赛者经验帖、民间赛事汇总 | 补抓年轻群体/创作者向赛事、口碑与真实报名体验 |
| 语义 / 深度检索 | **web-search-exa**（Exa MCP） | 海外 Devpost/GitHub、技术博客、语义相关赛事、深度研究 | 找英文 AI 黑客松、按"open registration"语义召回、做竞品/相似赛比对 |
| Google 联网研究 | **gemini**（联网搜索与研究） | Google 全域、海外赛事官网、学术论文型赛 | 海外赛事官方页、Tavily 式研究、验证英文入口 |
| 多引擎广域检索 | **multi-search-engine**（16 引擎） | 中文综合（7 引擎）+ 全球（9 引擎）、site 限定、时间过滤 | 大面铺网、按 `site:xxx` 锁官网、按时间窗过滤近期赛事 |
| 通用检索（兜底） | WorkBuddy 内置 WebSearch / domain_search | 天池、魔搭、DataFountain、政府/高校官网 | 主力官方源；上述专用 skill 之外的补充与交叉验证 |
| 聚合入口（首选） | `search_aggregator/aggregate_search.py` | 上表全部 10 类能力 | 统一调用；自动跳过无凭证/付费引擎；输出统一 JSON/HTML/MD |
| 免费全球雷达（新增） | `search_aggregator/global_event_radar.py` | GDELT 全球新闻 + HN Algolia + GitHub + arXiv + Devfolio + 站点扫描 + 可选 FreeSearch/Agent Reach | 完全免 key、覆盖全球平台与公域资讯；适合赛事发现阶段 |

## 二、各来源检索要点

- **官方/平台源（天池 / 魔搭 / DataFountain / 官网）**：用 WebSearch / multi-engine 锁 `site:tianchi.aliyun.com`、`site:modelscope.cn`、`site:datafountain.cn`、`site:*.gov.cn`。这是"报名入口探活 200"的主要来源。
- **公众号**：调 aiskill-wechat-search，query 形如 `AI 黑客松 报名 截止`、`人工智能 大赛 征集`，重点看互动数据高的官宣文，再溯源到官方报名页做探活。
- **小红书**：调 xiaohongshu-notes-search，query 形如 `AI黑客松 报名`、`AIGC大赛`，用于发现长尾/民间赛事与真实参赛反馈。
- **海外**：调 web-search-exa / gemini，query 形如 `AI hackathon open registration November 2026`、`Devpost machine learning competition`。注意"形式"标 线上/线下（海外多为线上或需签证线下）。
- **时间窗**：所有检索都加时间约束（如"近 30 天 / 截止晚于今天"），避免召回已过期赛事。

## 三、检索清单生成（提炼器）

`scripts/search_plan.py --identity <身份档> --snap <YYYY-MM-DD>` 会输出一份**可直接执行的检索清单**：
每行标明 `来源类型 → 用哪个 skill/工具 → 具体 query（已嵌入身份约束）`。
agent 按清单逐项检索、合并去重，再进入筛选流程。

身份档（详见 rules.md「身份/资格维度」）：
- `A` 社会人士/在职/个人开发者（杨博默认）→ 剔除纯学生限定，保留社会组+所有人可报
- `B` 在校学生 → 剔除仅社会/企业限定，保留学生+所有人可报
- `C` 所有人（最广）→ 仅剔除地域/纯视频/无入口，保留含学生+社会
- `D` 企业/团队 → 保留企业/团队+所有人可报，剔除纯学生+仅个人

## 四、来源覆盖检查（提交前自审）

检索结束后对照下表，确认每类来源都跑过；任一类缺失需在交付物"已剔除/说明"区注明原因。
| 来源 | 已检索 |
|---|---|
| 天池/魔搭/DataFountain/官网 | ☐ |
| 公众号（WebSearch site:mp.weixin.qq.com 回退） | ☐ |
| 小红书（WebSearch site:xiaohongshu.com 回退） | ☐ |
| 海外（WebFetch + 英文 query 回退 Exa/Gemini） | ☐ |
| 多引擎广域（WebSearch 多轮中英文） | ☐ |
| 差旅福利线索（供 auto_tag.py 打 perks） | ☐ |

## 五、当前环境可用性（2026-11-19 实测）
- 10 个搜索 Skill 目录均已存在；但 Tavily / Exa / Perplexity / Gemini / 小红书 / 抖音的 API Key 均未配置，公众号付费检索也未授权。
- 免费可用：`web_search`（内置 stdlib fallback）、`multi_search`（16 引擎 URL 模板的内置实现）、`wechat_article_search`（搜狗公众号）。以上三者已由聚合入口封装。
- 付费/需 key 引擎已实现为“凭证存在 + 显式 `--allow-paid` 双门禁”，不会自动激活、自动充值或读取凭证明文。
- 聚合入口会自动把 skipped 引擎写进报告，不能把 skipped 当作“搜索过了”；赛事清单交付前仍需用内置 WebSearch/WebFetch 对关键官方页做二次核实。
- 差旅福利（perks）必须在检索阶段主动采集（见 `search_plan.py` 第三轮），否则 `auto_tag.py` 无米下锅、筛选器形同虚设。采集关键词见 `rules.md` §0.7。

## 六、免费全球雷达（赛事发现阶段首选）
```bash
python search_aggregator/global_event_radar.py "AI hackathon" --max 30 \
  --html-out search_aggregator/output/radar_ai_hackathon.html
```
- 完全免 key：GDELT / HN Algolia / GitHub / arXiv / Devfolio / 免费网页搜索。
- 可选放大器：本地 FreeSearch API（自动检测 127.0.0.1:8000）；Agent Reach CLI（已真实接入：自动探测渠道等级与登录态，B站/YouTube/网页(Exa) 免登录即用；小红书/Reddit/X 需 `agent-reach add` + 本人登录后才启用；未添加/未登录/失败的渠道自动跳过并在报告里记录原因）。
- 2026-11-19 实测单次 query 原始 90 条 → 去重 30 条，覆盖 Devpost / Kaggle / Devfolio / DoraHacks / Mistral / Wired / HN / GitHub 等。
- 雷达只做“发现候选”，入清单前仍需 link 探活 + rules.md 复核。详见 `search_aggregator/GLOBAL_RADAR_README.md`。

## 七、聚合搜索入口（精确补充调用方式）
```bash
python search_aggregator/aggregate_search.py "AI 黑客松 报名 截止 2026年12月" \
  --engines auto --max 15 --fresh month \
  --json-out search_aggregator/output/events_query.json \
  --html-out search_aggregator/output/events_query.html
```
- `--engines auto`：10 个引擎全部进入路由，跳过无凭证/未允许付费的引擎。
- `--boost-terms "报名,截止,黑客松,大赛"`：赛事检索建议加业务加权词。
- 输出统一 schema，按 `score` 排序，按 `source_type` / `engines` 可筛选；报告中的 `engines[].status` 是来源覆盖审计依据。
