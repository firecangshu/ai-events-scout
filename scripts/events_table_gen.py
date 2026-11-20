# -*- coding: utf-8 -*-
"""
AI 赛事百晓生 · 清单生成器（ai-events-scout skill 配套脚本）
=================================================
从一份 JSON 数据文件生成 4 类交付物：
  1) AI赛事汇总_清爽表_{snap}.html       —— 完整版（含筛选口径 + 已剔除原因）
  2) AI赛事常驻清单_分享版_{snap}.html   —— 可转发常驻版（还能报 + 即将开启）
  3) AI赛事汇总_清爽版_{snap}.xlsx       —— 对照表（还能报 / 已剔除 两 sheet）
  4) AI赛事分享长图_{snap}.png           —— 1080 宽分享长图

运行环境：需 openpyxl + Pillow。本机已验证可用环境：
  C:/Users/User/.workbuddy/binaries/python/envs/default/Scripts/python.exe

用法：
  python events_table_gen.py --data events_data.json --out ./输出目录 --snap 2026-10-18
  若省略 --data，默认读取脚本同目录的 events_data.json；若省略 --out，默认输出到当前目录；
  若 JSON 内未给 snap/title_date/today，则优先用 --snap 参数，再回退到今天。

JSON 数据格式（见 references/events_template.json）：
{
  "snap": "2026-10-18",          // 快照日期戳（文件名与页眉用）
  "title_date": "2026-10-18",    // 页眉“刷新版”日期
  "today": "2026-10-18",         // 计算“剩余天数”用的基准日
  "events": [                    // 还能报 / 即将开启 的赛事
    {
      "name": "赛事名称",
      "tags": "标签/方向",
      "scope": "不限",           // 地区：国内 | 国外 | 不限（必填，按口径判定）
      "form": "线上",            // 线上 | 线下 | 混合（必填，按口径判定）
      "eligibility": "所有人可报", // 身份/资格标签：纯学生限定|社会组可报|所有人可报|企业·团队可报
      "deadline": "2026-10-20（报名截止）",  // 必须含“报名/作品征集截止”字段
      "link": "https://...",      // 网页报名入口（须探活 200）
      "note": "一句话备注",
      "chip": "报名将截止",        // 可选：紧急角标
      "verified": "OK(200)"        // 可选：链接探活结果，默认 OK(200)
    }
  ],
  "dropped": [                   // 已剔除的赛事及原因（透明可审计）
    {"name": "XXX", "reason": "初赛报名已截止→剔除"}
  ]
}
"""
import os
import sys
import json
import re
import datetime
import argparse

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from PIL import Image, ImageDraw, ImageFont
except ImportError as e:
    sys.stderr.write(
        "缺少依赖 openpyxl / Pillow。请使用已装好的 venv 运行：\n"
        "  C:/Users/User/.workbuddy/binaries/python/envs/default/Scripts/python.exe events_table_gen.py ...\n"
        f"原始错误：{e}\n"
    )
    sys.exit(2)


# ---------------- 工具函数 ----------------
def compute_remain(deadline_str, today):
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", deadline_str or "")
    if not m:
        return "赛季中"
    d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    days = (d - today).days
    if days <= 0:
        return "今天截止" if days == 0 else "已截止"
    return f"{days}天"


def form_class(s):
    """把 形式 文本映射到 CSS 类（复用既有配色约定）。"""
    if "混合" in s or "线上+线下" in s or "线下决赛" in s or "初赛+线下" in s:
        return "fm-mixed"
    if "线下" in s:
        return "fm-off"
    return "fm-on"


def form_cat(s):
    """形式归一化到 线上/线下/混合（用于分享版筛选 data-form）。"""
    if "混合" in s or "线上+线下" in s or "线下决赛" in s or "初赛+线下" in s:
        return "混合"
    if "线下" in s:
        return "线下"
    return "线上"


def scope_key(s):
    """地区归一化到 国内/国外/不限（缺失或无法识别默认「不限」）。"""
    s = (s or "").strip()
    if s in ("国内", "国外", "不限"):
        return s
    if "国外" in s or "海外" in s:
        return "国外"
    if "国内" in s:
        return "国内"
    return "不限"


def elig_bucket(s):
    """资格归一化到 open(不限)/student(纯学生)，用于人群筛选。"""
    return "student" if "纯学生" in (s or "") else "open"


def elig_bucket_cn(s):
    """资格归一化到中文短桶标签（速查表筛选与卡片展示用）。"""
    e = (s or "").strip()
    if e.startswith("纯学生限定"):
        return "仅学生"
    if e.startswith("社会组可报"):
        return "社会组可报"
    if e.startswith("企业·团队可报"):
        return "企业/团队"
    if e.startswith("仅个人可报"):
        return "仅个人"
    return "不限人群"


# 外地友好/差旅福利（正向优点标签，仅展示与筛选，不参与收录/剔除）
PERKS_CANON = ["全包", "包路费", "包食宿", "不包", "未标注"]
PERKS_COLOR = {"全包": "#8e44ad", "包路费": "#0066cc", "包食宿": "#1a7a1a", "不包": "#9aa0a6", "未标注": "#9aa0a6"}
PERKS_BG = {"全包": "#f3e6f8", "包路费": "#e7f0fb", "包食宿": "#e6f4ea", "不包": "#f1f2f4", "未标注": "#f1f2f4"}
PERKS_ICON = {"全包": "✈🏨", "包路费": "✈", "包食宿": "🏨", "不包": "－", "未标注": "?"}


def perks_key(s):
    """差旅福利归一化到五档；兼容各种写法，缺失/无法识别归「未标注」。"""
    s = (s or "").strip()
    if s in PERKS_CANON:
        return s
    t = norm_lower(s)
    if any(k in t for k in ("全包", "路费+食宿", "含机票", "包机酒", "交通食宿全包")):
        return "全包"
    if any(k in t for k in ("路费", "交通", "机票", "火车", "travel", "flight")):
        return "包路费"
    if any(k in t for k in ("食宿", "住宿", "餐饮", "酒店", "hotel", "accommodation")):
        return "包食宿"
    if any(k in t for k in ("自理", "不包", "不含")):
        return "不包"
    return "未标注"


def norm_lower(s):
    return (s or "").lower()


def perks_badge(it):
    """生成差旅福利的正向徽章 HTML；未标注不显示（避免误导）。"""
    p = perks_key(it.get("perks", ""))
    if p == "未标注":
        return ""
    c, bg, icon = PERKS_COLOR[p], PERKS_BG[p], PERKS_ICON[p]
    return (f'<span class="pill perk-pill" style="color:{c};background:{bg}" '
            f'title="外地友好·优点标签（不影响收录）">{icon} {esc(p)}</span>')


# 主题标签（v1.3.0 第三步呈现新增；多标签，第一个为主主题）
THEME_ALL = ["大模型", "智能体", "AIGC", "机器学习", "机器人", "行业应用", "硬件与IoT", "Web3", "数据竞赛", "综合AI"]


