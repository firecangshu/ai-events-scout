---
name: ai-events-scout
slug: ai-events-scout
displayName: AI赛事百晓生
version: 1.3.1
description: "AI赛事百晓生：抓取当前还能报的AI/科技类赛事（黑客松/算法赛/创新创业大赛等），按身份档与地区硬约束筛选，支持国内/国外/不限、线上/线下/混合、纯学生/不限三维分类筛选，产出可转发的HTML/xlsx/长图；并可一键产出小红书 redskill 图文笔记物料（竖版封面+内容长图+可复制文案）。搜比赛、看报名截止、要赛事清单、要发小红书帖时用。"
category: 资讯聚合
agent_created: true
---

# AI 赛事百晓生（ai-events-scout）

## 概述
本 skill「**AI赛事百晓生**」把"AI 赛事清单抓取规则"固化为可复用的标准工作流：从全网检索当前**还能报**的 AI/科技类赛事，按用户长期口径严格筛选，自动标注「地区（国内/国外/不限）」「形式（线上/线下/混合）」「身份资格」三个维度，并在分享版 HTML 顶部提供「地区 / 形式 / 人群」三组分类筛选器；产出四份交付物（清爽表 HTML、常驻分享版 HTML、xlsx 对照表、分享长图 PNG）。目标是每次刷新都口径一致、透明可审计、可直接转发。

## 何时使用
- 用户说"看看最近的比赛 / 搜一下 AI 比赛 / 有没有合适的黑客松 / 报名截止还有哪些"等。
- 用户提供赛事聚合页（如 `黑客松.com/this-week`、`xn--ubtw9y6z8b.com`）要求筛出合适项。
- 用户要求"把这个做成 skill / 以后按这个标准搜"——即本 skill 的固化场景。
- 触发即加载本 skill + 读取 `references/rules.md` 全套口径。

## 标准工作流（每次都按此执行）
1. **确认目标身份档（前置硬约束）**：与用户确认身份档 A/B/C/D（杨博默认 A 社会人士/在职）。这是后续检索与筛选的硬约束（详见 `references/rules.md` 0.5 身份/资格维度）。
2. **确认时间基准**：取当前真实日期作为 `today` 与 `snap` 日期戳（用户消息里的 `current_time` 即真实时间，不要用旧快照日期）。
3. **免费全球发现（默认第一步，必跑）**：先运行统一入口，一句话拿到全球候选与待探活链接清单：
   ```
   python search_aggregator/run.py --query "AI hackathon" --snap <日期> --out output
   # 中文主题也可以：--query "AI 黑客松 报名"（国际源会自动转英文）
   ```
   该入口自包含、零 API key、零外部依赖、无硬编码路径——**别人安装 skill 后无需任何配置即可运行**。它并行跑 GDELT 全球新闻 / Hacker News / GitHub / arXiv / Devfolio / 站点扫描，自动去重排序，产出 `output/candidates_<date>.json`、`output/urls.txt`、`output/radar_<date>.html`。报告中 `status=skipped` 的源表示当时不可用，不得当作已检索；`candidates` 只是候选，仍需第 5 步按口径复核。
4. **生成检索清单（提炼器）+ 精确补充**：运行 `scripts/search_plan.py --identity <档> --snap <日期>` 得到"按身份约束的三轮检索清单"（广撒网/site 精确/差旅福利补采）。把清单 query 投喂给聚合入口 `search_aggregator/aggregate_search.py`（10 引擎路由 + 失败降级 + 去重排序）做精准补充；有 key 且用户允许时才启用付费引擎（`--allow-paid`），否则跳过并记录。
   - 官方/平台源（天池·魔搭·DataFountain·政府/高校官网）→ 聚合入口的 `web_search / multi_search`，必要时 WebFetch 二次核实
   - 微信公众号 → `wechat_article_search`（免费兜底）；`aiskill-wechat_search` 需授权且用户允许付费
   - 小红书 → `xiaohongshu`（需 `REDFOX_API_KEY` + `--allow-paid`）；海外深度 → `exa / perplexity / gemini / tavily`（需 key + `--allow-paid`）
   - 用户给的指定来源（如 `黑客松.com/this-week`、`xn--ubtw9y6z8b.com`）逐页逐条读。
