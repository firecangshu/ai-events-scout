# HANDOFF · AI 赛事百晓生（ai-events-scout）

> 交接时间：2026-11-20（v1.3.1 更新）｜ 快照基准日：2026-11-19 ｜ 身份档：A（社会人士/在职，默认）
> 历史交接（2026-11-14，v1.2.0/小红书/小工具）见 §0–§11，仍有效；**v1.3.0 变化见 §12，v1.3.1 变化见 §12.7**。

## 0. 一句话现状

**源文件地址 = `E:/44.AI赛事百晓生/`。** v1.3.1 三层能力全部成型：**第一步抓取 ✅（全球雷达 8 源 + Agent Reach 真实接入）、第二步打标 ✅（六维规则 + AI 复判兜底 + 14 例回归全过）、第三步呈现 ✅（主题筛选器 + 雷达发现报告 HTML）**。代码/规则/文档已同步工作区与两个安装副本；腾讯 WorkBuddy SkillHub v1.3.1 已正式发布（审核中，见 §12.8）。
**小红书侧现状（2026-11-14 起）**：小工具 1.0.0 已发布（appId `6af864c73894b30015bbd288`）；1.0.1（去 footer 引流话术）已送审待用户扫码确认 v6 预览后 submit；图文物料用 `xhs-edition/` 合规版（23/23 PASS）。详见 §10–§11。

## 1. 目录结构

| 路径（相对本目录） | 内容 |
|---|---|
| `SKILL.md` | v1.3.1，工作流 13 步（第 7 步=候选自动打标+雷达发现报告） |
| `references/rules.md` | 全套口径，含 §0.7 perks、§1 校赛陷阱、§10 筛选器、§11 小红书 |
| `references/events_template.json` / `search_sources.md` | 数据 schema / 来源矩阵（含全球雷达与聚合入口） |
| `search_aggregator/` | **v1.3.0 新增**：`run.py` 一键入口、`global_event_radar.py` 全球雷达 8 源、`aggregate_search.py` 10 引擎聚合、`ENGINE_MATRIX.md`、`GLOBAL_RADAR_README.md`、`GITHUB_KEYLESS_SEARCH_RESEARCH.md` |
| `scripts/events_table_gen.py` | 五交付物生成器（v1.3.1：全量带主题列/徽章，速查表六组筛选 + CSV/Excel 主题列） |
| `scripts/auto_tag.py` | **v1.3.0 增强**：六维规则打标 + `--selftest` 回归 14 例 |
| `scripts/tag_candidates.py` | **v1.3.0 新增 / v1.3.1 增强**：候选打标流水线 + `radar_discovery_*.html` 雷达发现报告（高置信/待复核两层） |
| `scripts/gen_rednote.py` / `check_links.py` / `search_plan.py` / `tag_regions.py` | 小红书物料 / 探活 / 三轮检索清单 / 地区打标（已被 auto_tag 取代，保留兼容） |
| `output/` | 产物（events_data.json 快照 2026-11-19：17 可报/28 剔除；candidates_tagged 与打标报告等） |
| `minitool/` | 小红书小工具（§11）：1.0.0 已发布，1.0.1 送审中 |
| `xhs-edition/` | 小红书图文笔记版（§10，合规版 23/23 PASS） |
| `_archive/` | 归档区（§9，对外分享时排除） |
| `HANDOFF.md` | 本文件 |

## 2. 关键绝对路径

