# 免费全球 AI 赛事雷达

## 一句话结论

在**不接任何搜索 API、不按次付费**的前提下，当前收益最大的组合是：

> **GDELT 全球新闻 + Hacker News Algolia + GitHub Search + arXiv + Devfolio + 免费网页/公众号站点扫描**
> 再加两个可选放大器：**本地 FreeSearch API** 和 **Agent Reach CLI**。

已经实现为 `global_event_radar.py`，可直接运行。

## 为什么是这个组合

| 层级 | 数据源 | 为什么选它 |
|---|---|---|
| 全球新闻 | GDELT DOC API | 覆盖全球 190+ 国家的公域新闻， multilingual，免费无 key，带来源国家/语言 |
| 技术社区 | Hacker News Algolia | 免费 JSON API，能抓到全球 AI 黑客松讨论、Show HN、官方外链 |
| 开发者生态 | GitHub Search API | 免费匿名（有限速），能发现赛事仓库、官方 starter kit、组织赛事 |
| 学术赛事 | arXiv Atom API | 免费，抓 AI challenge / benchmark / competition 相关研究型赛事 |
| 赛事平台 | Devfolio `__NEXT_DATA__` | 免费公开页面，直接读出 open_hackathons（名称/时间/线上/人数） |
| 通用网页 + 中文 | 已有 `web_search` / `multi_search` / `wechat_article_search` | 通过平台词查询补 Devpost / Kaggle / MLH / 公众号 / 中文赛事 |
| 可选放大器 | FreeSearch API | 本地自建，RRF 融合 + 熔断 + curl_cffi，兼容 Tavily 端点；当前 Docker 未启动，脚本会自动跳过 |
| 可选放大器（已真实接入） | Agent Reach | 多渠道调用：B站 / YouTube / 网页(Exa) 免登录即用；小红书 / Reddit / X 需 add+登录后自动启用；未添加或未登录自动跳过 |

## 运行

```bash
python search_aggregator/global_event_radar.py "AI hackathon" \
  --max 30 \
  --json-out search_aggregator/output/radar_ai_hackathon.json \
  --html-out search_aggregator/output/radar_ai_hackathon.html \
  --md-out search_aggregator/output/radar_ai_hackathon.md
```

中文 query 也可以：

```bash
python search_aggregator/global_event_radar.py "AI 黑客松 报名" --max 30 \
  --html-out search_aggregator/output/radar_cn.html
```

## 真实验证（2026-11-19）

查询：`AI hackathon`，`--max 30`，`--timeout 12`。

| 数据源 | 状态 | 原始条数 | 说明 |
|---|---|---:|---|
| GDELT 全球新闻 | skipped | 0 | 本机出口 IP 触发 429 限流；脚本不伪造结果，自动跳过 |
| Hacker News | ok | 31 | Algolia 公开 API，含全球赛事讨论与官方外链 |
| arXiv | ok | 3 | AI challenge / competition 研究型赛事 |
| GitHub | ok | 20 | AI hackathon 相关仓库（匿名 API 偶发限流，会自动跳过） |
| Devfolio | ok | 2 | 从 20 个开放赛事中按 AI 关键词过滤 |
| 站点扫描 | ok | 34 | Devpost / Kaggle / MLH / 中文赛事 + 公众号兜底 |
| FreeSearch | skipped | 0 | 本地服务未启动 |
| Agent Reach | skipped | 0 | CLI 未安装 |

结果：**原始 90 条 → 去重后 30 条**。

> 2026-11-19 更新：Agent Reach 已真实接入并实测。`--sources agent_reach` 单源实测：web(Exa) 渠道返回 8 条真实结果（Devpost / PayPal AI Hackathon / Meta Global AI Developer Hackathon 等）；小红书 / Reddit / X 因未登录自动跳过；YouTube 因本机网络到 yt-dlp 超时、B站因上游工具下载中而如实记录失败原因。整表扫描时该源状态与其他源互不影响。

抓到的代表性来源包括：

- Devpost：`PayPal AI Hackathon`
- Kaggle：`Host an AI Competition or Hackathon`
- Devfolio：`ETHChiangmai & Longevity Hackathon 2026`
- DoraHacks：`QVAC Hackathon I – Unleash Edge AI`
- Mistral：`Mistral AI Worldwide Hackathon 2026`
- Wired / Medium / LinkedIn / Twitter / OpenAIRE / Hacker News 等公域资讯
- GitHub 赛事仓库与 starter kit

## 输出

- JSON：统一 schema，含 `engines[].status` 来源审计、每项 `engines[]` 来源合并、评分理由。
- HTML：卡片式报告，带来源类型筛选（网页/答案/公众号/小红书/抖音）。
- Markdown：适合贴到文档或群发。

## 可选放大器怎么开

### 1. FreeSearch API（推荐先开）

当前 Docker daemon 未运行；也可以直接 pip 安装：

```bash
pip install "free-search-api[mcp] @ git+https://github.com/Ethos6/free-search-api"
freesearch serve   # http://127.0.0.1:8000
```

启动后雷达会自动检测到 `/health`，并启用 `/search` 作为额外网页源。  
默认地址可用 `FREESEARCH_URL` 覆盖。

### 2. Agent Reach

确保 `agent-reach` 在 PATH 中（1.6+，官方 GitHub release zip + `uv tool install` 安装，勿装 PyPI 同名包）。雷达会先跑 `agent-reach channels` 解析各渠道等级与登录态，再对可用渠道执行 `<渠道> search`：

- **免登录渠道自动启用**：`bilibili`、`youtube`、`web`（Exa 语义搜索兜底）
- **登录渠道**（`xiaohongshu`、`reddit`、`twitter`）只有 `login.logged_in=true` 才调用；未登录自动跳过，不会弹出登录窗口
- 渠道未添加 / 上游工具未装 / 调用失败，都会在报告 `engines[].message` 里如实记录原因，不影响其他渠道与整体扫描

可选渠道先 `agent-reach add <渠道>`（自动安装上游工具，如 bili-cli / opencli），登录类渠道再 `agent-reach login <渠道>` 由本人完成登录（建议小号）。安装或添加渠道网络下载慢时耐心等待即可。

## 已知限制

1. GDELT 对共享 IP 限流明显，同一 IP 短时间多次查询会 429；脚本按 skipped 处理，不伪造数据。
2. GitHub Search API 匿名限速（60 次/小时，且共享 IP 更容易 403）；失败自动跳过。
3. Devpost / DoraHacks 直连 403/405，目前通过网页搜索的 `Devpost/Kaggle/MLH` 平台词间接覆盖。
4. 雷达负责“发现候选”，不等于“可报名”。入赛事清单前仍需跑 `check_links.py` 探活 + 按 `rules.md` 复核身份档、报名截止、网页入口。
5. 免费公开抓取要控制频率并遵守目标站 ToS；不要用于 mass scraping。

## 与赛事主流程集成

推荐流程：

1. `global_event_radar.py` 全球发现候选。
2. `aggregate_search.py` 对重点 query 做精确补充。
3. `check_links.py` 探活。
4. `auto_tag.py` 自动打标（含 perks）。
5. `events_table_gen.py` 生成五交付物。