5. **逐条按口径筛**（详见 `references/rules.md`，身份档统辖）：
   - 先按 `eligibility` 与身份档冲突即剔（如 A 档遇「纯学生限定」直接剔除，写原因）；
   - 必须含「报名/作品征集截止」字段；整体赛程结束日≠报名截止 → 剔除（腾讯云教训）；
   - 命中任一即剔除：初赛已截止、仅邮箱/扫码无网页入口、学生/校内/地域限定、纯视频内容类、无明确报名字段；
   - 保留硬门槛：报名进行中 + 网页入口探活200 + 对身份档开放。
6. **链接探活**：用 `scripts/check_links.py --file output/urls.txt`（直接吃第 3 步导出的清单）对每条候选报名入口核验 HTTP 200（curl 优先 + urllib 回退），仅 200 的保留；非 200 的换源或剔除。
7. **候选自动打标（规则为主 + AI 复判兜底）**：对第 3 步的雷达候选跑 `python scripts/tag_candidates.py --candidates <candidates_*.json> --out output`，自动打 `scope/form/eligibility/perks/regions/theme` 六维标签（含置信度与依据），产出 `candidates_tagged_*.json`、打标报告 md 与 `radar_discovery_*.html` 雷达发现报告（按「规则高置信 / 待AI复核」两层卡片呈现，自包含可转发）。报告里「待AI复核清单」的候选由**你（执行本 skill 的 AI）**按 `references/rules.md` 逐条复判定案，把结论写回对应项 `auto_tags`（conf 升「高」、来源标 ai-review）——这就是"LLM 兜底层"，零 key、随 skill 分发。**改打标规则后必须先跑 `python scripts/auto_tag.py --selftest`**（回归样例含华为校赛站/AWS/NFL 等历史误判，需全部通过）。
8. **判定形式 + 标注资格 + 判定地区**：按 `rules.md` 给每条标 `form`（线上/线下/混合，武汉异地线下需差旅）、`eligibility`（纯学生限定/社会组可报/所有人可报/企业·团队可报/仅个人可报）与 `scope`（国内/国外/不限，判定见 rules.md 0.6）。
9. **排序**：还能报的按剩余时间从近到远；"即将开启"单列（无则如实写"暂无"）。
10. **填数据文件**：复制 `references/events_template.json` 为 `events_data.json`，按 schema 填写（每条含 name/tags/scope/form/eligibility/deadline/link/note/chip/verified；被剔除的填进 dropped[] 写原因）。
11. **生成五交付物**：用已验证环境运行 `scripts/events_table_gen.py`（见下）。产出：分享版 HTML（卡片式·主交付物，顶部带「地区/形式/人群/差旅福利/主题」五组分类筛选器）、报名速查表 HTML（窄屏行动视图，同款筛选 + 关键词搜索 + CSV/Excel 导出）、清爽表 HTML（完整透明参考，含主题列）、清爽版 xlsx（辅助数据表，含主题列）、分享长图 PNG（每条含主题行）。
11b. **可选·小红书图文物料**：要发小红书时，**优先用 `xhs-edition/`**（独立合规版：`gen_xhs_note.py` 生成封面+内容长图+文案，`check_xhs.py` 23 项校验全 PASS 后才交付，数据口径已修，详见 `xhs-edition/TEST_REPORT.md`）。主版 `scripts/gen_rednote.py` 仍可用作快速出图，但未过平台字数/导流合规校验，不再作为小红书交付首选。
12. **本地预览交付物**：用 `present_files` 展示，**优先展示分享版 HTML** 作为清单主呈现，其余作为补充；向用户确认。
13. **发布判定**：用户说"看看/再看看"= 仅本地预览，**不**覆盖线上链接；用户显式说"发/发布"才用 `workbuddy_sites_deploy` 覆盖重发（复用既有沙箱）。

