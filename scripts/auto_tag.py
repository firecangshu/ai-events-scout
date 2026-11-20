# -*- coding: utf-8 -*-
"""
AI 赛事百晓生 · 规则引擎自动打标器（ai-events-scout skill 配套）
==============================================================
从赛事文本（name/tags/note/eligibility/form/deadline）用「关键词 + 规则」自动推断标签：
  - scope       地区：国内 / 国外 / 不限
  - form        形式：线上 / 线下 / 混合
  - eligibility 资格：所有人可报 / 社会组可报 / 企业·团队可报 / 纯学生限定 / 仅个人可报
  - perks       外地友好（差旅福利·加分项非门槛）：全包 / 包路费 / 包食宿 / 不包 / 未标注
  - regions     区域多标签（大湾区⊂珠三角⊂华南，多标签并存）—— 取代 tag_regions.py 的序号硬编码

设计铁律：
  1. perks 是【正向优点标签】，绝不参与收录/剔除判定，只做展示与筛选。
  2. 规则判定「宁缺勿错」：置信度低的标为「未标注」并在报告里提示人工复核。
  3. 已有人工标注的字段默认不覆盖（除非 --force），人工判断优先。

用法：
  python auto_tag.py --data output/events_data.json --report output/打标报告.md
  python auto_tag.py --data ... --write            # 写回 JSON（仅填空缺，不覆盖人工值）
  python auto_tag.py --data ... --write --force     # 强制用规则结果覆盖所有字段
"""
import os
import re
import sys
import json
import argparse

# ---------------- 标签词表 ----------------
# 外地友好/差旅福利：分「路费」「食宿」两轴，再组合成四档
PERK_TRAVEL_KW = [
    "包路费", "包交通", "包往返", "报销路费", "报销交通", "报销往返", "路费补贴", "交通补贴",
    "报销机票", "报销火车", "报销高铁", "提供机票", "提供火车票", "往返机票", "往返火车", "免费交通",
    "提供差旅", "包差旅", "差旅补贴", "含机票", "含路费", "含交通",
    "travel covered", "flight covered", "transport", "airfare", "travel grant", "free flight",
    "travel reimbursement", "reimburse travel", "cover travel", "travel expenses covered",
    "flight reimbursement", "train tickets covered", "transportation covered", "cover flights",
]
PERK_STAY_KW = [
    "包食宿", "包住宿", "包餐饮", "包吃住", "食宿全包", "提供食宿", "提供住宿", "提供餐饮", "提供酒店",
    "免费住宿", "免费酒店", "免费餐饮", "住宿补贴", "餐补", "含食宿", "含住宿", "含餐饮", "提供晚餐", "提供午餐",
    "accommodation", "hotel", "free food", "meals", "lunch", "dinner", "lodging",
    "accommodation covered", "hotel covered", "meals provided", "food provided", "housing provided",
    "free accommodation", "meals and lodging",
]
PERK_NONE_KW = [
    "食宿自理", "交通自理", "差旅自理", "费用自理", "路费自理", "不含食宿", "不含交通",
    "不提供住宿", "不包食宿", "需自行承担", "self-funded", "no accommodation",
    "travel not covered", "no travel reimbursement", "own expense", "at your own cost",
    "travel expenses are not", "does not cover travel",
]
#  negation：出现"是否提供/能否报销"等疑问/说明语时降置信
PERK_WEAK_KW = ["差旅", "住宿", "酒店", "机票", "火车", "食宿", "餐饮"]

SCOPE_FOREIGN_KW = [
    "国外", "海外", "kaggle", "devpost", "github", "devpost.com",
    "新加坡", "迪拜", "芬兰", "沙特", "麦地那", "印度", "美国", "英国", "欧盟", "worldwide", "global",
    "international", "overseas", "united", "uk", "usa", "canada", "australia",
]
# 注意：美元/美金是奖金币种，不能作为地区信号；全球/不限归 SCOPE_GLOBAL_KW 判定
SCOPE_GLOBAL_KW = ["全球开放", "面向全球", "全球个人", "不限地区", "各国均可", "worldwide", "global", "不限国家",
                   "any country", "all countries", "participants worldwide", "open to the world",
                   "no geographic restriction"]