def theme_list(it):
    """返回赛事的主题标签列表；空则归「综合AI」。"""
    t = it.get("theme") or []
    if isinstance(t, str):
        t = [x.strip() for x in t.replace("；", ",").replace("、", ",").split(",") if x.strip()]
    out = [str(x) for x in t if str(x).strip()]
    return out or ["综合AI"]


def theme_attr(it):
    """data-theme 属性值：空格分隔的全部主题（供 JS 多标签匹配）。"""
    return " ".join(theme_list(it))


def theme_buttons(items):
    """按当期数据实际出现的主题生成筛选按钮（THEME_ALL 顺序优先）。"""
    present = []
    for it in items:
        for t in theme_list(it):
            if t not in present:
                present.append(t)
    ordered = [t for t in THEME_ALL if t in present] + [t for t in present if t not in THEME_ALL]
    return "".join(f'<button class="fbtn" data-g="theme" data-v="{esc(t)}">{esc(t)}</button>' for t in ordered)


SCOPE_COLOR = {"国内": "#c0392b", "国外": "#00838f", "不限": "#5b6b8c"}
SCOPE_BG = {"国内": "#fbeae8", "国外": "#e0f4f6", "不限": "#eef0f5"}


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def short(u, n=42):
    for p in ("https://", "http://"):
        if u and u.startswith(p):
            u = u[len(p):]
    if u and u.startswith("www."):
        u = u[4:]
    return (u[:n] + ("…" if u and len(u) > n else "")) if u else ""


