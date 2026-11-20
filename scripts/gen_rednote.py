# -*- coding: utf-8 -*-
"""小红书 redskill 交付物生成器（ai-events-scout skill 配套）
=========================================================
读取 events_data.json，产出小红书图文笔记物料：
  1) 小红书_封面_{snap}.png       1080x1440 大字钩子封面
  2) 小红书_内容_{snap}_N.png     1080x1440 每页 7 条，白底粉色卡片风
  3) 小红书_文案_{snap}.md         标题候选x3 + 正文 + 话题标签

用法：
  python gen_rednote.py --data events_data.json --out <目录> --snap 2026-11-14
依赖：Pillow（同 venv：C:/Users/User/.workbuddy/binaries/python/envs/default/Scripts/python.exe）
注意：PNG 内不使用 emoji（PIL 中文字体不渲染彩色 emoji，会成豆腐块）；emoji 仅保留在文案 md 供复制。
"""
import os, sys, json, re, argparse, datetime
from PIL import Image, ImageDraw, ImageFont

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as e:
    sys.stderr.write(f"缺少 Pillow：{e}\n")
    sys.exit(2)

W = 1080
SLIDE_H = 1440
COVER_H = 1440
CHUNK = 7

# 小红书配色
C_BG = (255, 245, 247)        # 浅粉白底
C_CARD = (255, 255, 255)
C_BORDER = (255, 210, 219)    # 浅粉边
C_RED = (255, 36, 66)         # 小红书红 #FF2442
C_DARK = (43, 43, 43)
C_MUTED = (140, 140, 140)
C_ACCENT_BG = (255, 236, 240)

win_fonts = ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc"]


def load_font(paths, size):
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


fb = load_font(["C:/Windows/Fonts/msyhbd.ttc"], 30)
fbig = load_font(["C:/Windows/Fonts/msyhbd.ttc"], 62)
ftitle = load_font(win_fonts, 30)
ftitle_s = load_font(win_fonts, 26)
fmid = load_font(win_fonts, 22)
fsmall = load_font(win_fonts, 19)
fcap = load_font(win_fonts, 17)


def compute_remain(deadline_str, today):
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", deadline_str or "")
    if not m:
        return "赛季中"
    d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    days = (d - today).days
    if days <= 0:
        return "今天截止" if days == 0 else "已截止"
    return f"{days}天"


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


def elig_short(s):
    s = re.sub(r"[（(].*?[）)]", "", s or "").strip()
    return s or "所有人可报"


def fit(draw, text, font, maxw, ellipsis="…"):
    if draw.textlength(text, font=font) <= maxw:
        return text
    res = text
    while len(res) > 1 and draw.textlength(res + ellipsis, font=font) > maxw:
        res = res[:-1]
    return res + ellipsis


def short(u, n=40):
    for p in ("https://", "http://"):
        if u and u.startswith(p):
            u = u[len(p):]
    if u and u.startswith("www."):
        u = u[4:]
    return (u[:n] + ("…" if u and len(u) > n else "")) if u else ""