SCOPE_DOMESTIC_KW = [
    "国内", "中国", "全国", "厦门", "杭州", "北京", "上海", "深圳", "广州", "武汉", "合肥", "苏州", "南京",
    "成都", "重庆", "西安", "天津", "宁波", "青岛", "天池", "魔搭", "datafountain", "阿里云", "华为云",
    "腾讯", "支付宝", "中科大", "佛光", "中国台湾", "台湾", "香港", "澳门",
]

FORM_MIXED_KW = ["混合", "线上+线下", "线上初赛", "线下决赛", "线下评审", "线下路演", "线下现场", "真机线下",
                 "现场答辩", "线下赛", "online + offline", "online/offline", "hybrid", "online qualifiers",
                 "in-person finals", "offline finals"]
FORM_OFFLINE_KW = ["线下", "现场", "到场", "落地", "in-person", "onsite", "on-site", "offline event",
                   "physical event", "held in", "take place in"]
FORM_ONLINE_KW = ["线上", "远程", "online", "virtual", "提交至", "远程提交", "remote", "online submission",
                  "virtual hackathon", "fully online", "online-only"]

# 强学生限定词：出现这些才认定纯学生。注意"本科生/研究生/大学生"单独出现多为分赛道或对象描述，不算强限定。
ELIG_STUDENT_STRONG = ["纯学生限定", "学生限定", "仅限在校", "仅在校生", "只招在校", "在校生限定", "全日制在校生",
                       "students only", "student-only", "must be a student", "仅学生", "不接受社会",
                       "current students", "enrolled students", "full-time students", "student hackathon",
                       "high school students only", "only for students", "restricted to students"]
# 专属站点/校内限定信号（2026-11-19 新增，修复华为校赛站误判）：
# 赛事名带「XX大学站/XX学院站/校园赛」或正文写「全校学生/本校学生/我校学生」= 该校专属，对社会人士不开放。
# 这类信号的优先级高于「企业组/OPC组」等泛化赛道词——因为一个校赛站的说明里常照抄主赛事的"企业组"介绍。
ELIG_CAMPUS_SITE_KW = ["大学站", "学院站", "学校站", "校园赛", "校内赛", "校赛", "分校", "校区",
                       "全校学生", "本校学生", "我校学生", "全体在校学生", "面向本校", "该校学生",
                       "university chapter", "campus hackathon", "student chapter"]
# 明确的院校缩写承办站点（如"广科院·华为赛"）——单独列出避免误伤普通"XX学院"表述
ELIG_CAMPUS_ABBREV = ["广科院", "华科站", "武大站", "交大站", "南大站", "浙大站", "中大站"]
# 弱学生词：仅作提示，不足以单独判纯学生（如"设本科生赛道""在校大学生为主"）
ELIG_STUDENT_WEAK = ["在校生", "在校学生", "高校在校", "全日制", "学生赛", "在校大学生", "本科生", "研究生",
                     "university track", "undergraduate", "graduate student", "college student", "for students"]
ELIG_SOCIAL_KW = ["社会组", "社会通道", "社会人士", "在职", "面向全社会", "开放给社会", "professional",
                  "working professionals", "industry professionals"]
ELIG_TEAM_KW = ["企业组", "企业·团队", "企业/团队", "团队可报", "限apn", "限 aws partner", "msp", "科研院所", "企事业单位", "公司报名"]
ELIG_OPEN_KW = ["所有人", "全球开放", "面向全球", "不限身份", "不限主体", "open to all", "anyone", "18+", "成年",
                "open to everyone", "anyone can participate", "no restrictions", "above legal age"]
ELIG_SOLO_KW = ["仅个人", "个人参赛", "个人开发者", "solo", "individual only"]

