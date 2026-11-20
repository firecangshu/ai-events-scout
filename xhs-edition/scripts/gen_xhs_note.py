# -*- coding: utf-8 -*-
"""小红书版赛事清单生成器（ai-events-scout xhs-edition）

从 data/events_data.json 产出一篇可直接发布的小红书图文笔记物料：
  1) cover.png              1080x1440 封面（避开信息流遮挡安全区）
  2) content_N.png          1080x1440 内容页，每页 5 条，序号连续
  3) content.md             标题候选 + 正文 + 话题标签 + 发布设置

平台硬约束内建在生成器里，另由 check_xhs.py 独立校验：
  标题 <=20 字 / 正文 <=1000 字 / 标签 <=10 个 / 图片 1-18 张统一 3:4
  正文与图片不得含链接或导流话术 / 需主动标识 AI 生成内容

用法：
  python gen_xhs_note.py --data data/events_data.json --out output --snap 2026-11-14
依赖：Pillow
注意：PNG 内不使用 emoji（中文字体不渲染彩色 emoji，会成豆腐块）。
"""
import os
import re
import sys
import json
import math
import argparse
import datetime

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as e:
    sys.stderr.write("缺少 Pillow: %s\n" % e)
    sys.exit(2)

W = 1080
H = 1440
CHUNK = 5

# 信息流遮挡安全区：顶部 150 / 底部 200 / 左右 60
SAFE_TOP = 150
SAFE_BOTTOM = 1240
SAFE_LEFT = 60
SAFE_RIGHT = 1020

C_BG = (255, 245, 247)
C_CARD = (255, 255, 255)
C_BORDER = (255, 210, 219)
C_RED = (255, 36, 66)
C_DARK = (43, 43, 43)
C_MUTED = (120, 120, 120)
C_ACCENT_BG = (255, 236, 240)