## 资源使用
- **`scripts/events_table_gen.py`**：从 `events_data.json` 生成五交付物。用当前环境的 Python 运行即可（无硬编码路径）：
  ```
  python scripts/events_table_gen.py --data output/events_data.json --out output --snap <YYYY-MM-DD>
  ```
  依赖 `openpyxl` + `Pillow`。若报缺依赖，先 `python -m pip install openpyxl Pillow`。无 `--data` 默认读脚本同目录 `events_data.json`；无 `--out` 默认当前目录。
  五份产物：**报名速查表 HTML**（窄屏行动视图：倒计时在前、分类成组、「地区/区域/形式/人群/差旅福利/主题」六组筛选 + 关键词搜索 + CSV/Excel 导出、每条带可点击「去报名 →」直达官网）、分享版 HTML（卡片式·主交付物，顶部带「地区/形式/人群/差旅福利/主题」五组分类筛选器）、清爽表 HTML（完整透明参考，含主题列）、清爽版 xlsx（辅助数据表，含主题列）、分享长图 PNG（每条含主题行）。
- **`scripts/check_links.py`**：批量核验报名入口 HTTP 200（curl 优先 + urllib 回退）。用法 `python check_links.py url1 url2 ...` 或 `--file urls.txt`；全部 200 退出码 0，否则 1。
- **`scripts/search_plan.py`**：检索清单**提炼器**（不实际搜索）。按 `identity` + `snap` 生成**三轮检索清单**（①广撒网 ②site 精确 ③差旅福利补采）+ 来源×工具可用性表。用法 `python search_plan.py --identity A --snap 2026-11-19 [--out plan.md]`。
- **`search_aggregator/aggregate_search.py`**（2026-11-19 新增 · 统一搜索层）：封装 10 个搜索 Skill/API 的统一入口，输出 JSON/HTML/MD 报告，含引擎状态、统一结果 schema、去重合并和加权排序。免费引擎可直接跑；付费/需 key 引擎必须 `key + --allow-paid` 双门禁。能力矩阵见 `search_aggregator/ENGINE_MATRIX.md`。
- **`search_aggregator/global_event_radar.py`**（2026-11-19 新增 · 免费全球赛事雷达）：赛事发现阶段首选，免 key 聚合 GDELT/HN Algolia/GitHub/arXiv/Devfolio/站点扫描，可选接本地 FreeSearch API 与 Agent Reach（已真实接入：自动探测渠道与登录态，B站/YouTube/网页(Exa) 免登录即用，小红书/Reddit/X 需 `agent-reach add`+本人登录后才启用）；输出统一 JSON/HTML/MD。说明见 `search_aggregator/GLOBAL_RADAR_README.md`。
- **`scripts/auto_tag.py`**（2026-11-19 新增 · 规则引擎自动打标）：从赛事文本用关键词+规则自动推断 `scope/form/eligibility/perks/regions`，人工只复核。默认 dry-run 只出报告，**加 `--write` 写回（仅填空缺、不覆盖人工值），`--force` 才强制覆盖**。perks 四档判定已用 6 组样例验证。取代 `tag_regions.py` 的序号硬编码。用法 `python auto_tag.py --data events_data.json --report out.md --write`。
- **`scripts/tag_candidates.py`**（2026-11-20 新增 · 雷达候选打标流水线）：把雷达输出（`candidates` 或 `results` 键均可）逐条六维打标，低置信自动分流「待AI复核」不冒充高置信；产出 `candidates_tagged_*.json` + `tagged_report_*.md` + `radar_discovery_*.html` 雷达发现报告（高置信/待复核两层卡片 + 维度分布概览 + 复核指引，自包含可转发）。用法 `python tag_candidates.py --candidates <radar.json> --out output`（`--html-out none` 跳过 HTML）。
- **`references/rules.md`**：筛选与产出全套口径（身份/资格维度、地区维度、硬性剔除、保留门槛、形式维度、分类筛选规格、产出形态、发布约定）。执行前必读。
- **`references/search_sources.md`**：搜索来源矩阵——10 个搜索 skill/工具的覆盖来源、检索要点、聚合入口调用方式与来源覆盖自审表。
- **`references/events_template.json`**：数据 schema 模板，复制后填写。
- **`scripts/gen_rednote.py`**：小红书 redskill 物料生成器。读 `events_data.json`，产出 `小红书_封面_{snap}.png`、`小红书_内容_{snap}_N.png`、`小红书_文案_{snap}.md`（详见 `references/rules.md` §11）。同 venv 运行。