# 主题标签（2026-11-19 新增 · 多标签，取前 3）：与交付物分类/用户检索意图对齐
THEME_KW = [
    ("大模型", ["大模型", "llm", "gpt", "通义", "文心", "gemini", "llama", "foundation model", "多模态", "mllm"]),
    ("智能体", ["智能体", "agent", "agentic", "multi-agent", "autonomous agent", "mcp"]),
    ("AIGC", ["aigc", "生成式", "文生图", "文生视频", "扩散模型", "diffusion", "generative", "text-to-image",
              "image generation", "video generation"]),
    ("机器学习", ["机器学习", "深度学习", "machine learning", "deep learning", "neural", "nlp", "computer vision",
                  "数据挖掘", "data mining"]),
    ("机器人", ["机器人", "具身", "robot", "embodied", "自动驾驶", "autonomous driving", "无人机"]),
    ("行业应用", ["医疗", "金融", "教育", "制造", "农业", "legal", "healthcare", "fintech", "edtech",
                  "供应链", "能源", "碳中和"]),
    ("硬件与IoT", ["物联网", "iot", "硬件", "embedded", "边缘计算", "edge computing", "芯片"]),
    ("Web3", ["区块链", "web3", "blockchain", "nft", "defi", "加密"]),
    ("数据竞赛", ["数据分析", "数据赛", "数据建模", "data bowl", "kaggle", "预测模型", "推荐系统"]),
]

# 区域关键词（顺序：先特殊后一般；多标签并存）
REGION_KW = [
    ("大湾区", ["大湾区", "粤港澳", "香港", "澳门"]),
    ("珠三角", ["珠三角", "深圳", "广州", "佛山", "东莞", "珠海"]),
    ("长三角", ["长三角", "上海", "杭州", "苏州", "南京", "宁波", "昆山"]),
    ("中国台湾", ["中国台湾", "台湾", "臺大", "台北", "臺北"]),
    ("华北", ["北京", "天津", "河北", "雄安", "华北", "太原"]),
    ("华东", ["华东", "浙江", "江苏", "山东", "福建", "合肥", "中科大", "阿里云", "支付宝"]),
    ("华中", ["华中", "武汉", "湖北", "长沙", "湖南", "郑州", "河南", "南昌", "江西"]),
    ("华南", ["华南", "广东", "深圳", "广州", "厦门", "海南", "珠海"]),
    ("西南", ["西南", "成都", "重庆", "四川", "贵州", "云南", "贵安", "武当"]),
    ("西北", ["西北", "西安", "陕西", "甘肃", "宁夏", "青海", "新疆", "庆阳"]),
    ("东北", ["东北", "辽宁", "沈阳", "大连", "吉林", "黑龙江", "抚顺", "望花"]),
]

SINGLE_REGION = {"全国", "国外", "不限"}


def norm(s):
    return (s or "").lower()


def hit_any(text, kws):
    t = norm(text)
    return [k for k in kws if norm(k) in t]


# ---------------- 各维度判定 ----------------
def tag_perks(it):
    """返回 (取值, 置信度, 依据)。四档 + 未标注。仅展示用，不影响收录。"""
    text = " ".join(str(it.get(k, "") or "") for k in ("name", "tags", "note", "eligibility", "form", "deadline"))
    travel = hit_any(text, PERK_TRAVEL_KW)
    stay = hit_any(text, PERK_STAY_KW)
    none = hit_any(text, PERK_NONE_KW)
    weak = hit_any(text, PERK_WEAK_KW)
    if none and not travel and not stay:
        return "不包", "高", "明示自理/不含：" + ",".join(none[:3])
    if travel and stay:
        return "全包", "高", "路费+食宿：" + ",".join((travel + stay)[:4])
    if travel:
        return "包路费", "中", "路费：" + ",".join(travel[:3])
    if stay:
        return "包食宿", "中", "食宿：" + ",".join(stay[:3])
    if weak:
        return "未标注", "低", "仅泛提差旅词（" + ",".join(weak[:3]) + "），未明示提供→建议人工核对"
    return "未标注", "高", "文本无差旅福利信息"