| 用途 | 路径 |
|---|---|
| **源文件地址（唯一编辑目标）** | `E:/44.AI赛事百晓生/` |
| 数据快照 | `E:/44.AI赛事百晓生/output/events_data.json` |
| 工作区产物原件 | `F:/workbuddy缓存/2026-10-27-10-47-47/ai-events/` |
| 安装副本 A（v1.3.1，同源） | `C:/Users/User/.workbuddy/skills/ai-events-scout__skillhub/` |
| 安装副本 B（v1.3.1，同源） | `C:/Users/User/.workbuddy/skills/ai-events-scout/` |
| 旧版备份（可回滚） | `C:/Users/User/.workbuddy/skills/ai-events-scout/_backup_v1.1.0_2026-11-14/` |
| 工作区记忆日志 | `F:/workbuddy缓存/2026-10-27-10-47-47/.workbuddy/memory/2026-11-14.md` |
| Python 环境（已验证 openpyxl + Pillow） | `C:/Users/User/.workbuddy/binaries/python/envs/default/Scripts/python.exe` |

两个 C 盘目录是 WorkBuddy 用户级 skill 的安装副本，不作编辑目标。工作区根目录下的 `赛题.md`、`选手手册.md`、`灵机一动*.md`、`*_raw.txt` 属「双赛道赛题」另一任务，未搬入。

## 3. 运行命令

```
set P=C:/Users/User/.workbuddy/binaries/python/envs/default/Scripts/python.exe
set SRC=E:/44.AI赛事百晓生

REM 五交付物
"%P%" "%SRC%/scripts/events_table_gen.py" --data "%SRC%/output/events_data.json" --out "%SRC%/output" --snap 2026-11-14
REM 小红书物料
"%P%" "%SRC%/scripts/gen_rednote.py" --data "%SRC%/output/events_data.json" --out "%SRC%/output" --snap 2026-11-14
REM 链接探活
"%P%" "%SRC%/scripts/check_links.py" --file "%SRC%/output/urls.txt"
REM 小工具逻辑测试（17 项，离线 DOM stub）
node "%SRC%/minitool/test_logic.js"
```

本目录已从 `scripts/gen_rednote.py` 实跑通过（4 个文件正常产出）；所有文件与 C 盘同源副本字节一致。
注意：`--snap` 只改文件名与页眉，`today` 取自数据文件 `today` 字段；换新基准日需同步更新 `events_data.json`。

## 4. 数据状态

`events_data.json`：`snap/title_date/today` 均为 `2026-11-14`，**`identity` 档 C（所有人/最广口径）**，`events` **24 条**（按截止升序），`dropped` **23 类**剔除原因。资格分布：所有人可报 11 / 纯学生限定 8 / 企业·团队可报 3 / 社会组可报 2。**24 个报名入口已于 2026-11-14 复验：全部 HTTP 200**（`check_links.py --file output/urls.txt` 实跑，退出码 0，24/24 通过）。

**口径变更记录**：2026-11-14 起由身份档 A 改为 **C（最广口径）**，原因——小工具面向小红书全体读者，原 A 档会把「纯学生限定」全剔，导致工具内该筛选项恒为 0 条（空筛选项等于没有）。新增收录 10 条学生专属赛事（华为智能体创新赛、荣耀·英特尔 AI 智造创新赛、臺大×華南金融科技黑客松、CrossPointX 2026、AI芯智能赛道、Global AI Builder's Challenge、Qoder 高校创造力大赛、SpectoV National Hackathon、腾讯 WorkBuddy 创作挑战赛、GenHacks），每条均已核验报名截止字段与参赛对象并探活 200。同时剔除 4 条（NextWave 报名为 Google 表单、本机探活不可达；重庆大学 AI 开学季官方页显示「比赛休息」；HackGlobal 2026 报名窗口已过；Remote Control AI 提交已截止）。

> 若后续回到身份档 A（只面向社会人士/在职），需把 `events` 中 8 条纯学生限定移回 `dropped`，并重新生成五交付物与小工具包。

## 5. 本轮审查结论（只读评审，未改代码）

| 维度 | 判定 |
|---|---|
| 是否符合小红书 RedSkill 要求 | 不符合 |
| 是否流畅（工程运行） | 主流程通，边界脆 |
| 是否合理（内容/合规） | 不达标 |

