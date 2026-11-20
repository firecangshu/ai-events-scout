# 聚合搜索引擎使用说明

## 1. 它是什么

`aggregate_search.py` 是对 10 个搜索 Skill / API 逆向后形成的统一入口：

- 统一结果 schema：引擎、来源类型、标题、链接、摘要、正文、时间、作者、互动数据、原始字段、评分。
- 路由：按查询语言、意图、用户指定引擎选择调用路径。
- 并发扇出：多个引擎并行执行，单引擎失败不影响整体。
- 失败降级：状态分为 `ok / skipped / error`；skipped 不等于“搜过了”。
- 去重合并：URL 归一化 + 标题指纹；多引擎命中会合并并加分。
- 加权排序：相关性 60% + 引擎可信度 20% + 时效 10% + 互动/原生评分 10%。
- 输出：JSON / HTML / Markdown。HTML 带来源类型筛选。

能力矩阵详见 `ENGINE_MATRIX.md`。

## 2. 快速开始

```bash
python search_aggregator/aggregate_search.py "AI 黑客松 报名 2026" \
  --engines auto --max 12 --fresh month \
  --boost-terms "报名,截止,黑客松,大赛" \
  --json-out search_aggregator/output/query.json \
  --html-out search_aggregator/output/query.html \
  --md-out search_aggregator/output/query.md
```

赛事检索推荐加 `--boost-terms "报名,截止,黑客松,大赛"`，让报名/截止相关结果在排序中靠前。

## 3. 参数说明

| 参数 | 说明 |
|---|---|
| `query` | 查询词 |
| `--engines` | `auto/all` 或逗号分隔引擎名；默认 `auto`，即 10 个引擎全部进入路由，受凭证门禁约束 |
| `--mode` | `fast / balanced / deep`；deep 会让 Tavily/Exa 使用更深检索 |
| `--scope` | `auto / web / cn / global / social / answer` |
| `--max` | 最终返回条数 |
| `--fresh` | `day / week / month / year` |
| `--include-domains` | 逗号分隔，限定域名 |
| `--exclude-domains` | 逗号分隔，排除域名 |
| `--boost-terms` | 逗号分隔，相关性加权词 |
| `--allow-paid` | 显式允许调用需 key 或按次计费引擎 |
| `--timeout` | 单引擎超时秒数 |
| `--workers` | 并发引擎数 |
| `--json-out / --html-out / --md-out` | 输出文件路径 |

## 4. 引擎清单

| 引擎名 | 类型 | 当前环境 |
|---|---|---|
| `tavily` | AI 优化网页搜索 | 需 `TAVILY_API_KEY` + `--allow-paid` |
| `exa` | 神经语义 / 代码 / 公司 / 人物 | 需 `EXA_API_KEY` + `--allow-paid` |
| `perplexity` | 答案 + 引用 | 需 `PERPLEXITY_API_KEY` + `--allow-paid` |
| `gemini` | Google Search Grounding 研究 | 需 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY` + `--allow-paid` |
| `web_search` | 免费网页搜索 + 正文抽取 | 可用；本地脚本缺依赖时自动用 stdlib fallback |
| `multi_search` | 多引擎广域检索 | 可用；内置 Baidu/Bing/Sogou/360/DDG 等模板 |
| `wechat_article_search` | 搜狗公众号免费搜索 | 可尝试；受搜狗反爬影响 |
| `aiskill_wechat_search` | 10万+公众号深度搜索 | 按次计费；需授权 + `--allow-paid` |
| `xiaohongshu` | 小红书热门笔记 | 需 `REDFOX_API_KEY` + `--allow-paid` |
| `douyin` | 抖音公开数据 | 需 `GUAIKEI_API_TOKEN` + `--allow-paid` |

## 5. 安全与计费红线

1. 不会读取、打印或写入凭证明文；只通过环境变量是否存在判断是否可用。
2. 付费引擎必须显式 `--allow-paid`；否则只记录 `skipped`。
3. AISkill 返回 `onboardingPreview`、`balanceExhausted`、`serviceError` 时按状态返回，绝不自动激活、自动充值、自动重试。
4. 付费 API 失败时保留错误信息，不把失败伪装成空结果。
5. 抖音 `auth_required`（退出码 3）单独识别，不继续重试。

## 6. 真实验证记录（2026-11-19）

### 6.1 免费三引擎赛事检索

```bash
python search_aggregator/aggregate_search.py "AI 黑客松 报名 2026" \
  --engines web_search,multi_search,wechat_article_search \
  --max 12 --fresh month \
  --json-out search_aggregator/output/validate_hackathon.json \
  --html-out search_aggregator/output/validate_hackathon.html \
  --md-out search_aggregator/output/validate_hackathon.md
```

结果：
- Web Search：7 条，走内置 stdlib fallback。
- Multi Search：28 条，扇出 5 个网页搜索引擎。
- 公众号搜索：12 条。
- 原始 47 条，去重后展示 12 条；重复搜狗跳转链按标题指纹合并成功。

### 6.2 十引擎自动路由与付费门禁

```bash
python search_aggregator/aggregate_search.py "独立站 上线3个月 谷歌只收录8个页面 怎么提高收录" \
  --engines auto --max 5 \
  --json-out search_aggregator/output/validate_auto_gating.json
```

结果：
- Tavily / Exa / Perplexity / Gemini / 小红书 / 抖音：因缺 key 全部 `skipped`。
- 10万+公众号：因未加 `--allow-paid` 被 `skipped`，未产生付费调用。
- Web Search / Multi Search 正常返回结果，报告完整记录所有引擎状态。

## 7. 与赛事程序集成

`references/search_sources.md` 已把聚合入口设为首选搜索层。推荐流程：

1. `scripts/search_plan.py` 生成三轮检索清单。
2. 把清单中的 query 逐条交给 `aggregate_search.py`。
3. 从 JSON 中取 `results[].url`，用 `scripts/check_links.py` 探活。
4. 人工/规则复核资格、截止时间、入口一致性，再写入 `events_data.json`。
5. 聚合报告中的 `engines[].status` 作为“来源覆盖自审”证据，skipped 必须说明原因。