def draw_cover(snap, events, out_path):
    img = Image.new("RGB", (W, COVER_H), C_BG)
    d = ImageDraw.Draw(img)
    n_items = len(events)
    n_online = sum(1 for e in events if form_short(e.get("form", "")).startswith("线上"))
    n_domestic = sum(1 for e in events if scope_key(e.get("scope", "")) == "国内")
    d.rectangle([0, 0, W, 14], fill=C_RED)
    # 主标题
    d.text((64, 100), "2026 还能报的", font=fbig, fill=C_DARK)
    d.text((64, 200), "AI 赛事清单", font=fbig, fill=C_RED)
    # 数量胶囊
    d.rounded_rectangle([64, 338, 64 + 380, 338 + 72], radius=36, fill=C_RED)
    d.text((86, 358), f"共 {n_items} 个 · 报名中", font=ftitle, fill=(255, 255, 255))
    # 钩子框
    d.rounded_rectangle([64, 460, W - 64, 680], radius=24, fill=C_ACCENT_BG, outline=C_BORDER, width=2)
    d.text((96, 495), "打工人副业 / 学生党冲奖", font=fmid, fill=C_DARK)
    d.text((96, 550), "这一篇就够了", font=fmid, fill=C_RED)
    d.text((96, 605), "含直达报名链接 · 按截止从近到远", font=fsmall, fill=C_MUTED)
    # 分类标签
    chips = ["黑客松", "Kaggle 全球赛", "国内企业赛", "海外 AI 赛", "线上为主", "附报名链接"]
    cx0, cy0 = 64, 760
    pad_x, gap_y = 18, 22
    chh = 62
    x, y = cx0, cy0
    for c in chips:
        w = int(d.textlength(c, font=fsmall)) + pad_x * 2
        if x + w > W - 64:
            x = cx0
            y += chh + gap_y
        d.rounded_rectangle([x, y, x + w, y + chh], radius=chh // 2, fill=C_CARD, outline=C_BORDER, width=2)
        d.text((x + pad_x, y + 20), c, font=fsmall, fill=C_RED)
        x += w + 16
    # 统计条（真实计数）
    stats = [f"{n_items} 个报名中", f"{n_online} 个线上", f"{n_domestic} 个国内赛"]
    sy, sh = 1000, 64
    pads = 20
    ws = [int(d.textlength(s, font=fsmall)) + pads * 2 for s in stats]
    gap = 22
    total_w = sum(ws) + gap * (len(stats) - 1)
    sx = (W - total_w) // 2
    for s, w in zip(stats, ws):
        d.rounded_rectangle([sx, sy, sx + w, sy + sh], radius=sh // 2, fill=C_RED)
        d.text((sx + w // 2, sy + sh // 2), s, font=fsmall, fill=(255, 255, 255), anchor="mm")
        sx += w + gap
    # 提示
    d.text((64, 1110), f"下滑看完整 {n_items} 个赛事清单", font=fmid, fill=C_DARK)
    # 底部行动号召带
    by, bh = 1180, 190
    d.rounded_rectangle([40, by, W - 40, by + bh], radius=28, fill=C_ACCENT_BG, outline=C_BORDER, width=2)
    d.text((W // 2, by + 70), "每周刷新 · 关注我不迷路", font=fmid, fill=C_DARK, anchor="mm")
    d.text((W // 2, by + 130), f"生成自 WorkBuddy ｜ 快照 {snap}", font=fcap, fill=C_MUTED, anchor="mm")
    img.save(out_path)
    return out_path


def draw_slide(items, page, total_pages, snap, out_path):
    if not items:
        return None
    img = Image.new("RGB", (W, SLIDE_H), C_BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 100], fill=C_RED)
    d.text((56, 30), f"还能报的 AI 赛事（{page}/{total_pages}）", font=ftitle, fill=(255, 255, 255))
    d.text((W - 320, 38), f"快照 {snap}", font=fcap, fill=(255, 255, 255))

    top = 128
    bottom = SLIDE_H - 64
    usable = bottom - top
    ch = usable // len(items)
    tw = W - 100 - 110  # 文本可用宽
    y = top
    for i, it in enumerate(items, 1):
        x = 50
        cw = W - 100
        d.rounded_rectangle([x, y + 6, x + cw, y + ch - 6], radius=20, fill=C_CARD, outline=C_BORDER, width=2)
        cx, cy = x + 46, y + ch // 2
        d.ellipse([cx - 26, cy - 26, cx + 26, cy + 26], fill=C_RED)
        d.text((cx - 14, cy - 22), str(i), font=ftitle, fill=(255, 255, 255))
        tx = x + 96
        # 名称（按宽度截断，避免溢出）
        name = fit(d, it["name"], ftitle, tw)
        d.text((tx, y + 20), name, font=ftitle, fill=C_DARK)
        # 元信息：地区 · 形式 · 资格
        meta = f"{scope_key(it.get('scope',''))} · {form_short(it.get('form',''))} · {elig_short(it.get('eligibility',''))}"
        d.text((tx, y + 64), meta, font=fsmall, fill=C_MUTED)
        # 截止 + 剩余（只取日期，避免括号被截断）
        rem = it.get("remain", "")
        m = re.search(r"\d{4}-\d{2}-\d{2}", it.get("deadline", ""))
        dl = m.group(0) if m else it.get("deadline", "")[:12]
        d.text((tx, y + 98), f"截止 {dl}", font=fsmall, fill=C_RED)
        d.text((tx + 430, y + 98), f"剩余 {rem}", font=fsmall, fill=C_RED)
        # 亮点
        note = fit(d, "· " + it.get("note", ""), fcap, tw)
        d.text((tx, y + 132), note, font=fcap, fill=C_MUTED)
        y += ch
    d.text((56, SLIDE_H - 46), "AI 赛事百晓生 · 生成自 WorkBuddy", font=fcap, fill=C_MUTED)
    d.text((W - 200, SLIDE_H - 46), f"{page}/{total_pages}", font=fcap, fill=C_MUTED)
    img.save(out_path)
    return out_path


def build_md(snap, events, out_path):
    lines = []
    lines.append(f"# 小红书文案 · AI 赛事清单（快照 {snap}）\n")
    lines.append("## 标题候选（选一个）\n")
    lines.append(f"1. 2026 还能报的 {len(events)} 个 AI 赛事📌 报名进行中，附直达链接")
    lines.append(f"2. 打工人副业/学生党冲奖看这篇！{len(events)} 个 AI 赛事报名中")
    lines.append(f"3. 别错过报名🚨 这 {len(events)} 个 AI 黑客松/大赛还能投（含链接）\n")
    lines.append("## 正文\n")
    lines.append("最近想搞点 AI 副业 / 冲个奖的宝子看过来👀")
    lines.append(f"帮大家刷了一轮，目前还能报的 AI 赛事一共 **{len(events)} 个**，按截止时间从近到远排好了👇\n")
    for i, it in enumerate(events, 1):
        lines.append(f"{i}. **{it['name']}** ｜ 截止 {it.get('deadline','')}")
        lines.append(f"   {it.get('note','')}")
    lines.append("")
    lines.append("形式/地区/资格都标好了（线上·国内·所有人可报 等），武汉的宝子注意线下要差旅～")
    lines.append("链接放评论区/主页了，点进去就能报。")
    lines.append("觉得有用记得收藏🌟 下次刷新我再来更新～\n")
    lines.append("## 话题标签\n")
    tags = ["#AI赛事", "#人工智能比赛", "#打工人副业", "#程序员", "#副业搞钱",
            "#AI黑客松", "#算法竞赛", "#学习打卡", "#AI创业", "#大模型", "#具身智能", "#Kaggle"]
    lines.append(" ".join(tags))
    lines.append("")
    lines.append(f"> 快照 {snap} ｜ 生成自 WorkBuddy · AI 赛事百晓生")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_path


def main():
    ap = argparse.ArgumentParser(description="小红书 redskill 交付物生成器")
    ap.add_argument("--data", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--snap", default=None)
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    data_path = args.data or os.path.join(here, "events_data.json")
    if not os.path.exists(data_path):
        sys.stderr.write(f"找不到数据文件：{data_path}\n")
        sys.exit(1)
    with open(data_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    snap = args.snap or raw.get("snap") or datetime.date.today().strftime("%Y-%m-%d")
    today_str = raw.get("today") or snap
    try:
        today = datetime.date(*map(int, today_str.split("-")))
    except Exception:
        today = datetime.date.today()

    events = raw.get("events", [])
    for e in events:
        e["remain"] = compute_remain(e.get("deadline", ""), today)

    out_dir = args.out or os.getcwd()
    os.makedirs(out_dir, exist_ok=True)

    paths = []
    cover = os.path.join(out_dir, f"小红书_封面_{snap}.png")
    paths.append(draw_cover(snap, events, cover))
    total = (len(events) + CHUNK - 1) // CHUNK or 1
    for idx in range(total):
        chunk = events[idx * CHUNK:(idx + 1) * CHUNK]
        sp = os.path.join(out_dir, f"小红书_内容_{snap}_{idx+1}.png")
        paths.append(draw_slide(chunk, idx + 1, total, snap, sp))
    paths = [p for p in paths if p]
    md = os.path.join(out_dir, f"小红书_文案_{snap}.md")
    paths.append(build_md(snap, events, md))

    for p in paths:
        print(p)
    print(f"小红书 redskill 物料已生成：封面1 + 内容{total}张 + 文案1（共 {len(paths)} 个文件）")


if __name__ == "__main__":
    main()