方向错位：小红书官方 RedSkill 是「上传 SKILL.md 技能包 → 审核 → 挂载笔记组件 → 读者复制口令装到本地 Agent」的**技能分发机制**；`gen_rednote.py` 是**图文笔记物料生成器**。

P0（发布即失败 / 合规红线）：标题候选 28/33/31 字（上限 20）、正文 1608 字（上限 1000）、话题标签 12 个（建议 5–10）；「链接放评论区/主页」「附直达链接」属暗示导流话术且图内无链接；`events_data.json` 第 8 条「三好AI创新应用竞赛（台湾·社会组）」`scope=国外`，名称与地区口径均需修正；`elig_short()` 去括号删掉了「限 AWS Partner Network MSP」「需依托国内法人单位」「须用通义千问+阿里云算力」「18+」等关键报名限制。

P1（工程，均已实测复现）：空 events → `ZeroDivisionError`；缺 `name` → `KeyError`；两位数序号偏移；每页序号 1–7 与文案 1–14 断链；`--snap` 与 `today` 不同步；字体硬编码 `C:/Windows/Fonts/msyh*.ttc`，换平台回退后中文成豆腐块。

合规项：1080×1440 3:4、3 张图 ≤18、全篇比例统一、PNG 内无 emoji、封面统计条为真实计数（9 线上 / 7 国内）。

## 6. 引用核验表

| 内容 | 出处 | 状态 |
|---|---|---|
| 官方 CLI `redskill install <identifier>`，仅消费者侧安装路径 | `redskill.xiaohongshu.net/install.md`（curl 200，1081B） | 已核实·一手 |
| PC 5 步上传/管理/挂载，移动端 6 步挂载+消费 | `fe-video-qc.xhscdn.com/...` 官方「Red Skill · 诚邀创作者首批入驻」页 | 已核实·一手 |
| 标题≤20、正文≤1000、图片≤18、3:4 1080×1440 | 发布界面限制，多家第三方一致 | 部分核实 |
| 仅解析 Markdown/TXT、YAML 与 Python 脚本被过滤 | 2026-05/06 内测期报道（i黑马、腾讯新闻、九派财经） | 部分核实·时效性待核 |
| 《Skill上传规范》：粉丝≥1000、注册≥6个月、实名、账号健康 | i黑马 2026-06-10 转述 | 部分核实 |
| 站外导流为最高优先级红线 | 官方《交易导流违规管理细则》治理公告转载 | 部分核实 |
| 上传体积上限、类目体系、Windows 支持、当前是否全量开放 | 无一手来源可达 | 未核实，不臆测 |

## 7. 接手后待办

1. 决策：走真 RedSkill（另做纯 Markdown 可上传技能包，去掉 WorkBuddy 专属依赖与「杨博/武汉/默认A」个性化耦合），还是只把图文物料修到达标。→ 图文物料达标版已完成（`xhs-edition/`），是否上架 RedSkill 仍待决策。
2. ~~修 P0 四项~~：台湾口径与数据文件已修（output/events_data.json 第 8 条改「中国台湾·社会组」、scope=国内，四交付物已重生成）；标题/正文超长与导流话术属 gen_rednote.py，由 xhs-edition 取代，主版不再单修。发布前确认账号门槛，并在创作者后台确认格式限制是否已放开。
3. ~~修 P1 容错~~：gen_rednote.py 空数据 ZeroDivisionError 已修（draw_slide 空守卫 + paths 过滤）；字体回退与资格限制回显由 xhs-edition 覆盖。

上传 RedSkill 时排除 `output/`、`HANDOFF.md`；平台当前只解析 Markdown/TXT，PNG/HTML/xlsx 不会被打包。

## 8. 口径铁律（用户原话，不要改写）