## 数据文件 schema（events_data.json）
```json
{
  "snap": "2026-10-18",          // 快照日期戳（文件名与页眉用）
  "title_date": "2026-10-18",    // 页眉“刷新版”日期
  "today": "2026-10-18",         // 计算剩余天数基准日
  "events": [
    {     "name":"赛事名","tags":"标签","scope":"国内|国外|不限","form":"线上|线下|混合",
     "eligibility":"所有人可报|社会组可报|纯学生限定|企业·团队可报",
     "perks":"全包|包路费|包食宿|不包|未标注",  // 差旅福利·正向优点标签·非门槛
     "deadline":"2026-10-20（报名截止）","link":"https://...",
     "note":"一句话备注","chip":"报名将截止(可选)","verified":"OK(200)"}
  ],
  "dropped": [{"name":"被剔除赛事","reason":"初赛报名已截止→剔除"}]
}
```

## 产出与口径铁律
- 文案严格用用户原话与官方口径，**不自创润色**。
- 「形式」维度每次必带（🟢线上/🟠线下/🔵混合）。
- 「地区」维度每次必带（国内/国外/不限）；「身份资格」维度每次必带；「差旅福利（perks）」维度每次必带（全包/包路费/包食宿/不包/未标注，**正向优点标签、非门槛**，见 `rules.md` §0.7）。分享版 HTML 与速查表顶部提供「地区 / 形式 / 人群 / 差旅福利」四组分类筛选器（客户端过滤，见 `rules.md` §10）。
- 已剔除项及原因必写入交付物"已剔除"区，保证透明可审计。
- 每次刷新都做全网重搜 + 日期戳快照 + 链接存活校验，过期项移出"还能报"。
- **交付物定位**（按用户 2026-10-18 反馈）：主交付物 = **分享版 HTML**（卡片式、精致可转发，是清单对外呈现的核心）；**报名速查表 HTML** = 窄屏行动视图（时间在前、分类成组、每条带可点击「去报名 →」直达官网，适合手机转发与「点链接去报名」）；清爽表 HTML = 完整透明参考版（含筛选口径 + 已剔除原因）；**清爽版 xlsx 降为辅助数据表**（不单独作为头条，因过于简陋）；长图 PNG = 朋友圈/群分享配图。呈现给用户时**优先展示分享版 HTML**。
- **链接衔接口径（2026-11-14 定调）**：产品定位是「全网抓取 → 打标签 → 按需调取」。**小红书侧（笔记图文 + 小工具）只呈现「完整赛事名 + 一目了然的标签」**（线上/线下/混合、仅学生/社会组可报/企业·团队/仅个人/不限人群、国内/国外、剩余天数），**不出现任何网址与导流话术**；小工具容器断网且禁跳转站外与剪贴板，故不做域名长按复制。**需要报名衔接时用「报名速查表 HTML」/分享版 HTML/清爽表 HTML/xlsx**（不在容器内，三份 HTML 各带可点「去报名 →」，xlsx 带外部超链接）。
- **小红书 redskill（可选）**：用户要发小红书时，**优先用 `xhs-edition/`**（独立合规版：`gen_xhs_note.py` 生成封面+内容长图+文案，`check_xhs.py` 23 项校验全 PASS 后才交付，数据口径已修）；主版 `scripts/gen_rednote.py` 仅作快速出图备选，不作小红书交付首选。
