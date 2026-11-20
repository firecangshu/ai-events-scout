# -*- coding: utf-8 -*-
"""
检索清单提炼器（ai-events-scout skill 配套 · 搜索层）
================================================
不实际发起搜索，而是按「身份约束 + 快照日期」生成一份**可直接执行的检索清单**：
每份清单标明 来源类型 → 用哪个搜索 skill/工具 → 具体 query（已嵌入身份约束）。
保证搜索范围完整、可复现，避免"漏源导致漏赛"。

用法：
  python search_plan.py --identity A --snap 2026-10-18
  python search_plan.py --identity A --snap 2026-10-18 --out plan.md
身份档 identity：
  A 社会人士/在职/个人开发者（杨博默认）  B 在校学生  C 所有人(最广)  D 企业/团队
"""
import argparse
import datetime

# 身份档：keep=保留的资格类型，drop=剔除的资格类型
IDENTITY = {
    "A": {"label": "社会人士 / 在职 / 个人开发者（杨博默认）",
          "keep": ["所有人可报", "社会组可报", "企业/团队可报"],
          "drop": ["纯学生限定"],
          "note": "剔除纯学生限定赛事；保留社会组/社会通道、所有人可报、企业/团队可报。"},
    "B": {"label": "在校学生",
          "keep": ["所有人可报", "纯学生限定"],
          "drop": ["仅社会/企业限定"],
          "note": "保留学生赛与所有人可报；剔除仅限社会人士/企业、在校生不可报的赛事。"},
    "C": {"label": "所有人（最广口径）",
          "keep": ["所有人可报", "社会组可报", "纯学生限定", "企业/团队可报"],
          "drop": [],
          "note": "最广口径：仅按地域/纯视频/无入口等通用规则剔除，保留含学生与社会各类。"},
    "D": {"label": "企业 / 团队",
          "keep": ["所有人可报", "企业/团队可报"],
          "drop": ["纯学生限定", "仅个人"],
          "note": "保留企业/团队赛道与所有人可报；剔除纯学生限定与仅个人可报的赛事。"},
}

# 基础检索主题（身份无关）——第一轮广撒网
BASE_TOPICS = [
    "AI 黑客松 报名 截止 2026年12月",
    "人工智能 大赛 报名 征集 12月",
    "AIGC 智能体 挑战赛 征集 奖金",
    "创新创业大赛 AI 报名 社会组",
    "算法赛 机器学习 报名 datafountain",
]

# 差旅福利采集主题（外地友好标签的数据源）——第三轮定向补采
# 目标：在赛事正文/官宣里找「报销路费/提供食宿/包住宿」等承诺，供 auto_tag.py 打 perks 标签
PERK_TOPICS = [
    "黑客松 报销路费 提供住宿 餐饮",
    "AI大赛 线下决赛 包食宿 交通补贴",
    "hackathon travel covered free accommodation flight",
    "AI竞赛 外地选手 住宿 补贴 差旅",
]

# 来源配置：(来源类型, 工具, 当前环境可用性, 该来源专属 query 后缀, 检索说明)
# 说明：当前环境仅内置 WebSearch/WebFetch 稳定可用；标注「需插件」的专用源若未安装，
#       其覆盖由 WebSearch 的 site: 限定 + 中英文 query 回退补上，不静默漏源。
SOURCES = [
    ("官方/平台源（天池·魔搭·DataFountain·政府/高校官网）", "WebSearch（site: 限定 + 时间窗）", "可用",
     "site:tianchi.aliyun.com OR site:modelscope.cn OR site:datafountain.cn OR site:*.gov.cn",
     "锁定官方报名入口 URL；site: 限定 + 月份时间窗；找到后必须用 check_links.py 探活 200。"),
    ("微信公众号（官宣长尾）", "WebSearch（mp.weixin.qq.com 限定）〔原 aiskill-wechat-search 需插件，未装则回退〕", "回退可用",
     "site:mp.weixin.qq.com 报名 截止",
     "抓官宣长尾与各赛事汇总号；高互动文再溯源官方报名页探活。"),
    ("小红书（民间/年轻向赛事）", "WebSearch（xiaohongshu.com 限定）〔原 xiaohongshu-notes-search 需插件〕", "回退可用",
     "site:xiaohongshu.com AI黑客松 报名",
     "补抓民间赛事与真实参赛反馈（差旅/食宿体验帖是 perks 线索）。"),
    ("海外平台（Kaggle/Devpost/GitHub）", "WebFetch + WebSearch（英文 query）〔原 Exa/Gemini 需插件〕", "回退可用",
     "AI hackathon open registration December 2026 site:kaggle.com OR site:devpost.com",
     "英文 query 召回海外赛；用 WebFetch 读官方页核实 entry deadline（区分 entry 与 final submission）与奖金。"),
    ("多引擎广域（兜底铺网）", "WebSearch（多轮中英文 + site:/时间窗）", "可用",
     "",
     "中文 + 英文 + site: 三路交叉；每轮合并去重后再进入筛选。"),
]