- 「按我的语言来，不要自己组织语言」
- 「不去做对比，只描述」
- 「新增内容融入既有内容，不改既有结构与文风」
- 文案严格用用户原话与官方口径，不自创润色。
- 纯学生限定一律剔除；设社会组/社会通道的保留。
- 报名截止必须用「报名/作品征集截止」字段；整体赛程结束日 ≠ 报名截止（腾讯云教训）。
- 交付带引用编号的内容时，必须附「编号 → 内容 → 出处 → 核验状态」对照表。
- 索要信息前先查历史（transcript / memory / docs）。

## 9. 归档区（2026-11-14 15:13 新增）

`_archive/` 存放本项目相关的记忆、缓存、源文件副本，共 598 文件 / 约 135MB，统一为**复制**，各处原件保留。

| 子目录 | 内容 | 文件数 |
|---|---|---|
| `_archive/workspace/` | 工作区 23 文件（记忆日志、8 份源材料 md/txt、13 份产物原件） | 23 |
| `_archive/identity/` | 用户级 SOUL / IDENTITY / USER / MEMORY / workspace-state | 5 |
| `_archive/session/` | 本会话 jsonl + rollback + tool-results（复制时刻快照） | 63 |
| `_archive/blobs/` | WorkBuddy 全局图片缓存（跨项目共享） | 507 |

来源路径、大小、字节校验结果与快照差异见 `_archive/MANIFEST.md`。

- 身份文件、会话记录、blobs 均为平台运行数据，**只能复制不能移走**；原位置保留。
- 归档区含个人身份信息与跨项目图片；对外分享或上传 RedSkill 时排除整个 `_archive/`。
- 归档区不参与 skill 运行，`SKILL.md` / `references/` / `scripts/` / `output/` 布局未改动。

## 10. 小红书独立版本（2026-11-14 16:40 新增）

用户要求「另外做一个小红书的版本，按小红书要求改造并测试」。成果在 `xhs-edition/`，与源版并列，源版未改动。

- 构成：`SKILL.md`（纯 Markdown 可上传）、`references/rules.md`、`scripts/gen_xhs_note.py` + `scripts/check_xhs.py`（生成器+校验器）、`data/events_data.json`（地区口径已修）、`output/`（封面 1 + 内容 3 + 文案 + 校验结果）、`TEST_REPORT.md`。
- 平台约束内建：标题 ≤20 字、正文含话题 ≤1000 字、标签 7 个、图片 4 张统一 1080×1440、封面安全区、导流词与极限词扫描、AI 生成主动标识、PNG 无 emoji。
- 数据口径：第 8 条改为「中国台湾·社会组」，`scope` 由国外改国内；资格字段完整回显，不再去括号删减。
- **2026-11-14 数据同步**：随主数据身份档改为 C，`data/events_data.json` 已同步为 24 条，内容页由 3 张增至 5 张（图片 4→6 张），校验器重跑 **23/23 PASS**，TEST_REPORT 已更新。
- 测试结果：`23 PASS / 0 FAIL`（A 平台 10 / B 版式 3 / C 口径 5 / D 容错 5），4 张图经 3 轮视觉复检通过。详见 `xhs-edition/TEST_REPORT.md`。
- 运行：`python xhs-edition/scripts/gen_xhs_note.py --data xhs-edition/data/events_data.json --out xhs-edition/output --snap <日期>`，再跑 `check_xhs.py`。
- 未覆盖：真实发布（需账号手动）、RedSkill 上架（门槛与当前格式限制待核）、`--dry-run` 包校验（需 npm 与上传授权）。

## 11. 小红书小工具（2026-11-14 19:00 新增 · 待送审）

用户要求「小红书里点开就能用、能看搜索赛事信息」。成果在 `minitool/`，与源版并列。

**平台硬约束（已核实官方在线文档 2026-11-10 版）**：容器断网、禁跳转站外 URL（`target="_blank`／站外跳转）、禁剪贴板 API → **小工具内无法直接打开报名网站**；合规做法是卡片显示报名域名 + 长按复制。需要链接可点时用「报名速查表 HTML」（不在容器内）。