def tag_scope(it):
    text = " ".join(str(it.get(k, "") or "") for k in ("name", "tags", "note", "scope"))
    f = hit_any(text, SCOPE_FOREIGN_KW)
    # 国内平台/政府源强信号覆盖"全球参与"等弱词
    dom = hit_any(text, SCOPE_DOMESTIC_KW)
    if hit_any(text, SCOPE_GLOBAL_KW):
        return "不限", "高", "明示全球/不限地区：" + ",".join(hit_any(text, SCOPE_GLOBAL_KW)[:2])
    if any(norm(k) in norm(text) for k in ["国外", "海外", "kaggle", "devpost", "迪拜", "沙特", "印度", "worldwide", "global"]):
        return "国外", "高", "海外平台/落地：" + ",".join(f[:3])
    if dom:
        return "国内", "中", "国内主体/落地：" + ",".join(dom[:3])
    if f:
        return "国外", "低", "仅弱海外词：" + ",".join(f[:3])
    return "不限", "低", "无明确地区信号，默认不限"


def tag_form(it):
    text = " ".join(str(it.get(k, "") or "") for k in ("form", "note", "name", "tags"))
    if hit_any(text, FORM_MIXED_KW):
        return "混合", "高", "线上+线下信号"
    if hit_any(text, FORM_OFFLINE_KW):
        return "线下", "中", "线下/现场信号"
    if hit_any(text, FORM_ONLINE_KW):
        return "线上", "中", "线上/远程信号"
    return "线上", "低", "无明确形式信号，默认线上（Devpost/Kaggle 多为线上）"


def tag_elig(it):
    # name 必须纳入：赛事名里的「XX大学站/校园赛」是识别校赛专属的关键信号
    text = " ".join(str(it.get(k, "") or "") for k in ("name", "eligibility", "note", "tags"))
    name = str(it.get("name", "") or "")
    t = norm(text)
    # 【最高优先级】专属校赛站点：名称或正文出现「XX大学站/全校学生/本校学生」→ 纯学生限定。
    # 优先于「企业组/OPC组」等泛化赛道词，避免照抄主赛事介绍导致的误判（华为校赛站教训）。
    campus = hit_any(text, ELIG_CAMPUS_SITE_KW) + hit_any(name, ELIG_CAMPUS_ABBREV)
    if campus:
        return "纯学生限定", "高", "专属校赛站点信号：" + ",".join(campus[:2]) + "（优先级高于泛化赛道词）"
    # 强学生限定词 + 无社会通道信号
    strong_student = hit_any(text, ELIG_STUDENT_STRONG)
    social_signal = hit_any(text, ["社会组", "社会人士", "在职", "面向全社会", "open to all", "所有人", "各界人士"])
    if strong_student and not social_signal:
        return "纯学生限定", "高", "强学生限定词：" + ",".join(strong_student[:2])
    if hit_any(text, ELIG_SOLO_KW) and not hit_any(text, ["团队", "可组队", "teams"]):
        return "仅个人可报", "中", "仅个人信号"
    # 企业·团队可报只在「仅限企业/企业专属」时判定；「企业组」常是多赛道之一（企业组/OPC组/高校组），
    # 那种情况是对所有人开放的，应落到下面的「所有人可报」，不可误判为仅企业。
    team_exclusive = hit_any(text, ["仅限企业", "仅企业", "企业专属", "企业组专属", "企业团队专属",
                                     "限apn", "限 aws partner", "限aws partner", "must be an aws partner",
                                     "employees of", "employed by"])
    if team_exclusive:
        return "企业·团队可报", "高", "企业专属限定：" + ",".join(team_exclusive[:2])
    if hit_any(text, ELIG_SOCIAL_KW):
        return "社会组可报", "中", "社会组信号"
    if hit_any(text, ELIG_OPEN_KW):
        return "所有人可报", "中", "开放信号"
    return "所有人可报", "低", "无明确限定信号，默认开放"