def build(identity, snap):
    cfg = IDENTITY.get(identity, IDENTITY["A"])
    try:
        d = datetime.date(*map(int, snap.split("-")))
    except Exception:
        d = datetime.date.today()
    horizon = (d + datetime.timedelta(days=45)).strftime("%Y-%m-%d")

    lines = []
    lines.append(f"# AI 赛事检索清单（提炼器输出）")
    lines.append("")
    lines.append(f"- **快照日期**：{snap}（检索时间窗：{snap} ~ {horizon}）")
    lines.append(f"- **目标身份档**：{identity} · {cfg['label']}")
    lines.append(f"- **身份约束**：{cfg['note']}")
    lines.append(f"- **保留资格类型**：{', '.join(cfg['keep']) or '（无排除，最广口径）'}")
    lines.append(f"- **剔除资格类型**：{', '.join(cfg['drop']) or '（无）'}")
    lines.append("")
    lines.append("> 按「三轮检索」逐项执行，合并去重后再进入筛选流程（见 rules.md）。")
    lines.append("> 身份约束：保留 " + ", ".join(cfg["keep"]) + "；剔除 " + (", ".join(cfg["drop"]) or "无") + "。")
    lines.append("")

    # 三轮检索
    site_queries = [s[3] for s in SOURCES if s[3]]
    rounds = [
        ("第一轮 · 广撒网（中文主题 × 全来源）", BASE_TOPICS),
        ("第二轮 · site 精确（各来源定向）", site_queries),
        ("第三轮 · 差旅福利补采（外地友好 perks 数据源）", PERK_TOPICS),
    ]
    for rtitle, queries in rounds:
        lines.append(f"## {rtitle}")
        for q in queries:
            if q:
                lines.append(f"- [ ] {q}")
        lines.append("")

    # 按来源列出工具与可用性
    lines.append("## 来源 × 工具（含当前环境可用性）")
    lines.append("")
    lines.append("| 来源类型 | 使用工具 | 可用性 | 检索说明 |")
    lines.append("|---|---|---|---|")
    for src_type, tool, avail, _q, tip in SOURCES:
        lines.append(f"| {src_type} | {tool} | {avail} | {tip} |")
    lines.append("")
    lines.append("> 注：标注「回退可用」的专用源若未安装插件，用 WebSearch 的 site: 限定 + 中英文 query 覆盖，不可静默漏源。")
    lines.append("")

    lines.append("## 来源覆盖自审（提交前勾选）")
    for src_type, _, avail, _, _ in SOURCES:
        lines.append(f"- [ ] {src_type}（{avail}）")
    lines.append("- [ ] 差旅福利线索已采集（供 auto_tag.py 打 perks 标签）")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="AI 赛事检索清单提炼器")
    ap.add_argument("--identity", default="A", help="身份档 A/B/C/D（默认 A 社会人士/在职）")
    ap.add_argument("--snap", default=datetime.date.today().strftime("%Y-%m-%d"), help="快照日期 YYYY-MM-DD")
    ap.add_argument("--out", default=None, help="将清单写入该文件（否则仅打印）")
    args = ap.parse_args()

    if args.identity not in IDENTITY:
        ap.error(f"未知身份档 {args.identity}，可选：{','.join(IDENTITY)}")
    text = build(args.identity, args.snap)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"检索清单已写入：{args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