**构成**：`minitool/dist/`（index.html + assets/style.css / main.js / data.js）、`AI赛事百晓生_minitool.zip`、`build.js`（一条命令刷新数据→重打包）、`icon.png`（512×512 1:1）、`cover.png`（1080×1440 3:4，复用 xhs-edition 封面）、`preview.json` / `submit.json`、`session.json`（操作记录，中断可恢复）、`test_logic.js`（离线 DOM stub 逻辑测试 17 项）。

**功能**：关键词搜索 + 地区/形式/人群/状态四组筛选；每卡含倒计时徽章（≤3天红/≤7天橙）、三维分类标签、报名域名（长按复制）。

**送审参数**：类目 `query_tool`（实用工具）、权限无（纯静态页）、名称「AI赛事百晓生」、版本 1.0.0。

**踩坑**：
- Windows `Compress-Archive` 写的 zip 用反斜杠路径，`redapp upload` 报 `LOCAL_VALIDATION_FAILED` → 须用 Python `zipfile` 写正斜杠；`index.html` 必须在 zip 根。
- zip 内 JS 必须外置且为经典脚本（禁 `type="module"`）；内联脚本与行内事件被容器 CSP 拦截。
- 容器禁 Worker；`assets/` 静态资源优化策略需 9.53.3+ 且仅对新发布生效。

**当前状态**：**1.0.0 已发布**（appId `6af864c73894b30015bbd288`，status 2 已发布，24 条赛事含 8 条纯学生限定）。**1.0.1 已送审，审核中**（appId `6af871908eb43600159f38d4`，status 1）：移除 footer「配套速查表（可下载表格）」站外引流话术与悬空引用（按《交易导流违规管理细则》类型5自查发现），代码包 md5 `0300b27a0e88ed8e031c4abd69f4fe46`，送审 planHash `07231cd0fce78c734a777b2560a7ad623797843502b5757a480f7be94ece0c96`。审核期间旧版 1.0.0 继续在线；可用 `redapp status --app-id 6af871908eb43600159f38d4` 跟踪审核。

**产品定位（用户 2026-11-14 定调）**：全网抓取 → 打标签 → 按需调取。**小红书侧只呈现「完整赛事名 + 一目了然的标签」（线上/线下/混合、仅学生/社会组可报/企业·团队/不限人群、国内/国外、倒计时）**；**笔记正文与小工具内均不出现任何网址、链接字、下载/网盘等站外获取话术**。**报名衔接靠两条路**：① 读者点赛事名自行搜索官网（正文只写「报名前请各赛事官方页面核对」）；② 表格产物（速查表/分享版/清爽表 HTML + xlsx）含可点链接，**仅作为离线交付物，不在小红书内容中引导下载**。

> 预览迭代记录：v1（14 条）→ v2（倒计时+三维标签+域名行）→ v3（24 条含学生赛）→ v4（绑定新版封面）→ v5（去链接化，已发布为 1.0.0）→ **v6（1.0.1，去 footer 引流话术，当前有效）**。v1–v5 的二维码与 appId 均已作废。
> **v6 变更**：footer 由「完整报名方式与资格细则整理在配套速查表（可下载表格）中」改为「数据为当日赛事快照，报名信息以各赛事官方页面为准」。同时 `xhs-edition/scripts/check_xhs.py` 引流词表新增「下载/网盘/附件/自取/领取」（依据《交易导流违规管理细则》2025-03-12：类型3 发布其他平台链接及其变形植入、类型5 明示或暗示诱导用户至站外/私域）。已实测：包内网址/引流词扫描 **0 命中**。
> **合规判定（2026-11-14，用户问「具体详情可下载表格（含报名网站衔接）能不能过审」）**：**不能过**。表格文件本身含链接不违规（平台外文件，用户本地行为），但笔记正文写「可下载表格」= 诱导站外获取文件（类型5）；「含报名网站链接」= 其他平台链接的变形表述（类型3）。处罚梯度：警告→限流→扣信誉分→永久封号。合规替代话术：①「完整详情可点下方『AI赛事百晓生』小工具组件」（平台内组件，细则明文豁免）②「完整清单在上方图片里，报名前请各赛事官方页面核对」。

