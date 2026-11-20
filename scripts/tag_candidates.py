# -*- coding: utf-8 -*-
"""
AI 赛事百晓生 · 雷达候选自动打标流水线（第二步：夯实打标）
============================================================
把 global_event_radar / run.py 产出的 candidates_*.json 逐条打上分类标签：
  scope / form / eligibility / perks / regions / theme

流程（规则为主 + AI 复判兜底）：
  1. 字段适配：候选的 title/snippet/content/tags/raw → 打标器的 name/note/tags
  2. 规则引擎先打标（复用 auto_tag.tag_*），输出 标签 + 置信度 + 依据
  3. 分流：资格(硬门槛)低置信、或差旅仅泛提的候选 → 进入「待AI复核清单」，
     不冒充高置信；其余直接采用规则结果
  4. 输出 candidates_tagged_*.json + 打标报告 Markdown（含待复核清单，
     供执行本 skill 的 AI 按 rules.md 逐条复判后写回——即「LLM 兜底层」）

用法：
  python tag_candidates.py --candidates output/candidates_20261119.json --out output
"""
import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auto_tag as at  # noqa: E402


def adapt(item: dict) -> dict:
    """候选字段 → 打标器字段（title→name，snippet/content/raw→note）"""
    title = str(item.get("title") or "")
    snippet = str(item.get("snippet") or "")
    content = str(item.get("content") or "")
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
    raw_note = " ".join(str(raw.get(k) or "") for k in ("description", "about", "subtitle", "name")
                        if raw.get(k))
    note = " ".join(x for x in (title, snippet, content, raw_note) if x)
    tags = item.get("tags") or []
    return {
        "name": title,
        "note": note[:1500],
        "tags": " ".join(str(t) for t in tags),
        "eligibility": str(item.get("eligibility") or ""),
        "form": str(item.get("form") or ""),
        "scope": str(item.get("scope") or ""),
        "deadline": str(item.get("published_at") or ""),
    }


def tag_one(item: dict):
    """返回 (tags_info, pending_reasons)。tags_info 各维度带值/置信/依据。"""
    it = adapt(item)
    scope, sc, swhy = at.tag_scope(it)
    form, fc, fwhy = at.tag_form(it)
    elig, ec, ewhy = at.tag_elig(it)
    perks, pc, pwhy = at.tag_perks(it)
    regions = at.tag_regions(it, scope)
    theme, tmc, twhy = at.tag_theme(it)
    tags_info = {
        "scope": {"value": scope, "conf": sc, "why": swhy},
        "form": {"value": form, "conf": fc, "why": fwhy},
        "eligibility": {"value": elig, "conf": ec, "why": ewhy},
        "perks": {"value": perks, "conf": pc, "why": pwhy},
        "regions": {"value": regions},
        "theme": {"value": theme, "conf": tmc, "why": twhy},
    }
    # 分流规则：身份是硬门槛，低置信必须复核；差旅只泛提了词（没明示给不给）也复核
    pending_reasons = []
    if ec == "低":
        pending_reasons.append(f"资格低置信：{ewhy}")
    if pc == "低" and pwhy.startswith("仅泛提"):
        pending_reasons.append(f"差旅仅泛提：{pwhy}")
    return tags_info, pending_reasons


def flat_tags(tags_info: dict) -> dict:
    """扁平视图：{scope: 国内, form: 线上, ...}，便于筛选器直接消费"""
    return {k: v.get("value") for k, v in tags_info.items()}


# ---------------- 雷达发现报告 HTML（第三步：呈现） ----------------
SCOPE_COLOR = {"国内": "#c0392b", "国外": "#00838f", "不限": "#5b6b8c"}
SCOPE_BG = {"国内": "#fbeae8", "国外": "#e0f4f6", "不限": "#eef0f5"}
PERKS_COLOR = {"全包": "#8e44ad", "包路费": "#0066cc", "包食宿": "#1a7a1a",
               "不包": "#9aa0a6", "未标注": "#9aa0a6"}