def tag_regions(it, scope):
    text = " ".join(str(it.get(k, "") or "") for k in ("name", "note", "tags", "scope"))
    if scope in SINGLE_REGION:
        return [scope]
    out = []
    for label, kws in REGION_KW:
        if hit_any(text, kws):
            if label not in out:
                out.append(label)
    return out[:4] if out else [scope if scope in SINGLE_REGION else "全国"]


def tag_theme(it):
    """主题多标签：返回 (标签列表, 置信度, 依据)。最多取 3 个；无命中归「综合AI」。"""
    text = " ".join(str(it.get(k, "") or "") for k in ("name", "tags", "note", "eligibility", "form"))
    hits = []
    for label, kws in THEME_KW:
        h = hit_any(text, kws)
        if h:
            hits.append((label, h))
    if not hits:
        return ["综合AI"], "低", "无主题词命中，默认综合AI"
    labels = [h[0] for h in hits][:3]
    conf = "高" if len(hits) >= 2 else "中"
    return labels, conf, "主题词：" + "；".join(f"{l}({','.join(h[:2])})" for l, h in hits[:3])


# ---------------- 主流程 ----------------
FIELDS = ["scope", "form", "eligibility", "perks", "regions", "theme"]


# ---------------- 回归样例集（改规则必跑；含全部历史误判） ----------------
REGRESSION_CASES = [
    ("华为校赛站误判(校名站=纯学生)", {"name": "华为智能体创新赛·西安邮电大学站", "note": "参赛对象：全校本科生、研究生"},
     {"eligibility": "纯学生限定"}),
    ("AWS MSP 美元≠海外", {"name": "AWS MLS Summit", "note": "奖金6.4万美元，全球开放报名"},
     {"scope": "不限"}),
    ("NFL 本科生队≠纯学生", {"name": "NFL Big Data Bowl", "note": "参赛者为本科生队，open to all"},
     {"eligibility": "所有人可报"}),
    ("PayPal 全龄全球线上", {"name": "PayPal AI Hackathon", "note": "Above legal age of majority, all countries, online"},
     {"eligibility": "所有人可报", "scope": "不限", "form": "线上"}),
    ("Kaggle=海外", {"name": "Kaggle Competition", "note": "", "tags": ["kaggle"]},
     {"scope": "国外"}),
    ("天池=国内", {"name": "天池AI大赛", "note": "阿里云天池平台"},
     {"scope": "国内"}),
    ("差旅全包", {"name": "XX黑客松", "note": "报销路费，提供住宿和餐饮"},
     {"perks": "全包"}),
    ("仅包路费", {"name": "YY大赛", "note": "报销往返交通，食宿自理"},
     {"perks": "包路费"}),
    ("明示不包", {"name": "ZZ挑战赛", "note": "差旅费用自理"},
     {"perks": "不包"}),
    ("混合形式", {"name": "AA创新赛", "note": "线上初赛，线下决赛"},
     {"form": "混合"}),
    ("英文纯学生", {"name": "Student Hackathon 2026", "note": "students only, must be a student"},
     {"eligibility": "纯学生限定"}),
    ("英文差旅全包", {"name": "Global AI Challenge", "note": "travel covered, free accommodation and meals"},
     {"perks": "全包"}),
    ("主题-智能体", {"name": "Multi-Agent 黑客松", "note": "构建自主智能体应用"},
     {"theme": ["智能体"]}),
    ("主题-大模型", {"name": "LLM 应用创新赛", "note": "基于大语言模型构建应用"},
     {"theme": ["大模型"]}),
]