**刷新与重打包**：`node minitool/build.js --data output/events_data.json` 一条命令完成「读数据 → 重写 `dist/assets/data.js` → 重新打包 zip」（固定时间戳，同样输入必得同样 md5，可复现）。仅改 `data.js`，`index.html` / `main.js` / `style.css` 不动。注意 zip 内文件内容逐字节一致时，zip 整体 md5 仍可能因时间戳元数据不同而变化——比对内容要用「解包后逐文件 md5」，不要只看 zip md5。

**校验状态（2026-11-14）**：逻辑测试 17/17 通过；官方审计 PASS；链接探活 14/14 全 200；官方模拟器（`redapp dev`，simulator 0.2.0）加载 dist 全部文件均 200，iframe 精确 393px 视口实测 `vw=378 scrollW=378 overflowing=0`（无横向溢出），渲染截图确认头部/搜索框/四组筛选/倒计时/三维标签/域名行均正常。

**待办**：① 用户扫码确认 v6 预览（`minitool/preview-qr-v6.png`）→ 执行 submit（planHash `07231cd0fce78c734a777b2560a7ad623797843502b5757a480f7be94ece0c96`）→ 回报审核状态（旧版 1.0.0 审核期间继续在线）；② 审核通过后用户在笔记「发布页 → 添加组件 → Red Skill」挂载，读者才可点开；③ **快照会过期**（当前 3 个赛事「还剩1天」）：下一轮刷新需重跑检索 → 更新 `output/events_data.json` → `node minitool/build.js` → 重新上传并出新预览二维码（版本号需递增，如 1.0.2）；④ 发布笔记时正文**禁用**「下载表格」「链接」等话术（见上「合规判定」），用平台内小工具组件做报名衔接入口。

## 12. v1.3.0 · 搜索与打标能力升级（2026-11-19 新增）

### 12.1 三步走路线图（用户定的主线路）

| 步骤 | 状态 | 说明 |
|---|---|---|
| 一、抓取 | ✅ | 全球雷达 8 源 + 10 引擎聚合 + 三轮检索清单 + 一键入口 + 探活 |
| 二、打标 | ✅ | `tag_candidates.py` 流水线：规则六维打标，低置信分流「待AI复核」；`auto_tag.py --selftest` 14/14 |
| 三、呈现 | ✅ | 五交付物全量带主题：分享版/速查表筛选项含「主题」、清爽表/xlsx 加主题列、长图加主题行；新增 `radar_discovery_*.html` 雷达发现报告（高置信/待复核两层 + 维度分布 + 复核指引） |

### 12.2 常用命令（无硬编码路径，任意目录可跑）

```bash
# 第一步：一键全球发现（candidates + urls.txt + HTML/MD）
python search_aggregator/run.py --query "AI hackathon" --snap 2026-11-19 --out output
# 第二步：候选自动打标（规则为主，产出 tagged JSON + 报告 + 待AI复核清单）
python scripts/tag_candidates.py --candidates output/candidates_20261119.json --out output
# 改打标规则后必跑（14 例回归含历史误判，需全过）
python scripts/auto_tag.py --selftest
# 链接探活（直接吃第一步的 urls.txt）
python scripts/check_links.py --file output/urls.txt
# 第三步：五交付物
python scripts/events_table_gen.py --data output/events_data.json --out output --snap 2026-11-19
```

### 12.3 Agent Reach（可选放大器，已真实接入）

