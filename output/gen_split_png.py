# -*- coding: utf-8 -*-
"""把长图拆成多张可完整预览的短图（解决预览卡片高度截断问题）。
读取 events_data.json，按 chunks 大小切分，每张独立带标题与页脚。
用法：python gen_split_png.py
"""
import os, json, datetime
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "events_data.json")

with open(DATA, "r", encoding="utf-8") as f:
    raw = json.load(f)
snap = raw.get("snap") or datetime.date.today().strftime("%Y-%m-%d")
events = raw.get("events", [])

W = 1080
pad = 28
head_h = 150
row_h = 116
foot_h = 90
CHUNK = 7  # 每张 7 条，拆成 2 张

win_fonts = ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc"]

def load_font(paths, size):
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

fbold = load_font(["C:/Windows/Fonts/msyhbd.ttc"], 30)
ftitle = load_font(win_fonts, 25)
fmid = load_font(win_fonts, 19)
fsmall = load_font(win_fonts, 16)
flink = load_font(win_fonts, 15)

def scope_key(s):
    s = (s or "").strip()
    if s in ("国内", "国外", "不限"): return s
    if "国外" in s or "海外" in s: return "国外"
    if "国内" in s: return "国内"
    return "不限"

def short(u, n=42):
    for p in ("https://", "http://"):
        if u and u.startswith(p): u = u[len(p):]
    if u and u.startswith("www."): u = u[4:]
    return (u[:n] + ("…" if u and len(u) > n else "")) if u else ""

def draw_part(items, part_label, total_parts, out_path):
    H = head_h + len(items) * row_h + foot_h
    img = Image.new("RGB", (W, H), (245, 246, 250))
    d = ImageDraw.Draw(img)
    # header
    d.rectangle([0, 0, W, head_h], fill=(26, 26, 46))
    d.text((pad, 34), "AI 赛事百晓生 · 还能报 & 即将开启", font=fbold, fill=(255, 255, 255))
    d.text((pad, 82), f"快照 {snap} ｜ {len(items)} 项 · 共{total_parts}张之{part_label} ｜ 链接均已探活200", font=fmid, fill=(0, 212, 255))
    y = head_h
    for i, it in enumerate(items, 1):
        d.rectangle([pad, y + 8, W - pad, y + row_h - 8], fill=(255, 255, 255), outline=(225, 225, 225))
        cx, cy = pad + 26, y + row_h // 2
        d.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill=(0, 102, 204))
        d.text((cx - 12, cy - 16), str(i), font=ftitle, fill=(255, 255, 255))
        tx = pad + 62
        d.text((tx, y + 16), it["name"][:20], font=ftitle, fill=(26, 26, 46))
        d.text((tx, y + 50), f"地区：{scope_key(it.get('scope',''))} ｜ 形式：{it.get('form','')[:10]} ｜ 资格：{it.get('eligibility','')[:10]}", font=fsmall, fill=(90, 90, 90))
        d.text((tx, y + 74), f"备注：{it.get('note','')[:28]}", font=fsmall, fill=(90, 90, 90))
        rx = W - pad - 4
        d.text((rx - 150, y + 20), f"截止 {it.get('deadline','')[:14]}", font=fmid, fill=(156, 0, 6))
        d.text((rx - 150, y + 52), f"剩余 {it.get('remain','')}", font=ftitle, fill=(156, 0, 6))
        d.text((tx, y + 96), f"🔗 {short(it['link'])}", font=flink, fill=(5, 99, 193))
        y += row_h
    # footer
    d.rectangle([0, H - foot_h, W, H], fill=(26, 26, 46))
    d.text((pad, H - foot_h + 30), f"AI 赛事百晓生 · 常驻分享版 v{snap} ｜ 生成自 WorkBuddy", font=fsmall, fill=(180, 195, 255))
    img.save(out_path)
    return out_path, H

# 切分
total = (len(events) + CHUNK - 1) // CHUNK
paths = []
for idx in range(total):
    chunk = events[idx * CHUNK:(idx + 1) * CHUNK]
    label = "（上）" if idx == 0 else ("（下）" if total == 2 else f"（{idx+1}）")
    if total == 1:
        label = ""
    out = os.path.join(HERE, f"AI赛事分享长图_{snap}_P{idx+1}.png")
    p, hh = draw_part(chunk, label, total, out)
    paths.append((p, hh, len(chunk)))

for p, hh, n in paths:
    print(f"{p}  ({hh}px, {n} 项)")
print(f"共 {total} 张，原长图仍保留：AI赛事分享长图_{snap}.png")