PERKS_BG = {"全包": "#f3e6f8", "包路费": "#e7f0fb", "包食宿": "#e6f4ea",
            "不包": "#f1f2f4", "未标注": "#f1f2f4"}
CONF_COLOR = {"高": "#1a7a1a", "中": "#b25a00", "低": "#c0392b"}


def esc(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _pill(text, color, bg, title=""):
    t = f' title="{esc(title)}"' if title else ""
    return f'<span class="pill"{t} style="color:{color};background:{bg}">{esc(text)}</span>'


def _form_color(form: str) -> str:
    if "混合" in form or ("线上" in form and "线下" in form):
        return "#0066cc"
    if "线下" in form:
        return "#b25a00"
    return "#1a7a1a"


def _dist_rows(tagged) -> str:
    """把各维度分布渲染成概览行。"""
    out = []
    for dim, label in (("scope", "地区"), ("form", "形式"),
                       ("eligibility", "资格"), ("perks", "差旅")):
        c = Counter(t["tags_flat"].get(dim) for t in tagged)
        items = " ｜ ".join(f"{k} × {v}" for k, v in c.most_common())
        out.append(f'<div class="drow"><span class="dl">{label}</span>'
                   f'<span class="dv">{esc(items)}</span></div>')
    c = Counter((t["tags_flat"].get("theme") or ["综合AI"])[0] for t in tagged)
    items = " ｜ ".join(f"{k} × {v}" for k, v in c.most_common())
    out.append(f'<div class="drow"><span class="dl">主题</span>'
               f'<span class="dv">{esc(items)}</span></div>')
    return "".join(out)


def _candidate_card(i: int, t: dict) -> str:
    """单条候选卡片：六维徽章 + 来源/评分 + 摘要 + 评分依据 + 待复核原因。"""
    ti = t["auto_tags"]
    scope = str(ti["scope"]["value"])
    form = str(ti["form"]["value"])
    elig = str(ti["eligibility"]["value"])
    perks = str(ti["perks"]["value"])
    regions = ti["regions"]["value"] or []
    themes = ti["theme"]["value"] or ["综合AI"]
    conf = str(ti["eligibility"]["conf"])
    score = t.get("score", "")
    src = t.get("source") or t.get("engine") or ""
    pub = str(t.get("published_at") or "")[:10]
    metrics = t.get("metrics") or {}
    inter = metrics.get("interaction") or 0
    reasons = t.get("score_reasons") or []
    badges = "".join([
        _pill(f"地区:{scope}", SCOPE_COLOR.get(scope, "#5b6b8c"), SCOPE_BG.get(scope, "#eef0f5")),
        _pill(f"形式:{form}", _form_color(form), "#f0f4f8"),
        _pill(f"资格:{elig}", "#2a7a2a", "#eef7ee"),
        _pill(f"差旅:{perks}", PERKS_COLOR.get(perks, "#9aa0a6"),
              PERKS_BG.get(perks, "#f1f2f4"), "外地友好·优点标签，不影响收录"),
        _pill("区域:" + ("/".join(str(x) for x in regions) if regions else scope), "#7c3aed", "#f3ecff"),
        _pill("主题:" + "/".join(str(x) for x in themes), "#8a5a00", "#fff4e0"),
        _pill(f"置信:{conf}", CONF_COLOR.get(conf, "#555"), "#f5f5f5"),
    ])
    reason_html = ""
    if reasons:
        reason_html = ('<div class="why">评分依据：'
                       + esc("；".join(str(x) for x in reasons[:4])) + "</div>")
    pend = t.get("_pending") or []
    pend_html = ""
    if pend:
        pend_html = '<div class="pend">⚠ ' + esc("；".join(str(x) for x in pend)) + "</div>"
    return f'''<div class="card">
  <div class="idx">{i}</div>
  <div class="bd">
    <div class="ttl"><a href="{esc(t.get("url") or "#")}" target="_blank" rel="noopener">{esc(str(t.get("title") or "")[:90])}</a></div>
    <div class="meta">{badges}</div>
    <div class="sub">来源 {esc(str(src))} ｜ 评分 <b>{esc(score)}</b> ｜ 互动 {esc(inter)} ｜ {esc(pub)}</div>
    <div class="snip">{esc(str(t.get("snippet") or "")[:200])}</div>
    {reason_html}{pend_html}
  </div>
</div>'''


def build_report_html(result: dict) -> str:
    """雷达发现报告：按「规则高置信 / 待AI复核」两层呈现候选，自包含单文件。"""
    snap = result.get("snap", "")
    tagged = result.get("candidates") or []
    hi = [t for t in tagged if not t.get("_pending")]
    pd = [t for t in tagged if t.get("_pending")]
    hi_html = "".join(_candidate_card(i, t) for i, t in enumerate(hi, 1)) or \
        '<div class="empty">本轮候选全部低置信，均进入待复核区。</div>'
    pd_html = "".join(_candidate_card(i, t) for i, t in enumerate(pd, 1)) or \
        '<div class="empty">本轮无待复核候选——规则引擎对全部维度均有把握。</div>'
    gen_at = result.get("generated_at", "")
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI赛事雷达发现报告_{snap}</title>
<style>
*{{box-sizing:border-box;}}
body{{font-family:"Microsoft YaHei","PingFang SC",sans-serif;margin:0;background:#eef1f7;color:#1a1a2e;}}
.wrap{{max-width:860px;margin:0 auto;padding:0 16px 48px;}}
header{{background:linear-gradient(135deg,#1A1A2E 0%,#28365e 100%);color:#fff;padding:24px 28px 20px;border-radius:0 0 18px 18px;}}
header h1{{margin:0 0 6px;font-size:21px;letter-spacing:.5px;}}
header .sub{{color:#a9c7ff;font-size:12.5px;line-height:1.7;}}
header .sub b{{color:#00D4FF;}}
.stats{{background:#fff;border-radius:12px;padding:14px 16px;margin:16px 0;box-shadow:0 2px 10px rgba(20,40,80,.06);font-size:12.5px;}}
.drow{{display:flex;padding:4px 0;border-bottom:1px dashed #eef0f4;}}
.drow:last-child{{border-bottom:none;}}
.dl{{flex:0 0 52px;font-weight:bold;color:#1a1a2e;}}
.dv{{flex:1;color:#555;line-height:1.7;}}
h2{{font-size:16px;margin:24px 0 12px;padding-bottom:7px;border-bottom:2px solid #00D4FF;}}
h2 .cnt{{font-size:12px;color:#888;font-weight:normal;margin-left:8px;}}
.card{{display:flex;gap:14px;background:#fff;border-radius:14px;padding:15px;margin-bottom:12px;box-shadow:0 2px 12px rgba(20,40,80,.07);}}
.idx{{flex:0 0 34px;height:34px;width:34px;border-radius:50%;background:linear-gradient(135deg,#1A1A2E,#28365e);color:#fff;font-weight:bold;font-size:15px;display:flex;align-items:center;justify-content:center;}}
.pd .idx{{background:linear-gradient(135deg,#8a5a00,#c9922e);}}
.bd{{flex:1;min-width:0;}}
.ttl{{font-size:15px;line-height:1.45;word-break:break-word;}}
.ttl a{{color:#1a1a2e;text-decoration:none;}}
.ttl a:hover{{color:#0066cc;text-decoration:underline;}}
.meta{{margin:8px 0 6px;display:flex;flex-wrap:wrap;gap:6px;}}
.pill{{display:inline-block;font-weight:bold;font-size:11.5px;border-radius:20px;padding:3px 10px;}}
.sub{{font-size:12px;color:#777;margin:2px 0 6px;}}
.sub b{{color:#0066cc;}}
.snip{{font-size:12.5px;color:#555;line-height:1.65;}}
.why{{margin-top:7px;font-size:11.5px;color:#888;line-height:1.6;border-top:1px dashed #eef0f4;padding-top:6px;}}
.pend{{margin-top:7px;font-size:12px;color:#8a5a00;background:#fff7e8;border:1px solid #f0d9a8;border-radius:8px;padding:6px 10px;line-height:1.6;}}
.empty{{background:#fff;border:1px dashed #c9d3e6;border-radius:12px;padding:16px;font-size:13px;color:#666;line-height:1.7;}}
.guide{{background:#eef7ff;border:1px solid #bcdcff;border-radius:12px;padding:13px 16px;margin:16px 0;font-size:12.5px;line-height:1.8;color:#1a3a5c;}}
.guide b{{color:#0a4a8a;}}
footer{{text-align:center;color:#8a93a6;font-size:11.5px;padding:20px 12px 0;line-height:1.8;}}
</style></head><body>
<header><div class="wrap" style="padding-bottom:0;">
<h1>AI 赛事百晓生 · 雷达发现报告</h1>
<div class="sub">快照 <b>{esc(snap)}</b> ｜ 候选 <b>{len(tagged)}</b> 条 ｜ 规则高置信 <b>{len(hi)}</b> 条 ｜ 待AI复核 <b>{len(pd)}</b> 条<br>规则为主 + AI 复判兜底 ｜ 差旅福利为优点标签不参与剔除 ｜ 生成于 {esc(gen_at)}</div>
</div></header>
<div class="wrap">
<div class="stats">{_dist_rows(tagged)}</div>
<h2>① 规则高置信 <span class="cnt">{len(hi)} 条 · 各维度均有把握，可直接采用</span></h2>
{hi_html}
<h2>② 待 AI 复核 <span class="cnt">{len(pd)} 条 · 低置信不冒充高置信</span></h2>
{pd_html}
<div class="guide"><b>复核方法：</b>按 <b>references/rules.md</b> 逐条打开链接核实——重点确认「报名资格是否限定学生/地域」「差旅福利是否明确给出」。把结论写回 <b>candidates_tagged_*.json</b> 对应项的 auto_tags：conf 升为「高」、来源标 ai-review；确认不符合口径的移入剔除清单。</div>
<footer><b>AI 赛事百晓生</b> · 雷达发现报告 ｜ 上游：全球雷达 8 源聚合 ｜ 打标：规则引擎（六维）<br>本报告为候选层呈现，正式收录以 events_data.json 为准。</footer>
</div></body></html>'''


def main():
    ap = argparse.ArgumentParser(description="雷达候选自动打标流水线（规则为主 + AI 复判兜底）")
    ap.add_argument("--candidates", required=True, help="雷达输出 candidates_*.json 路径")
    ap.add_argument("--out", default="output", help="输出目录")
    ap.add_argument("--report", default=None, help="打标报告 md 路径（默认 <out>/tagged_report_<date>.md）")
    ap.add_argument("--html-out", default=None,
                    help="雷达发现报告 HTML 路径（默认 <out>/radar_discovery_<date>.html；传 none 跳过）")
    args = ap.parse_args()

    if not os.path.exists(args.candidates):
        sys.stderr.write(f"找不到候选文件：{args.candidates}\n")
        sys.exit(1)
    with open(args.candidates, "r", encoding="utf-8") as f:
        data = json.load(f)
    candidates = data.get("candidates") or data.get("results") or []
    meta = data.get("meta") or {}
    snap = str(data.get("snap") or meta.get("snap") or "")
    if not snap:
        ga = str(meta.get("generated_at") or "")
        snap = ga[:10] if len(ga) >= 10 else dt.date.today().strftime("%Y-%m-%d")
    snap_compact = snap.replace("-", "")

    tagged = []
    pending = []
    for c in candidates:
        tags_info, pending_reasons = tag_one(c)
        entry = dict(c)
        entry["auto_tags"] = tags_info
        entry["tags_flat"] = flat_tags(tags_info)
        entry["_pending"] = pending_reasons
        tagged.append(entry)
        if pending_reasons:
            pending.append({
                "title": str(c.get("title") or "")[:80],
                "url": c.get("url") or "",
                "reasons": pending_reasons,
                "excerpt": str(c.get("snippet") or "")[:300],
            })

    os.makedirs(args.out, exist_ok=True)
    out_json = os.path.join(args.out, f"candidates_tagged_{snap_compact}.json")
    result = {
        "snap": snap,
        "query": data.get("query"),
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_file": args.candidates,
        "count": len(tagged),
        "pending_count": len(pending),
        "note": "auto_tags 为规则引擎结果；pending 项需执行 skill 的 AI 按 rules.md 复判后写回",
        "candidates": tagged,
        "pending": pending,
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # ---------------- 报告 ----------------
    rep_path = args.report or os.path.join(args.out, f"tagged_report_{snap_compact}.md")
    lines = ["# 候选打标报告（规则为主 + AI 复判兜底）", "",
             f"- 候选文件：{args.candidates}",
             f"- 快照：{snap} ｜ 候选数：{len(tagged)} ｜ 待AI复核：{len(pending)}",
             "- 口径：perks 为正向优点标签不参与剔除；资格为硬门槛，低置信必须复核。", ""]

    for dim in ("scope", "form", "eligibility", "perks"):
        c = Counter(t["tags_flat"].get(dim) for t in tagged)
        lines.append(f"## {dim} 分布")
        for k, v in c.most_common():
            lines.append(f"- {k}: {v} 条")
        lines.append("")
    c = Counter(t["tags_flat"].get("theme", ["综合AI"])[0] for t in tagged)
    lines.append("## theme 分布（按主主题）")
    for k, v in c.most_common():
        lines.append(f"- {k}: {v} 条")
    lines.append("")

    lines.append("## 逐条明细")
    for i, t in enumerate(tagged, 1):
        ti = t["auto_tags"]
        lines.append(f"### {i}. {str(t.get('title') or '')[:70]}")
        lines.append(f"- {t.get('url') or ''}")
        lines.append(f"- scope={ti['scope']['value']}({ti['scope']['conf']}) ｜ form={ti['form']['value']}({ti['form']['conf']})"
                     f" ｜ elig={ti['eligibility']['value']}({ti['eligibility']['conf']}) ｜ perks={ti['perks']['value']}({ti['perks']['conf']})")
        lines.append(f"- theme={','.join(ti['theme']['value'])} ｜ regions={','.join(ti['regions']['value'])}")
        lines.append(f"- 依据：{ti['eligibility']['why']}；{ti['perks']['why']}")
        lines.append("")

    if pending:
        lines += ["## ⚠ 待AI复核清单（低置信，不冒充高置信）", ""]
        for i, p in enumerate(pending, 1):
            lines.append(f"{i}. **{p['title']}**")
            lines.append(f"   - 链接：{p['url']}")
            for r in p["reasons"]:
                lines.append(f"   - {r}")
            lines.append(f"   - 摘录：{p['excerpt']}")
        lines += ["", "复核方法：按 references/rules.md 逐条判断，把结论写回 candidates_tagged JSON 对应项的 auto_tags，"
                      "并把 conf 升为「高」、来源标 ai-review。"]

    with open(rep_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    html_path = args.html_out
    if html_path is None:
        html_path = os.path.join(args.out, f"radar_discovery_{snap_compact}.html")
    if html_path.strip().lower() != "none":
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(build_report_html(result))
        print(f"发现报告：{html_path}")

    print(f"打标完成：{len(tagged)} 条 → {out_json}")
    print(f"待AI复核：{len(pending)} 条")
    print(f"打标报告：{rep_path}")


if __name__ == "__main__":
    main()