- 已按官方 install.md 用 `uv tool install`（GitHub release zip）装好 agent-reach 1.6.1；**勿装 PyPI 同名包**。
- 雷达会先 `agent-reach channels` 解析渠道与登录态，再对可用渠道执行 `<渠道> search`；1.6+ 输出为 `{ok, result, error}` JSON，适配器已兼容。
- 渠道现状：**web(Exa) ✅ 实测出真实数据**（Devpost/PayPal/Meta 等）；**B站/小红书 = 用户明确不装**（后台安装已终止）；Reddit/X = 未登录自动跳过；YouTube = 本机网络超时。未就绪渠道在 `engines[].message` 如实记录，不影响其他源。
- 登录类渠道需用户本人 `agent-reach login <渠道>`（建议小号）；装好/登录后无需改代码，雷达自动启用。

### 12.4 AI 复判兜底层（"智能体"的正确形态）

WorkBuddy 云服务 LLM 走 HTTP 会校验浏览器 Origin（`auth_` 错误），Python CLI 直连不可行；故 LLM 兜底设计为：**脚本把低置信候选分流成「待AI复核清单」，执行 skill 的 AI 按 rules.md 逐条复判后写回 `auto_tags`（conf 升「高」、标 ai-review）**——零 key、零 token 成本、随 skill 分发到任何 AI。不要在脚本里硬调云服务 LLM。

### 12.5 新增铁律

- perks 永远是优点标签，不参与剔除。
- 改打标规则必须先 `auto_tag.py --selftest` 全过（14 例含：华为校赛站=纯学生、AWS 美元≠海外、NFL 本科生队≠纯学生、英文差旅全包等）。
- 候选打标宁缺勿错：资格低置信/差旅仅泛提的候选进待复核清单，不冒充高置信。
- 工作区改动必须 cp 同步到两个安装副本（`skills/ai-events-scout/` 与 `__skillhub/`），否则别人拿不到。

### 12.6 接手优先级（v1.3.1 视角）

1. ~~第三步呈现~~ ✅ 已完成（v1.3.1）：分享版/速查表主题筛选器、清爽表/xlsx/长图主题展示、雷达发现报告 HTML 均已落地并同步副本。
2. 每轮刷新后跑 `--selftest` + 抽查当轮打标报告待复核项。注意：英文 hackathon 候选普遍因「无明确限定信号」进待复核（30/30 属预期），需 AI 按 rules.md 复判定案，不要批量默认开放。
3. ~~SkillHub 线上发布~~ ✅ 已完成（v1.3.1 已正式发布，审核中，见 §12.8）。
4. 小红书侧：跟进 1.0.1 审核状态与 v6 预览确认（§11 待办）。

### 12.7 v1.3.1 · 第三步呈现落地（2026-11-20 新增）

- **`events_table_gen.py`**：分享版与速查表新增「主题」筛选器（`data-theme` 空格分隔多标签，JS `indexOf` 命中任一即通过；筛选按钮按当期数据动态生成）；清爽表加主题列、xlsx 加主题列（链接列号 11→12、列宽 A-N）、长图每条信息行加「主题：」；速查表 CSV/Excel 导出表头与数据同步加「主题」列。
- **`tag_candidates.py`**：新增 `radar_discovery_<date>.html` 雷达发现报告（`--html-out` 可自定义路径，传 `none` 跳过）；按「规则高置信 / 待AI复核」两层卡片呈现，含六维徽章、来源/评分/互动、评分依据、维度分布概览与复核指引；兼容雷达原生 `results` 键与 `meta.generated_at` 快照回退；JSON 结果新增 `pending` 明细与候选级 `_pending` 字段（可审计）。
- **验证**：`py_compile` 通过；17 条正式数据重新生成五交付物成功；30 条真实雷达候选全链路跑通（全部进入待复核属预期，见 12.6-2）。
- **同步**：`events_table_gen.py`、`tag_candidates.py`、`SKILL.md`、`HANDOFF.md` 已 cp 同步到 `skills/ai-events-scout/` 与 `__skillhub/`（脚本 MD5 三处一致）。

### 12.8 双平台发布回执（2026-11-20 新增 · 平台辨析）