def run_selftest():
    ok = 0
    fails = []
    for desc, item, expect in REGRESSION_CASES:
        scope, _, _ = tag_scope(item)
        form, _, _ = tag_form(item)
        elig, _, _ = tag_elig(item)
        perks, _, _ = tag_perks(item)
        theme, _, _ = tag_theme(item)
        got = {"scope": scope, "form": form, "eligibility": elig, "perks": perks, "theme": theme}
        bad = {k: (v, got.get(k)) for k, v in expect.items() if got.get(k) != v}
        if not bad:
            ok += 1
            print(f"[PASS] {desc}")
        else:
            fails.append(desc)
            detail = "；".join(f"{k} 期望[{v}] 实际[{g}]" for k, (v, g) in bad.items())
            print(f"[FAIL] {desc} -> {detail}")
    print(f"\n回归结果：{ok}/{len(REGRESSION_CASES)} 通过")
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser(description="AI 赛事规则引擎自动打标器")
    ap.add_argument("--data", default="output/events_data.json", help="赛事数据 JSON 路径")
    ap.add_argument("--report", default=None, help="打标报告输出路径（Markdown）")
    ap.add_argument("--write", action="store_true", help="写回 JSON（默认仅填空缺，不覆盖人工值）")
    ap.add_argument("--force", action="store_true", help="强制用规则结果覆盖已有字段（配合 --write）")
    ap.add_argument("--selftest", action="store_true", help="跑回归样例集（含全部历史误判），不读数据文件")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(run_selftest())

    if not os.path.exists(args.data):
        sys.stderr.write(f"找不到数据文件：{args.data}\n")
        sys.exit(1)
    with open(args.data, "r", encoding="utf-8") as f:
        data = json.load(f)

    report = ["# 自动打标报告（规则引擎）", "",
              f"- 数据文件：{args.data}",
              f"- 模式：{'写回(' + ('强制覆盖' if args.force else '仅填空缺') + ')' if args.write else '仅预演(dry-run)'}",
              "- 说明：perks 为正向优点标签，不参与任何剔除/收录判定。", ""]
    changed = 0
    low_conf = []

    for i, it in enumerate(data.get("events", []), 1):
        name = it.get("name", "")[:26]
        scope, sc, _swhy = tag_scope(it)
        form, fc, _fwhy = tag_form(it)
        elig, ec, _ewhy = tag_elig(it)
        perks, pc, pwhy = tag_perks(it)
        regions = tag_regions(it, scope)
        theme, tmc, _twhy = tag_theme(it)
        inferred = {"scope": scope, "form": form, "eligibility": elig, "perks": perks, "regions": regions,
                    "theme": theme}
        conf = {"scope": sc, "form": fc, "eligibility": ec, "perks": pc, "theme": tmc}

        applied = {}
        for k in FIELDS:
            old = it.get(k)
            empty = old is None or old == "" or old == [] or (k == "perks" and old == "未标注")
            if args.force or empty:
                it[k] = inferred[k]
                applied[k] = (old, inferred[k])
                changed += 1
        if pc == "低":
            low_conf.append(f"{i}. {name} — {pwhy}")

        report.append(f"## {i}. {name}")
        report.append(f"- scope={scope}({sc}) ｜ form={form}({fc}) ｜ eligibility={elig}({ec}) ｜ **perks={perks}({pc})** ｜ theme={','.join(theme)}({tmc})")
        report.append(f"- 区域：{', '.join(regions)}")
        report.append(f"- perks 依据：{pwhy}")
        if applied:
            report.append("- 已应用：" + "；".join(f"{k}: {o or '空'}→{n}" for k, (o, n) in applied.items()))
        else:
            report.append("- 已有人工标注，未改动。")
        report.append("")

    if low_conf:
        report += ["## ⚠ 需人工复核（低置信）", ""] + [f"- {x}" for x in low_conf] + [""]
    report += ["## 外地友好分布", ""]
    from collections import Counter
    c = Counter(it.get("perks", "未标注") for it in data.get("events", []))
    for k, v in c.most_common():
        report.append(f"- {k}: {v} 项")
    report.append("")

    text = "\n".join(report)
    if args.report:
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"打标报告：{args.report}")
    else:
        print(text)

    if args.write:
        with open(args.data, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"已写回 {args.data}（变更字段 {changed} 处）")
    else:
        print(f"[dry-run] 预演完成，可变更字段 {changed} 处（未写回；加 --write 生效）")


if __name__ == "__main__":
    main()