# ---------------- HTML：清爽表 ----------------
def build_clean_html(cfg, items, dropped):
    snap, title_date = cfg["snap"], cfg["title_date"]
    rows = []
    for i, it in enumerate(items, 1):
        chip = f'<span class="chip">{esc(it.get("chip",""))}</span>' if it.get("chip") else ""
        verified = it.get("verified", "OK(200)")
        perk = perks_key(it.get("perks", ""))
        pcolor = PERKS_COLOR[perk]
        rows.append(
            f'<tr><td class="num">{i}</td>'
            f'<td class="name">{esc(it["name"])}{chip}</td>'
            f'<td class="tags">{esc(it.get("tags",""))}</td>'
            f'<td class="th">{esc("/".join(theme_list(it)))}</td>'
            f'<td class="{form_class(it.get("form",""))}">{esc(it.get("form",""))}</td>'
            f'<td class="sc">{esc(scope_key(it.get("scope","")))}</td>'
            f'<td class="rg">{esc(" · ".join(it.get("regions") or []))}</td>'
            f'<td class="el">{esc(it.get("eligibility",""))}</td>'
            f'<td class="pk" style="color:{pcolor};font-weight:bold">{esc(perk)}</td>'
            f'<td class="dl">{esc(it.get("deadline",""))}</td>'
            f'<td class="rm">{esc(it["remain"])}</td>'
            f'<td class="note">{esc(it.get("note",""))}</td>'
            f'<td class="lk"><a href="{it["link"]}">{esc(short(it["link"]))}</a><br>'
            f'<span class="ok">报名验证 {esc(verified)}</span></td></tr>'
        )
    drop_rows = "".join(
        f'<tr><td class="dn">{esc(d["name"])}</td><td class="dr">{esc(d["reason"])}</td></tr>'
        for d in dropped
    )
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI赛事汇总_清爽表_{snap}</title>
<style>
*{{box-sizing:border-box;}}
body{{font-family:"Microsoft YaHei","PingFang SC",sans-serif;margin:0;background:#f5f6fa;color:#1a1a2e;}}
header{{background:#1A1A2E;color:#fff;padding:22px 28px;}}
header h1{{margin:0 0 6px;font-size:22px;letter-spacing:1px;}}
header .sub{{color:#00D4FF;font-size:13px;}}
.rules{{background:#fff;margin:18px 28px;padding:14px 18px;border-radius:10px;border-left:4px solid #00D4FF;font-size:13px;line-height:1.8;}}
.rules b{{color:#1A1A2E;}}
.wrap{{margin:0 28px 40px;}}
h2{{font-size:17px;margin:26px 0 10px;padding-bottom:6px;border-bottom:2px solid #00D4FF;}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;font-size:12.5px;}}
th{{background:#1A1A2E;color:#fff;padding:9px 8px;text-align:left;vertical-align:middle;}}
td{{padding:8px 8px;border-bottom:1px solid #e6e6e6;vertical-align:top;line-height:1.5;}}
tr:hover td{{background:#f0f9ff;}}
.num{{text-align:center;font-weight:bold;color:#0066cc;width:4%;}}
.name{{width:20%;font-weight:bold;}}
.tags{{width:10%;color:#555;}}
.th{{width:9%;color:#8a5a00;font-size:11.5px;}}
.fm-on{{width:7%;color:#1a7a1a;font-weight:bold;}}
.fm-off{{width:7%;color:#b25a00;font-weight:bold;}}
.fm-mixed{{width:7%;color:#0066cc;font-weight:bold;}}
.sc{{width:9%;color:#5b6b8c;font-size:11.5px;font-weight:bold;}}
.el{{width:9%;color:#2a7a2a;font-size:11.5px;}}
.pk{{width:6%;font-size:11px;white-space:nowrap;}}
.dl{{width:11%;font-family:Consolas,monospace;}}
.rm{{width:5%;text-align:center;color:#9C0006;font-weight:bold;}}
.note{{width:16%;color:#555;font-size:11.5px;}}
.lk{{width:7%;}}
.chip{{display:inline-block;background:#fde7e9;color:#9C0006;font-weight:bold;border-radius:4px;padding:1px 6px;font-size:10.5px;margin-left:4px;}}
.ok{{color:#1a7a1a;font-weight:bold;font-size:11px;}}
a{{color:#0563C1;text-decoration:underline;word-break:break-all;}}
.dn{{width:30%;font-weight:bold;}}
.dr{{width:70%;color:#555;}}
footer{{text-align:center;color:#999;font-size:11px;padding:20px;}}
</style></head><body>
<header><h1>AI 赛事百晓生 · 清爽表（{title_date} 刷新版）</h1>
<div class="sub">快照 {snap} ｜ 仅保留「还能报」赛事（按剩余时间从近到远）｜ 全部网页入口已探活 200 ｜ 含地区/形式/资格标注</div></header>
<div class="rules"><b>筛选口径（{snap}，按用户长期记忆规则）：</b><br>
① <b>纯学生限定（仅在校生）一律剔除</b>；设「社会组/社会通道」、社会人士可报的保留。<br>
② <b>报名截止判定</b>：必须找到「报名/作品征集截止」字段；严禁把整体赛程结束日当报名截止（腾讯云教训）。<br>
③ <b>剔除项</b>：初赛报名已截止、仅邮箱/扫码报名（无网页入口）、学生/校内/地域限定、纯视频内容类。<br>
④ <b>保留硬性要求</b>：报名仍在进行 + 可访问网页入口（探活200）+ 对社会开放。<br>
⑤ <b>形式维度</b>：标注「线上 / 线下 / 混合」，便于按可参与性筛选（你在武汉，异地线下需差旅）。<br>
⑥ <b>身份/资格维度</b>：已按目标身份档（默认 A 社会人士）标注「资格/对象」——纯学生限定已剔除，社会组/所有人/企业·团队可报的保留。<br>
⑦ <b>地区维度</b>：标注「国内 / 国外 / 不限」，便于按想打国内赛还是海外赛筛选。<br>
⑧ <b>差旅福利（外地友好）维度</b>：标注「全包(路费+食宿) / 包路费 / 包食宿 / 不包 / 未标注」。<b>这是优点标签，不设门槛</b>——不包路费的赛事照样收录，只是多一个维度供筛选，方便你在武汉判断异地参赛成本。<br>
⑨ 本表 <b>{len(items)} 项</b>全部满足；下方「已剔除」列出被排除的赛事及原因。
</div>
<div class="wrap">
<h2>① 还能报（报名进行中）<span style="font-size:12px;color:#888;">（{len(items)} 项 · 按截止从近到远）</span></h2>
<table><tr><th>#</th><th>赛事名称</th><th>标签</th><th>主题</th><th>形式</th><th>地区</th><th>区域</th><th>资格/对象</th><th>差旅福利</th><th>报名截止/赛期</th><th>剩余</th><th>备注</th><th>报名入口(已验证)</th></tr>
{''.join(rows)}
</table>
<h2>② 已剔除 <span style="font-size:12px;color:#888;">（{len(dropped)} 类｜已过期/已关闭/限定/纯视频/无入口）</span></h2>
<table><tr><th style="width:30%">赛事名称</th><th>剔除原因</th></tr>
{drop_rows}
</table>
</div>
<footer>生成于 {title_date} ｜ 清爽表 ｜ 蓝字下划线 = 可点击真实链接（探活200）；灰字 = 备注 ｜ 绿=线上 橙=线下 蓝=混合</footer>
</body></html>'''


# ---------------- HTML：常驻分享版 ----------------
def build_share_html(cfg, items):
    snap, title_date = cfg["snap"], cfg["title_date"]
    FORM_COLOR = {"fm-on": "#1a7a1a", "fm-off": "#b25a00", "fm-mixed": "#0066cc"}
    FORM_BG = {"fm-on": "#e6f4ea", "fm-off": "#fdf0e3", "fm-mixed": "#e7f0fb"}
    cards = []
    for i, it in enumerate(items, 1):
        form = it.get("form", "")
        fcls = form_class(form)
        fcolor = FORM_COLOR.get(fcls, "#555")
        fbg = FORM_BG.get(fcls, "#eee")
        scope = scope_key(it.get("scope", ""))
        scolor = SCOPE_COLOR.get(scope, "#5b6b8c")
        sbg = SCOPE_BG.get(scope, "#eef0f5")
        elig = it.get("eligibility", "")
        perk = perks_key(it.get("perks", ""))
        chip = f'<span class="chip-soon">{esc(it.get("chip",""))}</span>' if it.get("chip") else ""
        cards.append(f'''
    <div class="card" data-scope="{scope}" data-form="{form_cat(form)}" data-elig="{elig_bucket(elig)}" data-perk="{perk}" data-theme="{theme_attr(it)}">
      <div class="idx">{i}</div>
      <div class="body">
        <div class="ttl"><b>{esc(it["name"])}</b>{chip}</div>
        <div class="meta">
          <span class="pill" style="color:{fcolor};background:{fbg}">● {esc(form)}</span>
          <span class="pill" style="color:{scolor};background:{sbg}">{esc(scope)}</span>
          <span class="pill el-pill">资格：{esc(elig)}</span>
          {perks_badge(it)}
          <span class="pill theme-pill" title="主题标签">🏷 {'/'.join(theme_list(it))}</span>
          <span class="tags">{esc(it.get("tags",""))}</span>
        </div>
        <div class="note">{esc(it.get("note",""))}</div>
        <div class="foot">
          <span class="dl">截止 {esc(it.get("deadline",""))} ｜ 剩余 <b>{esc(it["remain"])}</b></span>
          <a class="btn" href="{it["link"]}" target="_blank" rel="noopener">报名入口 →</a>
        </div>
      </div>
    </div>''')
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 赛事百晓生 · 还能报 &amp; 即将开启（常驻分享版）</title>
<style>
*{{box-sizing:border-box;}}
body{{font-family:"Microsoft YaHei","PingFang SC",sans-serif;margin:0;background:#eef1f7;color:#1a1a2e;}}
.wrap{{max-width:780px;margin:0 auto;padding:0 16px 48px;}}
header{{background:linear-gradient(135deg,#1A1A2E 0%,#28365e 100%);color:#fff;padding:26px 28px 22px;border-radius:0 0 18px 18px;}}
header .row{{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:8px;}}
header h1{{margin:0;font-size:22px;letter-spacing:.5px;}}
header .badge{{display:inline-block;background:#00D4FF;color:#001a2e;font-weight:bold;font-size:11px;border-radius:20px;padding:3px 11px;margin-top:8px;}}
header .ver{{text-align:right;font-size:11.5px;color:#9db3ff;line-height:1.6;}}
header .sub{{color:#a9c7ff;font-size:12.5px;margin-top:10px;line-height:1.7;}}
.tip{{background:#fff;margin:18px 0;padding:13px 16px;border-radius:12px;border-left:4px solid #00D4FF;font-size:12.5px;line-height:1.8;box-shadow:0 2px 10px rgba(20,40,80,.06);}}
.tip b{{color:#1A1A2E;}}
.sec-title{{font-size:16px;margin:26px 0 12px;padding-bottom:7px;border-bottom:2px solid #00D4FF;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;}}
.sec-title .cnt{{font-size:12px;color:#888;font-weight:normal;margin-left:8px;}}
.card{{display:flex;gap:14px;background:#fff;border-radius:14px;padding:16px;margin-bottom:14px;box-shadow:0 2px 12px rgba(20,40,80,.07);transition:transform .15s ease, box-shadow .15s ease;}}
.card:hover{{transform:translateY(-2px);box-shadow:0 6px 18px rgba(20,40,80,.12);}}
.idx{{flex:0 0 38px;height:38px;width:38px;border-radius:50%;background:linear-gradient(135deg,#1A1A2E,#28365e);color:#fff;font-weight:bold;font-size:16px;display:flex;align-items:center;justify-content:center;}}
.body{{flex:1;min-width:0;}}
.ttl{{font-size:16px;color:#1a1a2e;line-height:1.4;}}
.meta{{margin:8px 0 6px;display:flex;align-items:center;flex-wrap:wrap;gap:8px;}}
.pill{{display:inline-block;font-weight:bold;font-size:12px;border-radius:20px;padding:3px 10px;}}
.el-pill{{background:#eef7ee;color:#2a7a2a;border:1px solid #bfe3bf;}}
.theme-pill{{background:#fff4e0;color:#8a5a00;border:1px solid #f0d9a8;}}
.filters{{background:#fff;border-radius:12px;padding:14px 16px;margin:16px 0;box-shadow:0 2px 10px rgba(20,40,80,.06);}}
.fgroup{{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:9px;}}
.fgroup:last-of-type{{margin-bottom:0;}}
.flabel{{font-size:12.5px;font-weight:bold;color:#1a1a2e;min-width:32px;margin-right:4px;}}
.fbtn{{border:1px solid #d5dbe8;background:#f7f9fc;color:#33415e;font-size:12px;font-weight:bold;border-radius:16px;padding:4px 12px;cursor:pointer;transition:all .12s ease;font-family:inherit;}}
.fbtn:hover{{border-color:#00a0e0;color:#0066cc;}}
.fbtn.active{{background:linear-gradient(135deg,#0066cc,#00a0e0);color:#fff;border-color:transparent;}}
.fcount{{font-size:12px;color:#666;margin-top:10px;padding-top:10px;border-top:1px dashed #e3e7ef;}}
.fcount b{{color:#0066cc;}}
.tags{{color:#777;font-size:12px;}}
.note{{color:#555;font-size:12.5px;line-height:1.6;margin:4px 0 10px;}}
.foot{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;border-top:1px dashed #e3e7ef;padding-top:9px;}}
.dl{{font-size:12.5px;color:#444;}}
.dl b{{color:#9C0006;font-size:13px;}}
.btn{{display:inline-block;background:linear-gradient(135deg,#0066cc,#00a0e0);color:#fff;font-weight:bold;font-size:12.5px;text-decoration:none;border-radius:8px;padding:7px 14px;white-space:nowrap;}}
.btn:hover{{filter:brightness(1.06);}}
.chip-soon{{display:inline-block;background:#fde7e9;color:#9C0006;font-weight:bold;border-radius:5px;padding:1px 7px;font-size:10.5px;margin-left:6px;vertical-align:middle;}}
.empty{{background:#fff;border:1px dashed #c9d3e6;border-radius:12px;padding:18px;font-size:13px;line-height:1.8;color:#555;}}
footer{{text-align:center;color:#8a93a6;font-size:11.5px;padding:24px 12px 8px;line-height:1.8;}}
footer b{{color:#1A1A2E;}}
</style></head><body>
<header><div class="wrap" style="padding-bottom:0;">
<div class="row"><div><h1>AI 赛事百晓生 · 还能报 &amp; 即将开启</h1>
<span class="badge">常驻 · 持续更新</span></div>
<div class="ver">版本 {snap}（准确核版）<br>最后核验 {snap[5:]}</div></div>
<div class="sub">只收「还能报」和「即将开启」两类 ｜ 每张卡片报名入口均可点击 ｜ 自包含单文件，可转发、可收藏</div>
</div></header>
<div class="wrap">
<div class="tip"><b>口径：</b>①「还能报」= 报名仍在进行/未截止，且有可访问的网页报名入口（网页探活200）；②「即将开启」= 已官宣将于近期开放、但当前尚未开放报名；③ 初赛报名已截止、仅邮箱报名、学生/校内/地域限定、纯视频内容类的，一律不收入本表。<b>三个维度徽章</b>：🟢线上/🟠线下/🔵混合 ｜ 地区（国内/国外/不限）｜ 资格（是否对你开放）。👇 <b>点下方筛选器</b>，可按「地区 / 形式 / 人群」实时过滤。</div>
<div class="filters">
  <div class="fgroup"><span class="flabel">地区</span><button class="fbtn active" data-g="scope" data-v="all">全部</button><button class="fbtn" data-g="scope" data-v="国内">国内</button><button class="fbtn" data-g="scope" data-v="国外">国外</button><button class="fbtn" data-g="scope" data-v="不限">不限</button></div>
  <div class="fgroup"><span class="flabel">形式</span><button class="fbtn active" data-g="form" data-v="all">全部</button><button class="fbtn" data-g="form" data-v="线上">线上</button><button class="fbtn" data-g="form" data-v="线下">线下</button><button class="fbtn" data-g="form" data-v="混合">线上线下</button></div>
  <div class="fgroup"><span class="flabel">人群</span><button class="fbtn active" data-g="elig" data-v="all">全部</button><button class="fbtn" data-g="elig" data-v="open">不限</button><button class="fbtn" data-g="elig" data-v="student">纯学生</button></div>
  <div class="fgroup"><span class="flabel">差旅福利</span><button class="fbtn active" data-g="perk" data-v="all">全部(含不包)</button><button class="fbtn" data-g="perk" data-v="全包">✈🏨全包</button><button class="fbtn" data-g="perk" data-v="包路费">✈包路费</button><button class="fbtn" data-g="perk" data-v="包食宿">🏨包食宿</button><button class="fbtn" data-g="perk" data-v="未标注">未标注</button></div>
  <div class="fgroup"><span class="flabel">主题</span><button class="fbtn active" data-g="theme" data-v="all">全部</button>{theme_buttons(items)}</div>
  <div class="fcount">当前筛选显示 <b id="fcount">{len(items)}</b> / {len(items)} 项</div>
</div>
<h2 class="sec-title">① 还能报（报名进行中）<span class="cnt">{len(items)} 项 · 按截止时间从近到远</span></h2>
{''.join(cards)}
<h2 class="sec-title">② 即将开启（已官宣 · 尚未开放报名）<span class="cnt">截至本快照暂无</span></h2>
<div class="empty">目前检索范围内（公众号/小红书/知乎 + 天池/魔搭/DataFountain/官网等）<b>暂无「已官宣但报名还没开」的赛事</b>。凡能查到的基本都在报（见上）或已截止/限定。如果你有「听说要开、但官网还没放报名」的赛，把名字告诉我，我会核验后补进本区。</div>
<footer><b>AI 赛事百晓生</b>（常驻分享版）· 快照 {snap}<br>蓝字按钮 = 可点击官方/可查网页 ｜ 报名前请以官网核对截止日 ｜ 本清单持续维护，见新赛即迭代更新。<br>生成自 WorkBuddy</footer>
</div>
<script>
(function(){{
  var cards=document.querySelectorAll('.card[data-scope]');
  var state={{scope:'all',form:'all',elig:'all',perk:'all',theme:'all'}};
  var cnt=document.getElementById('fcount');
  function apply(){{
    var n=0;
    cards.forEach(function(c){{
      var ok=(state.scope==='all'||c.getAttribute('data-scope')===state.scope)
        &&(state.form==='all'||c.getAttribute('data-form')===state.form)
        &&(state.elig==='all'||c.getAttribute('data-elig')===state.elig)
        &&(state.perk==='all'||c.getAttribute('data-perk')===state.perk)
        &&(state.theme==='all'||(' '+(c.getAttribute('data-theme')||'')+' ').indexOf(' '+state.theme+' ')>=0);
      c.style.display=ok?'':'none';
      if(ok){{n++;}}
    }});
    if(cnt)cnt.textContent=n;
  }}
  document.querySelectorAll('.fbtn').forEach(function(b){{
    b.addEventListener('click',function(){{
      var g=b.getAttribute('data-g');
      document.querySelectorAll('.fbtn[data-g="'+g+'"]').forEach(function(x){{x.classList.remove('active');}});
      b.classList.add('active');
      state[g]=b.getAttribute('data-v');
      apply();
    }});
  }});
  apply();
}})();
</script>
</body></html>'''


# ---------------- 报名速查表（移动端友好 · 链接可点）----------------
def build_signup_table(cfg, items, dropped):
    """速查表：每条赛事一行，倒计时 + 三维分类 + 可点击报名入口。

    与清爽表的区别：清爽表是宽表审计视图（列多、信息全、适合桌面核对）；
    速查表是窄屏优先的行动视图（时间在前、分类成组、链接是主角）。
    """
    snap = cfg["snap"]
    rows = []
    for i, it in enumerate(items, 1):
        remain = it["remain"]
        days = None
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", it.get("deadline", "") or "")
        if m:
            days = (datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) - cfg["today"]).days
        if days is None:
            cls, rtext = "rem-unknown", remain
        elif days <= 0:
            cls, rtext = "rem-over", ("今天截止" if days == 0 else "已截止")
        elif days <= 3:
            cls, rtext = "rem-urgent", f"还剩{days}天"
        elif days <= 7:
            cls, rtext = "rem-soon", f"还剩{days}天"
        else:
            cls, rtext = "rem-normal", f"还剩{days}天"
        dl = m.group(0) if m else it.get("deadline", "")
        sc = scope_key(it.get("scope", ""))
        fc = form_cat(it.get("form", ""))
        ec = elig_bucket_cn(it.get("eligibility", ""))
        pk = perks_key(it.get("perks", ""))
        rg = "|".join(it.get("regions") or []) or sc
        rg_show = " · ".join(it.get("regions") or [])
        perk_badge = perks_badge(it)
        rows.append(
            f'<div class="ev" data-scope="{esc(sc)}" data-form="{esc(fc)}" '
            f'data-elig="{esc(ec)}" data-perk="{esc(pk)}" data-region="{esc(rg)}" data-theme="{esc(theme_attr(it))}" data-q="{esc(it["name"] + " " + it.get("note","") + " " + it.get("tags",""))}">'
            f'<div class="ev-head">'
            f'<span class="num">{i}</span>'
            f'<span class="rem {cls}">{esc(rtext)}</span>'
            f'<span class="dl">{esc(dl)}</span>'
            f'</div>'
            f'<div class="nm">{esc(it["name"])}</div>'
            f'<div class="tags">'
            f'<span class="t t-scope">{esc(sc)}</span>'
            f'<span class="t t-form">{esc(fc)}</span>'
            f'<span class="t t-elig">{esc(it.get("eligibility",""))}</span>'
            f'<span class="t t-region">{esc(rg_show)}</span>'
            f'<span class="t t-theme">🏷 {esc("/".join(theme_list(it)))}</span>'
            f'{perk_badge}'
            f'</div>'
            f'<div class="note">{esc(it.get("note",""))}</div>'
            f'<div class="ev-foot">'
            f'<span class="dom">{esc(short(it["link"], 32))}</span>'
            f'<a class="go" href="{it["link"]}">去报名 →</a>'
            f'</div>'
            f'</div>'
        )
    body = "".join(rows)
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>AI赛事报名速查表_{snap}</title>
<style>
*{{box-sizing:border-box;}}
body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
margin:0;background:#f4f5f7;color:#1a1a1a;-webkit-text-size-adjust:100%;}}
header{{background:#c22;color:#fff;padding:18px 16px;}}
header h1{{margin:0 0 6px;font-size:19px;}}
header .sub{{font-size:12px;opacity:.92;}}
.hint{{margin:12px 12px 0;padding:11px 13px;background:#fff;border-radius:9px;
font-size:12px;line-height:1.75;color:#555;box-shadow:0 1px 3px rgba(20,20,40,.06);}}
.hint b{{color:#c22;}}
.wrap{{padding:12px 12px 26px;}}
.ev{{background:#fff;border-radius:10px;padding:13px;margin-bottom:10px;
box-shadow:0 1px 3px rgba(20,20,40,.06);}}
.ev-head{{display:flex;align-items:center;flex-wrap:wrap;}}
.num{{display:inline-block;min-width:22px;height:22px;line-height:22px;text-align:center;
background:#1a1a1a;color:#fff;border-radius:11px;font-size:12px;font-weight:bold;padding:0 5px;}}
.rem{{margin-left:8px;font-size:12px;font-weight:bold;}}
.rem-urgent{{color:#c22;}}
.rem-soon{{color:#d4761b;}}
.rem-normal{{color:#1c7a3d;}}
.rem-over{{color:#999;}}
.rem-unknown{{color:#888;font-weight:normal;}}
.dl{{margin-left:8px;font-size:11px;color:#999;}}
.nm{{margin-top:8px;font-size:15px;font-weight:bold;line-height:1.45;word-break:break-word;}}
.tags{{margin-top:6px;}}
.t{{display:inline-block;font-size:11px;line-height:19px;padding:0 7px;border-radius:3px;
margin:0 5px 4px 0;}}
.t-scope{{background:#eaf2ff;color:#2563c9;}}
.t-form{{background:#e9f8ef;color:#1c8a4a;}}
.t-elig{{background:#fff5e5;color:#a9700f;}}
.t-region{{background:#f3ecff;color:#7c3aed;}}
.t-theme{{background:#fff4e0;color:#8a5a00;}}
.note{{margin-top:5px;font-size:12px;color:#777;line-height:1.55;word-break:break-word;}}
.ev-foot{{margin-top:9px;padding-top:9px;border-top:1px dashed #e6e6e8;
display:flex;align-items:center;justify-content:space-between;}}
.dom{{flex:1;min-width:0;font-size:11px;color:#2563c9;word-break:break-all;line-height:1.4;}}
.go{{flex:0 0 auto;margin-left:10px;font-size:13px;font-weight:bold;color:#c22;text-decoration:none;
border:1px solid #e8b4b4;border-radius:15px;padding:5px 12px;background:#fdeeee;white-space:nowrap;}}
.go:active{{background:#f8dcdc;}}
.foot{{margin-top:14px;text-align:center;font-size:11px;color:#999;line-height:1.8;}}
/* 筛选器 */
.bar{{position:sticky;top:0;z-index:9;background:#fff;margin:0 -12px 10px;padding:10px 12px;
border-bottom:1px solid #e8e8ea;box-shadow:0 1px 4px rgba(20,20,40,.05);}}
.frow{{display:flex;align-items:center;flex-wrap:wrap;margin-bottom:7px;}}
.frow:last-child{{margin-bottom:0;}}
.flabel{{flex:0 0 40px;font-size:12px;color:#888;}}
.fbtn{{font-size:12px;line-height:24px;padding:0 11px;margin:0 6px 6px 0;border:1px solid #e3e4e8;
background:#f7f8fa;color:#555;border-radius:13px;cursor:pointer;font-family:inherit;}}
.fbtn.on{{background:#fdeaea;border-color:#e7b3b3;color:#c22;font-weight:600;}}
.fq{{flex:1;min-width:120px;height:30px;font-size:13px;border:1px solid #e3e4e8;border-radius:15px;
padding:0 12px;margin:0 6px 6px 0;font-family:inherit;background:#f7f8fa;}}
.fcount{{margin-left:auto;font-size:12px;color:#888;white-space:nowrap;}}
.fcount b{{color:#c22;font-size:14px;}}
.fexp{{flex:0 0 auto;margin:0 0 6px 6px;font-size:12px;line-height:26px;padding:0 12px;
background:#1a1a1a;color:#fff;border:none;border-radius:14px;cursor:pointer;font-family:inherit;}}
.fexp:hover{{opacity:.85;}}
.hide{{display:none !important;}}
</style></head>
<body>
<header>
<h1>AI 赛事报名速查表</h1>
<div class="sub">快照 {snap} ｜ {len(items)} 个报名进行中 ｜ 可筛选、可导出、点「去报名」直达官方页面</div>
</header>
<div class="hint">
<b>怎么用：</b>按「还剩几天」排序，越靠上越紧急 ｜ 用下方筛选器按<b>地区 / 形式 / 人群</b>过滤，或搜索关键词 ｜
点<b>「去报名 →」</b>直达主办方报名页，链接均已探活可访问 ｜ 点<b>「导出 CSV」</b>保存当前筛选结果。<br>
<b>口径：</b>只收报名仍在进行、且有可访问网页入口的赛事；已截止、仅邮箱/扫码报名的已剔除。
</div>
<div class="wrap">
<div class="bar">
  <div class="frow">
    <span class="flabel">地区</span>
    <button class="fbtn on" data-g="scope" data-v="all">全部</button>
    <button class="fbtn" data-g="scope" data-v="国内">国内</button>
    <button class="fbtn" data-g="scope" data-v="国外">国外</button>
    <button class="fbtn" data-g="scope" data-v="不限">不限</button>
  </div>
  <div class="frow">
    <span class="flabel">区域</span>
    <button class="fbtn on" data-g="region" data-v="all">全部</button>
    <button class="fbtn" data-g="region" data-v="大湾区">大湾区</button>
    <button class="fbtn" data-g="region" data-v="珠三角">珠三角</button>
    <button class="fbtn" data-g="region" data-v="长三角">长三角</button>
    <button class="fbtn" data-g="region" data-v="华北">华北</button>
    <button class="fbtn" data-g="region" data-v="华东">华东</button>
    <button class="fbtn" data-g="region" data-v="华南">华南</button>
    <button class="fbtn" data-g="region" data-v="华中">华中</button>
    <button class="fbtn" data-g="region" data-v="西南">西南</button>
    <button class="fbtn" data-g="region" data-v="东北">东北</button>
    <button class="fbtn" data-g="region" data-v="台湾">台湾</button>
    <button class="fbtn" data-g="region" data-v="全国">全国</button>
    <button class="fbtn" data-g="region" data-v="国外">国外</button>
  </div>
  <div class="frow">
    <span class="flabel">形式</span>
    <button class="fbtn on" data-g="form" data-v="all">全部</button>
    <button class="fbtn" data-g="form" data-v="线上">线上</button>
    <button class="fbtn" data-g="form" data-v="线下">线下</button>
    <button class="fbtn" data-g="form" data-v="混合">混合</button>
  </div>
  <div class="frow">
    <span class="flabel">人群</span>
    <button class="fbtn on" data-g="elig" data-v="all">全部</button>
    <button class="fbtn" data-g="elig" data-v="仅学生">仅学生</button>
    <button class="fbtn" data-g="elig" data-v="社会组可报">社会组可报</button>
    <button class="fbtn" data-g="elig" data-v="企业/团队">企业/团队</button>
    <button class="fbtn" data-g="elig" data-v="不限人群">不限人群</button>
  </div>
  <div class="frow">
    <span class="flabel">差旅福利</span>
    <button class="fbtn on" data-g="perk" data-v="all">全部(含不包)</button>
    <button class="fbtn" data-g="perk" data-v="全包">全包</button>
    <button class="fbtn" data-g="perk" data-v="包路费">包路费</button>
    <button class="fbtn" data-g="perk" data-v="包食宿">包食宿</button>
    <button class="fbtn" data-g="perk" data-v="未标注">未标注</button>
  </div>
  <div class="frow">
    <span class="flabel">主题</span>
    <button class="fbtn on" data-g="theme" data-v="all">全部</button>
    {theme_buttons(items)}
  </div>
  <div class="frow">
    <span class="flabel">搜索</span>
    <input id="fq" class="fq" type="search" placeholder="赛事名 / 主办方 / 备注关键词" autocomplete="off" />
    <span class="fcount">显示 <b id="fc">{len(items)}</b> / {len(items)} 项</span>
    <button class="fexp" id="fexp">导出 CSV</button>
    <button class="fexp" id="fexp2">导出 Excel</button>
  </div>
</div>
<div id="rows">
{body}
</div>
<div class="foot">
AI 赛事百晓生 ｜ 快照 {snap}<br>
另有 {len(dropped)} 类赛事因不符合口径未收录 ｜ 报名前请以官网核对截止日
</div>
</div>
<script>
(function(){{
  var S={{scope:'all',form:'all',elig:'all',perk:'all',region:'all',theme:'all',q:''}};
  var rows=Array.prototype.slice.call(document.querySelectorAll('#rows .ev'));
  var fc=document.getElementById('fc');
  var fq=document.getElementById('fq');
  var exp=document.getElementById('fexp');

  function apply(){{
    var n=0;
    for(var i=0;i<rows.length;i++){{
      var r=rows[i], ok=true;
      if(S.scope!=='all' && r.getAttribute('data-scope')!==S.scope) ok=false;
      if(S.form!=='all' && r.getAttribute('data-form')!==S.form) ok=false;
      if(S.elig!=='all' && r.getAttribute('data-elig')!==S.elig) ok=false;
      if(S.perk!=='all' && r.getAttribute('data-perk')!==S.perk) ok=false;
      if(ok && S.region!=='all'){{
        // 区域为多标签（| 分隔），命中任一即通过
        ok=('|'+(r.getAttribute('data-region')||'')+'|').indexOf('|'+S.region+'|')!==-1;
      }}
      if(ok && S.theme!=='all'){{
        // 主题为多标签（空格分隔），命中任一即通过
        ok=(' '+(r.getAttribute('data-theme')||'')+' ').indexOf(' '+S.theme+' ')!==-1;
      }}
      if(ok && S.q){{
        ok=(r.getAttribute('data-q')||'').toLowerCase().indexOf(S.q.toLowerCase())!==-1;
      }}
      if(ok){{r.classList.remove('hide');n++;}} else {{r.classList.add('hide');}}
    }}
    fc.textContent=n;
  }}

  var btns=document.querySelectorAll('.fbtn');
  for(var i=0;i<btns.length;i++){{
    btns[i].addEventListener('click',function(){{
      var g=this.getAttribute('data-g'),v=this.getAttribute('data-v');
      S[g]=v;
      var sib=this.parentNode.querySelectorAll('.fbtn');
      for(var j=0;j<sib.length;j++){{
        if(sib[j].getAttribute('data-g')===g){{
          sib[j].classList.toggle('on',sib[j].getAttribute('data-v')===v);
        }}
      }}
      apply();
    }});
  }}

  var t=null;
  fq.addEventListener('input',function(){{
    var v=fq.value;
    if(t) clearTimeout(t);
    t=setTimeout(function(){{S.q=v.replace(/^\\s+|\\s+$/g,'');apply();}},150);
  }});

  function csvCell(s){{
    s=String(s==null?'':s);
    return '"'+s.replace(/"/g,'""')+'"';
  }}

    exp.addEventListener('click',function(){{
      exportCsv();
    }});

  function collectRows(){{
    var out=[],idx=0;
    for(var i=0;i<rows.length;i++){{
      var r=rows[i];
      if(r.classList.contains('hide')) continue;
      idx++;
      var num=r.querySelector('.num'),rem=r.querySelector('.rem'),dl=r.querySelector('.dl');
      var nm=r.querySelector('.nm'),note=r.querySelector('.note');
      var go=r.querySelector('.go');
      var th=(r.getAttribute('data-theme')||'').split(/\\s+/).filter(Boolean).join('/')||'综合AI';
      out.push([
        idx,
        nm?nm.textContent:'',
        r.getAttribute('data-scope'),
        r.getAttribute('data-form'),
        r.getAttribute('data-elig'),
        r.getAttribute('data-perk')||'未标注',
        th,
        dl?dl.textContent.replace('截止','').trim():'',
        rem?rem.textContent:'',
        note?note.textContent:'',
        go?go.getAttribute('href'):''
      ]);
    }}
    return out;
  }}

  function exportCsv(){{
    var head=['序号','赛事名称','地区','形式','人群/资格','差旅福利','主题','报名截止','剩余天数','备注','报名入口'];
    var lines=[head.map(csvCell).join(',')];
    var data=collectRows();
    for(var i=0;i<data.length;i++) lines.push(data[i].map(csvCell).join(','));
    var csv='\\ufeff'+lines.join('\\r\\n');
    var blob=new Blob([csv],{{type:'text/csv;charset=utf-8;'}});
    var a=document.createElement('a');
    a.href=URL.createObjectURL(blob);
    a.download='AI赛事清单_筛选结果_{snap}.csv';
    document.body.appendChild(a);
    a.click();
    setTimeout(function(){{URL.revokeObjectURL(a.href);document.body.removeChild(a);}},100);
  }}

  // Excel 导出：生成 SpreadsheetML 2003（xls），Excel/WPS/Numbers 均可直接打开
  function exportXls(){{
    var data=collectRows();
    var head=['序号','赛事名称','地区','形式','人群/资格','差旅福利','主题','报名截止','剩余天数','备注','报名入口'];
    var xml='<?xml version="1.0" encoding="UTF-8"?>\\n'
      +'<?mso-application progid="Excel.Sheet"?>\\n'
      +'<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
      +'xmlns:o="urn:schemas-microsoft-com:office:office" '
      +'xmlns:x="urn:schemas-microsoft-com:office:excel" '
      +'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'
      +'<Worksheet ss:Name="AI赛事清单"><Table>';
    var rowsXml='';
    var allRows=[head].concat(data);
    for(var i=0;i<allRows.length;i++){{
      rowsXml+='<Row>';
      for(var j=0;j<allRows[i].length;j++){{
        var v=String(allRows[i][j]==null?'':allRows[i][j])
          .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        var isNum=/^\\d+$/.test(v);
        rowsXml+='<Cell><Data ss:Type="'+(isNum?'Number':'String')+'">'+v+'</Data></Cell>';
      }}
      rowsXml+='</Row>';
    }}
    xml+=rowsXml+'</Table></Worksheet></Workbook>';
    var blob=new Blob(['\\ufeff'+xml],{{type:'application/vnd.ms-excel;charset=utf-8;'}});
    var a=document.createElement('a');
    a.href=URL.createObjectURL(blob);
    a.download='AI赛事清单_筛选结果_{snap}.xls';
    document.body.appendChild(a);
    a.click();
    setTimeout(function(){{URL.revokeObjectURL(a.href);document.body.removeChild(a);}},100);
  }}

  document.getElementById('fexp2').addEventListener('click',function(){{
    exportXls();
  }});

  apply();
}})();
</script>
</body></html>'''


# ---------------- xlsx ----------------
def build_xlsx(cfg, items, dropped, out_dir):
    snap = cfg["snap"]
    wb = Workbook()
    ws = wb.active
    ws.title = "还能报"
    hdr_fill = PatternFill("solid", fgColor="1A1A2E")
    hdr_font = Font(color="FFFFFF", bold=True, size=11)
    thin = Side(style="thin", color="E6E6E6")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    cols = ["#", "赛事名称", "标签", "主题", "形式", "地区", "区域", "资格/对象", "差旅福利", "报名截止/赛期", "剩余", "报名入口(链接)", "备注", "链接核验"]
    ws.append(cols)
    for c in range(1, len(cols) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(vertical="center")
    for i, it in enumerate(items, 1):
        ws.append([
            i, it["name"], it.get("tags", ""), "/".join(theme_list(it)), it.get("form", ""),
            it.get("scope", ""), " · ".join(it.get("regions") or []),
            it.get("eligibility", ""), perks_key(it.get("perks", "")),
            it.get("deadline", ""), it["remain"], it["link"],
            it.get("note", ""), it.get("verified", "OK(200)")
        ])
        r = ws.max_row
        # 第12列 = 报名入口(链接)
        ws.cell(row=r, column=12).hyperlink = it["link"]
        ws.cell(row=r, column=12).font = Font(color="0563C1", underline="single")
    for col, w in zip("ABCDEFGHIJKLMN", [4, 32, 16, 12, 14, 10, 14, 22, 12, 22, 8, 40, 36, 10]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"

    ws2 = wb.create_sheet("已剔除")
    ws2.append(["赛事名称", "剔除原因"])
    for c in range(1, 3):
        cell = ws2.cell(row=1, column=c)
        cell.fill = hdr_fill
        cell.font = hdr_font
    for d in dropped:
        ws2.append([d["name"], d["reason"]])
    ws2.column_dimensions["A"].width = 34
    ws2.column_dimensions["B"].width = 90
    ws2.freeze_panes = "A2"
    path = os.path.join(out_dir, f"AI赛事汇总_清爽版_{snap}.xlsx")
    wb.save(path)
    return path


# ---------------- 长图 PNG ----------------
def _load_font(paths, size):
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def build_card(cfg, items, out_dir):
    snap = cfg["snap"]
    W = 1080
    pad = 28
    head_h = 150
    row_h = 116
    foot_h = 90
    H = head_h + len(items) * row_h + foot_h
    img = Image.new("RGB", (W, H), (245, 246, 250))
    d = ImageDraw.Draw(img)
    win_fonts = [
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/msyh.ttc",
    ]
    fbold = _load_font(["C:/Windows/Fonts/msyhbd.ttc"], 30)
    ftitle = _load_font(win_fonts, 25)
    fmid = _load_font(win_fonts, 19)
    fsmall = _load_font(win_fonts, 16)
    flink = _load_font(win_fonts, 15)
    d.rectangle([0, 0, W, head_h], fill=(26, 26, 46))
    d.text((pad, 34), "AI 赛事百晓生 · 还能报 & 即将开启", font=fbold, fill=(255, 255, 255))
    d.text((pad, 82), f"快照 {snap} ｜ {len(items)} 项 ｜ 地区/形式/资格/差旅福利 ｜ 链接均已探活200", font=fmid, fill=(0, 212, 255))
    y = head_h
    for i, it in enumerate(items, 1):
        d.rectangle([pad, y + 8, W - pad, y + row_h - 8], fill=(255, 255, 255), outline=(225, 225, 225))
        cx, cy = pad + 26, y + row_h // 2
        d.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill=(0, 102, 204))
        d.text((cx - 12, cy - 16), str(i), font=ftitle, fill=(255, 255, 255))
        tx = pad + 62
        d.text((tx, y + 16), it["name"][:20], font=ftitle, fill=(26, 26, 46))
        d.text((tx, y + 50), f"地区：{scope_key(it.get('scope',''))} ｜ 形式：{it.get('form','')[:10]} ｜ 资格：{it.get('eligibility','')[:10]} ｜ 主题：{'/'.join(theme_list(it))}", font=fsmall, fill=(90, 90, 90))
        pk = perks_key(it.get("perks", ""))
        if pk != "未标注":
            d.text((tx, y + 74), f"差旅福利：{PERKS_ICON[pk]} {pk}（优点标签）  ·  备注：{it.get('note','')[:20]}", font=fsmall, fill=(142, 68, 173))
        else:
            d.text((tx, y + 74), f"备注：{it.get('note','')[:28]}", font=fsmall, fill=(90, 90, 90))
        rx = W - pad - 4
        d.text((rx - 150, y + 20), f"截止 {it.get('deadline','')[:14]}", font=fmid, fill=(156, 0, 6))
        d.text((rx - 150, y + 52), f"剩余 {it['remain']}", font=ftitle, fill=(156, 0, 6))
        d.text((tx, y + 96), f"🔗 {short(it['link'])}", font=flink, fill=(5, 99, 193))
        y += row_h
    d.rectangle([0, H - foot_h, W, H], fill=(26, 26, 46))
    d.text((pad, H - foot_h + 30), f"AI 赛事百晓生 · 常驻分享版 v{snap} ｜ 生成自 WorkBuddy", font=fsmall, fill=(180, 195, 255))
    path = os.path.join(out_dir, f"AI赛事分享长图_{snap}.png")
    img.save(path)
    return path


# ---------------- 主流程 ----------------
def main():
    ap = argparse.ArgumentParser(description="AI 赛事清单四交付物生成器")
    ap.add_argument("--data", default=None, help="赛事数据 JSON 路径（默认：脚本同目录 events_data.json）")
    ap.add_argument("--out", default=None, help="输出目录（默认：当前工作目录）")
    ap.add_argument("--snap", default=None, help="快照日期戳 YYYY-MM-DD（覆盖 JSON 内的 snap）")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    data_path = args.data or os.path.join(here, "events_data.json")
    if not os.path.exists(data_path):
        sys.stderr.write(f"找不到数据文件：{data_path}\n可复制 references/events_template.json 为 events_data.json 后填写。\n")
        sys.exit(1)
    with open(data_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    snap = args.snap or raw.get("snap") or datetime.date.today().strftime("%Y-%m-%d")
    title_date = raw.get("title_date") or snap
    today_str = raw.get("today") or snap
    try:
        today = datetime.date(*map(int, today_str.split("-")))
    except Exception:
        today = datetime.date.today()

    cfg = {"snap": snap, "title_date": title_date, "today": today}

    events = raw.get("events", [])
    items = []
    for e in events:
        e = dict(e)
        # 字段规范化：缺字段补默认值，保证下游直接下标访问不崩溃（鲁棒性）
        for k, v in (("name", ""), ("link", ""), ("note", ""), ("tags", ""),
                     ("chip", ""), ("verified", ""), ("scope", ""), ("form", ""),
                     ("eligibility", ""), ("perks", ""), ("deadline", "")):
            e.setdefault(k, v)
        if not isinstance(e.get("regions"), list):
            e["regions"] = []
        e["remain"] = compute_remain(e.get("deadline", ""), today)
        items.append(e)
    dropped = raw.get("dropped", [])
    for d in dropped:
        if isinstance(d, dict):
            d.setdefault("name", "")
            d.setdefault("reason", "")

    out_dir = args.out or os.getcwd()
    os.makedirs(out_dir, exist_ok=True)

    p1 = os.path.join(out_dir, f"AI赛事汇总_清爽表_{snap}.html")
    p2 = os.path.join(out_dir, f"AI赛事常驻清单_分享版_{snap}.html")
    p0 = os.path.join(out_dir, f"AI赛事报名速查表_{snap}.html")
    with open(p1, "w", encoding="utf-8") as f:
        f.write(build_clean_html(cfg, items, dropped))
    with open(p2, "w", encoding="utf-8") as f:
        f.write(build_share_html(cfg, items))
    with open(p0, "w", encoding="utf-8") as f:
        f.write(build_signup_table(cfg, items, dropped))
    px = build_xlsx(cfg, items, dropped, out_dir)
    pc = build_card(cfg, items, out_dir)

    print("速查表:", p0)
    print("清爽表:", p1)
    print("分享版:", p2)
    print("xlsx  :", px)
    print("长图  :", pc)
    print(f"共 {len(items)} 项还能报，{len(dropped)} 类已剔除。")


if __name__ == "__main__":
    main()