**三个发布渠道必须区分，历史上曾把「小红书 Red Skill」误当「腾讯 SkillHub」：**

| 渠道 | CLI | zip 结构 | v1.3.1 状态 |
|---|---|---|---|
| **腾讯 WorkBuddy SkillHub** | `~/.skillhub/skills_store_cli.py` | 外层目录必须是 skill 名：`ai-events-scout/SKILL.md` | ✅ 已正式发布，审核中（本节回执 A） |
| 小红书 Red Skill | `redskillhub-upload` | SKILL.md 在 zip 根目录 | 用户网页端已上传**迭代版本**；助手零发送动作，仅提供填写信息（见回执 B） |
| 小红书小工具 minitool | `redapp` | index.html 在 zip 根 | 1.0.3 已上传+预览，待用户扫码确认后 submit（见 §11 待办） |

**回执 A · 腾讯 WorkBuddy SkillHub（正确平台）**
- 登录态：`userId=559390 / handle=user_2f59a3b2 / role=user`。
- 包：`output/ai-events-scout_v1.3.1_tencent_skillhub.zip`（18 文件，外层 `ai-events-scout/`）。
- dry-run：`{"dryRun":true,"slug":"ai-events-scout","version":"1.3.1"}`。
- 正式发布：
  ```json
  {"ok":true,"skillId":285548,"slug":"ai-events-scout","version":"1.3.1","versionId":534363,
   "reviewStatus":"pending","contentAuditStatus":"pending","securityScanStatus":"pending",
   "fileCount":18,"fingerprint":"d75ba10c629cf0f710ae1c0d25c04ee9e4329291ec352bff2450b5654d1cea43",
   "tags":{"latest":"1.3.1"}}
  ```
- 跟进：审核通过后 `skills_store_cli.py search "ai-events-scout"` 或在技能市场确认公开版本为 1.3.1；pending 期间搜索结果暂不可见属正常。

**回执 B · 小红书 Red Skill（勿与 A 混淆）**
- 关键发现：`redskillhub-upload` 默认 `--env prod`（edith.xiaohongshu.com，200）；此前失败全因误用 `--env beta`（504 网关）。
- prod CLI 提交回执：`status=submitted / skillId=107492 / versionId=115027 / auditRequestId=107492_115027_1795172499486 / first_version=true`。
- **定位（用户 2026-11-20 明确）**：用户网页端上传的这一版就是**迭代版本**，不是新建；助手**零发送动作**——不 CLI 提交、不重复网页提交，仅提供填写信息。CLI 那次 `first_version=true`（skillId 107492 / versionId 115027）只是 prod CLI 的 side effect，不代表本次迭代是新建，不得据此补发。

**元数据整理**：`__skillhub/_skillhub_meta.json` 原先 `lastPublishReceipt` 误存小红书回执，现已拆为 `lastPublishReceipt`（腾讯 SkillHub，回执 A）与 `xiaohongshuRedSkillReceipt`（小红书，回执 B）两个字段。

**小红书双对象并存（2026-11-20 用户截图实证）**
- 页面现状：`ai-events-scout` 出现两个同名对象且都「生效中」——V1.3.1（无使用人数，有「更新版本」按钮）与 V1.0.2（1 人使用）。根因是 V1.3.1 走了"新建上传"通道（CLI `first_version=true`），而非在 V1.0.2 上点"更新版本"原地迭代。
- **用户定调（长期铁律）**：只保留一个最新版本即可；以后所有迭代都必须在**旧版本对象上点「更新版本」**，不得重新上传生成一个新对象。
- 收口动作（待用户本人在页面执行，助手零发送/零提交/零下架）：① 下架旧 V1.0.2，只留 V1.3.1；② 若笔记组件挂的是旧对象，下架前改挂 V1.3.1；③ 后续升级一律在 V1.3.1 上「更新版本」。
- 本条已写入项目长期记忆 `.workbuddy/memory/MEMORY.md`。