BOLD_FONTS = [
    "C:/Windows/Fonts/msyhbd.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]
REG_FONTS = [
    "C:/Windows/Fonts/msyh.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]


def load_font(candidates, size):
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    raise RuntimeError("未找到可用中文字体，已安装字体后重试；不以默认字体代替（会出豆腐块）")


fbig = load_font(BOLD_FONTS, 66)
ftitle = load_font(BOLD_FONTS, 30)
fname = load_font(BOLD_FONTS, 30)
fmid = load_font(REG_FONTS, 24)
fsmall = load_font(REG_FONTS, 22)
fcap = load_font(REG_FONTS, 20)
ftiny = load_font(REG_FONTS, 18)


def compute_remain(deadline_str, today):
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", deadline_str or "")
    if not m:
        return "赛季中"
    try:
        d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return "赛季中"
    days = (d - today).days
    if days < 0:
        return "已截止"
    if days == 0:
        return "今天截止"
    return "%d天" % days


def scope_key(s):
    s = (s or "").strip()
    if s in ("国内", "国外", "不限"):
        return s
    if "国外" in s or "海外" in s:
        return "国外"
    if "国内" in s:
        return "国内"
    return "不限"


def form_short(s):
    s = (s or "").split("（")[0].split("(")[0].strip()
    return s or "线上"


def has_offline(form):
    return "线下" in (form or "")


def elig_bucket(eligibility):
    """人群短桶标签：笔记内一眼可辨，完整资格限制只在表格产物中呈现。"""
    e = (eligibility or "").strip()
    if e.startswith("纯学生限定"):
        return "仅学生"
    if e.startswith("社会组可报"):
        return "社会组可报"
    if e.startswith("企业·团队可报"):
        return "企业/团队"
    if e.startswith("仅个人可报"):
        return "仅个人"
    return "不限人群"


def fit(draw, text, font, maxw, ellipsis="…"):
    """按像素宽度兜底截断；正常路径优先用 wrap 折行，不丢信息。"""
    text = text or ""
    if draw.textlength(text, font=font) <= maxw:
        return text
    res = text
    while len(res) > 1 and draw.textlength(res + ellipsis, font=font) > maxw:
        res = res[:-1]
    return res + ellipsis


def wrap(draw, text, font, maxw, max_lines=2):
    """按像素宽度折行，最多 max_lines 行。

    断行时优先退到最近的空格，避免把英文单词从中间腰斩；
    最后一行仍超宽才用 fit() 加省略号兜底。
    """
    text = text or ""
    if draw.textlength(text, font=font) <= maxw:
        return [text]
    lines = []
    remaining = text
    for _ in range(max_lines - 1):
        cut = len(remaining)
        while cut > 1 and draw.textlength(remaining[:cut].rstrip(), font=font) > maxw:
            cut -= 1
        prefix = remaining[:cut].rstrip()
        sp = prefix.rfind(" ")
        if sp > 0 and (len(prefix) - sp) < 20:
            prefix = prefix[:sp].rstrip()
        if not prefix:
            prefix = remaining[:cut]
        lines.append(prefix)
        remaining = remaining[len(prefix):].lstrip()
        if draw.textlength(remaining, font=font) <= maxw:
            break
    if remaining:
        lines.append(fit(draw, remaining, font, maxw))
    return lines[:max_lines]


def draw_cover(snap, events, out_path):
    img = Image.new("RGB", (W, H), C_BG)
    d = ImageDraw.Draw(img)
    n = len(events)
    n_online = sum(1 for e in events if form_short(e.get("form", "")).startswith("线上"))
    n_domestic = sum(1 for e in events if scope_key(e.get("scope", "")) == "国内")

    d.rectangle([0, 0, W, 12], fill=C_RED)

    # 主标题（顶部安全区内起排，字号 >=60px）
    y = 178
    d.text((SAFE_LEFT + 12, y), "2026 还能报的", font=fbig, fill=C_DARK)
    d.text((SAFE_LEFT + 12, y + 92), "AI 赛事清单", font=fbig, fill=C_RED)

    # 数量胶囊
    d.rounded_rectangle([SAFE_LEFT + 12, 380, SAFE_LEFT + 412, 452], radius=36, fill=C_RED)
    d.text((SAFE_LEFT + 34, 400), "共 %d 个 · 报名中" % n, font=fmid, fill=(255, 255, 255))

    # 事实框（陈述句，不使用营销钩子）
    d.rounded_rectangle([SAFE_LEFT, 490, SAFE_RIGHT, 690], radius=24,
                        fill=C_ACCENT_BG, outline=C_BORDER, width=2)
    d.text((SAFE_LEFT + 32, 522), "按报名截止从近到远排列", font=fmid, fill=C_DARK)
    d.text((SAFE_LEFT + 32, 574), "地区 · 形式 · 参赛资格 已标注", font=fmid, fill=C_RED)
    d.text((SAFE_LEFT + 32, 626), "混合与线下赛需留意现场差旅", font=fsmall, fill=C_MUTED)

    # 分类标签（身份档 C：含学生赛，故不写「社会组可报」这种单一档位标签）
    chips = ["黑客松", "Kaggle", "国内赛", "海外赛", "线上赛", "含学生赛"]
    x, y0 = SAFE_LEFT, 730
    pad, chh, gap = 18, 58, 16
    for c in chips:
        cw = int(d.textlength(c, font=fsmall)) + pad * 2
        if x + cw > SAFE_RIGHT:
            x = SAFE_LEFT
            y0 += chh + 18
        d.rounded_rectangle([x, y0, x + cw, y0 + chh], radius=chh // 2,
                            fill=C_CARD, outline=C_BORDER, width=2)
        d.text((x + pad, y0 + 17), c, font=fsmall, fill=C_RED)
        x += cw + gap

    # 统计条（真实计数）
    stats = ["%d 个报名中" % n, "%d 个线上" % n_online, "%d 个国内赛" % n_domestic]
    sy, sh, pad = 900, 62, 20
    ws = [int(d.textlength(s, font=fsmall)) + pad * 2 for s in stats]
    gap = 20
    sx = (W - (sum(ws) + gap * (len(stats) - 1))) // 2
    for s, cw in zip(stats, ws):
        d.rounded_rectangle([sx, sy, sx + cw, sy + sh], radius=sh // 2, fill=C_RED)
        d.text((sx + cw // 2, sy + sh // 2), s, font=fsmall,
               fill=(255, 255, 255), anchor="mm")
        sx += cw + gap

    d.text((SAFE_LEFT + 12, 1000), "下滑看完整清单（共 %d 个）" % n, font=fmid, fill=C_DARK)

    # 行动号召带（收在底部安全区内，含 AI 主动标识）
    by, bh = 1070, 160
    d.rounded_rectangle([SAFE_LEFT, by, SAFE_RIGHT, by + bh], radius=28,
                        fill=C_ACCENT_BG, outline=C_BORDER, width=2)
    d.text((W // 2, by + 46), "每周刷新 · 快照 " + snap, font=fmid, fill=C_DARK, anchor="mm")
    d.text((W // 2, by + 88), "图文由 AI 辅助生成", font=fcap, fill=C_MUTED, anchor="mm")
    d.text((W // 2, by + 122), "赛事信息以官方页面为准", font=ftiny, fill=C_MUTED, anchor="mm")

    img.save(out_path)
    return out_path


def draw_content(items, start_no, page, total_pages, snap, out_path):
    img = Image.new("RGB", (W, H), C_BG)
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, W, 100], fill=C_RED)
    d.text((SAFE_LEFT, 34), "还能报的 AI 赛事（%d/%d）" % (page, total_pages),
           font=ftitle, fill=(255, 255, 255))
    d.text((SAFE_RIGHT, 40), "快照 " + snap, font=ftiny, fill=(255, 255, 255), anchor="rm")

    top, bottom = 120, SAFE_BOTTOM
    n = len(items)
    # 统一按每页 CHUNK 条计算卡片高度，保证各页卡片等高；末页不足时余量留给页尾说明
    ch = (bottom - top) // CHUNK
    tw = SAFE_RIGHT - (SAFE_LEFT + 110) - 24

    for i, it in enumerate(items):
        no = start_no + i
        y = top + i * ch
        x = SAFE_LEFT
        cw = SAFE_RIGHT - SAFE_LEFT
        d.rounded_rectangle([x, y + 5, x + cw, y + ch - 5], radius=20,
                            fill=C_CARD, outline=C_BORDER, width=2)

        cx, cy = x + 52, y + ch // 2
        d.ellipse([cx - 28, cy - 28, cx + 28, cy + 28], fill=C_RED)
        d.text((cx, cy), str(no), font=ftitle, fill=(255, 255, 255), anchor="mm")

        tx = x + 110
        # 名称：折行，不丢信息
        lines = wrap(d, it.get("name", "未命名赛事"), fname, tw, max_lines=2)
        for k, ln in enumerate(lines):
            d.text((tx, y + 16 + k * 34), ln, font=fname, fill=C_DARK)
        ny = 16 + len(lines) * 34

        form = it.get("form", "")
        meta = "%s · %s" % (scope_key(it.get("scope", "")), form_short(form))
        if has_offline(form):
            meta += " · 需现场差旅"
        d.text((tx, y + ny + 6), fit(d, meta, fsmall, tw), font=fsmall, fill=C_MUTED)

        dl = re.search(r"\d{4}-\d{2}-\d{2}", it.get("deadline", ""))
        dl_text = dl.group(0) if dl else (it.get("deadline", "") or "")[:12]
        d.text((tx, y + ny + 40), "截止 " + dl_text, font=fsmall, fill=C_RED)
        d.text((tx + 330, y + ny + 40), "剩余 " + it.get("remain", ""),
               font=fsmall, fill=C_RED)

        # 人群：短桶标签，一目了然（完整资格限制见表格产物，笔记内不展开）
        elig = elig_bucket(it.get("eligibility", ""))
        d.text((tx, y + ny + 74), fit(d, "人群 " + elig, fcap, tw),
               font=fcap, fill=C_DARK)

        # 亮点：名称占 2 行时给 1 行，否则给 2 行，尽量不丢信息
        note = it.get("note", "") or ""
        note_lines = wrap(d, note, ftiny, tw, max_lines=(1 if len(lines) == 2 else 2))
        for k, nl in enumerate(note_lines):
            d.text((tx, y + ny + 106 + k * 24), nl, font=ftiny, fill=C_MUTED)

    # 末页卡片数不足时，用一行事实说明填补下方留白
    if page == total_pages:
        fy = top + n * ch + 44
        if fy < SAFE_BOTTOM - 30:
            d.text((W // 2, fy), "信息以官方页面为准 · 图文由 AI 辅助生成",
                   font=fcap, fill=C_MUTED, anchor="mm")

    img.save(out_path)
    return out_path


def build_content(snap, events, out_path):
    n = len(events)
    titles = [
        "2026还能报的%d个AI赛事" % n,
        "%d个AI赛事报名进行中" % n,
        "AI赛事清单：%d个报名中" % n,
    ]
    body = [
        "截至 %s，仍能报名的 AI 赛事共 %d 个，按报名截止从近到远排列。" % (snap, n),
        "",
        "图片里逐条列了赛事名称、地区、形式、参赛资格、报名截止、剩余天数，以及主办方与奖金信息。",
        "",
        "几点说明：",
        "形式分线上、线下、混合；混合与线下赛需留意现场差旅。",
        "参赛资格按官方参赛对象标注，含需依托法人单位、限合作伙伴、须用指定平台算力、年龄门槛等限制条件。",
        "地区分国内、国外、不限；中国台湾地区的赛事归入国内。",
        "报名前请到赛事官方页面确认赛程与资格，信息会随官方公告变化。",
        "",
        "本笔记图文由 AI 辅助生成，赛事信息以官方页面为准。",
    ]
    tags = ["#AI赛事", "#人工智能比赛", "#算法竞赛", "#AI黑客松",
            "#大模型", "#具身智能", "#Kaggle"]
    lines = [
        "# 小红书发布文案（快照 %s）" % snap,
        "",
        "## 标题（选一个）",
        "",
    ]
    for i, t in enumerate(titles, 1):
        lines.append("%d. %s" % (i, t))
    lines += ["", "## 正文", ""] + body + ["", "## 话题标签", "", " ".join(tags), "",
              "## 发布设置", "",
              "- 发布时勾选「内容自主声明 → 含 AI 生成内容」。",
              "- 图片顺序：cover.png 为封面，其后按 content_1.png 起依次上传。",
              "- 不添加站外链接、联系方式、二维码或引导跳转的话术。",
              ""]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_path


def main():
    ap = argparse.ArgumentParser(description="小红书版赛事清单生成器")
    ap.add_argument("--data", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--snap", default=None)
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    data_path = args.data or os.path.join(root, "data", "events_data.json")
    if not os.path.exists(data_path):
        sys.stderr.write("找不到数据文件: %s\n" % data_path)
        sys.exit(1)
    with open(data_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    snap = args.snap or raw.get("snap") or datetime.date.today().strftime("%Y-%m-%d")
    # today 与 snap 统一，避免换基准日后剩余天数算错
    if raw.get("today") and raw["today"] != snap:
        sys.stderr.write("提示: 数据 today=%s 与 snap=%s 不一致，本次按 snap 计算剩余天数\n"
                         % (raw["today"], snap))
    try:
        today = datetime.date(*map(int, snap.split("-")))
    except Exception:
        today = datetime.date.today()

    events = raw.get("events") or []
    for e in events:
        e["remain"] = compute_remain(e.get("deadline", ""), today)

    out_dir = args.out or os.path.join(root, "output")
    os.makedirs(out_dir, exist_ok=True)

    paths = [draw_cover(snap, events, os.path.join(out_dir, "cover.png"))]
    total = max(1, math.ceil(len(events) / CHUNK))
    for idx in range(total):
        chunk = events[idx * CHUNK:(idx + 1) * CHUNK]
        p = os.path.join(out_dir, "content_%d.png" % (idx + 1))
        paths.append(draw_content(chunk, idx * CHUNK + 1, idx + 1, total, snap, p))
    paths.append(build_content(snap, events, os.path.join(out_dir, "content.md")))

    for p in paths:
        print(p)
    print("已生成: 封面 1 张 + 内容 %d 张 + 文案 1 份（共 %d 个文件）"
          % (total, len(paths)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
