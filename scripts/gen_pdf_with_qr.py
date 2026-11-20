#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI赛事百晓生 · 生成带二维码的 PDF 清单。

二维码指向线上报名速查表（公网 URL），手机扫码即可打开并可点「去报名」。
PDF 放清单摘要（名称/地区/形式/资格/截止）+ 醒目二维码区，A4 适合打印转发。

依赖（用已装好的 venv 运行）：
  C:/Users/User/.workbuddy/binaries/python/envs/default/Scripts/python.exe
  - qrcode, Pillow, PyMuPDF(pymupdf)

用法：
  python gen_pdf_with_qr.py --data output/events_data.json \
      --url "https://..." --out output/AI赛事清单_带二维码_2026-11-20.pdf \
      --snap 2026-11-20
"""
import argparse
import io
import json
import os
import sys

import qrcode
import pymupdf  # PyMuPDF


CN_FONT = "C:/Windows/Fonts/msyh.ttc"          # 微软雅黑常规
CN_FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"   # 微软雅黑粗体

# A4 尺寸（pt）
PW, PH = 595.28, 841.89
MARGIN = 42


def make_qr_png(url, box=220):
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img = img.resize((box, box))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), box


def wrap_text(text, font, fontsize, max_width):
    """按像素宽度折行，返回行列表。"""
    lines, cur = [], ""
    for ch in text:
        trial = cur + ch
        if font.text_length(trial, fontsize=fontsize) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--url", required=True, help="线上报名速查表的公网 URL（二维码指向）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--snap", default="")
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)
    snap = args.snap or data.get("snap", "")
    events = data.get("events", [])
    dropped = data.get("dropped", [])
    identity = str(data.get("identity", "C"))

    doc = pymupdf.open()
    # 注册中文字体（页面级插入，用 insert_font）
    page = doc.new_page(width=PW, height=PH)
    page.insert_font(fontname="cn", fontfile=CN_FONT)
    page.insert_font(fontname="cnb", fontfile=CN_FONT_BOLD)
    f = pymupdf.Font(fontfile=CN_FONT)
    fb = pymupdf.Font(fontfile=CN_FONT_BOLD)

    # ---- 顶部布局：左侧标题三行，右侧二维码 ----
    # 二维码区（右上醒目）
    qr_bytes, qr_box = make_qr_png(args.url, box=200)
    qr_rect = pymupdf.Rect(PW - MARGIN - 118, MARGIN - 4, PW - MARGIN, MARGIN - 4 + 118)
    page.insert_image(qr_rect, stream=qr_bytes)
    qy = qr_rect.y1 + 15
    for line in ["扫码打开", "可报名速查表", "（含去报名链接）"]:
        w = f.text_length(line, fontsize=9)
        page.insert_text((qr_rect.x0 + (qr_rect.width - w) / 2, qy), line,
                         fontname="cn", fontsize=9, color=(0.15, 0.40, 0.70))
        qy += 13

    # 左侧列宽（避开二维码）
    left_w = qr_rect.x0 - MARGIN - 16

    # 第 1 行：标题
    page.insert_text((MARGIN, MARGIN + 18), "AI 赛事百晓生 · 可报名清单",
                     fontname="cnb", fontsize=18, color=(0.10, 0.24, 0.45))
    # 第 2 行：统计
    page.insert_text((MARGIN, MARGIN + 40),
                     f"快照 {snap}  ·  {identity.split('（')[0]}  ·  {len(events)} 项可报 / {len(dropped)} 类剔除",
                     fontname="cn", fontsize=10, color=(0.35, 0.35, 0.38))
    # 第 3-4 行：说明（折行，限定在左列宽内）
    note = "纸质版仅供速览；扫码打开线上清单，点每条「去报名」直达官网。报名信息以各赛事官方页面为准。"
    ny = MARGIN + 58
    for line in wrap_text(note, f, 8.5, left_w):
        page.insert_text((MARGIN, ny), line, fontname="cn", fontsize=8.5, color=(0.48, 0.48, 0.50))
        ny += 12

    y = max(ny, qy) + 10

    # ---- 分隔线 ----
    page.draw_line((MARGIN, y), (PW - MARGIN, y), color=(0.80, 0.82, 0.85), width=0.8)
    y += 14

    # 表头
    cols = [("name", "赛事名称", None), ("scope", "地区", 46),
            ("form", "形式", 44), ("eligibility", "资格", 118), ("deadline", "报名截止", 108)]
    col_x = [MARGIN]
    widths = [PW - 2 * MARGIN - 46 - 44 - 118 - 108]
    for _, _, w in cols[1:]:
        widths.append(w)
    for w in widths:
        col_x.append(col_x[-1] + w)

    def row_height(item):
        maxlines = 1
        for i, (key, _, _) in enumerate(cols):
            txt = str(item.get(key, "") or "")
            lines = wrap_text(txt, f, 8.5, widths[i] - 6)
            maxlines = max(maxlines, len(lines))
        return max(20, maxlines * 11 + 6)

    for idx, item in enumerate(events):
        rh = row_height(item)
        # 换页
        if y + rh > PH - MARGIN:
            page = doc.new_page(width=PW, height=PH)
            page.insert_font(fontname="cn", fontfile=CN_FONT)
            page.insert_font(fontname="cnb", fontfile=CN_FONT_BOLD)
            y = MARGIN
        if idx % 2 == 0:
            page.draw_rect(pymupdf.Rect(MARGIN - 4, y - 2, PW - MARGIN + 4, y + rh - 2),
                           color=None, fill=(0.965, 0.972, 0.98), width=0)
        for i, (key, _, _) in enumerate(cols):
            txt = str(item.get(key, "") or "")
            lines = wrap_text(txt, fb if key == "name" else f, 8.5, widths[i] - 6)
            ly = y + 10
            for ln in lines:
                page.insert_text((col_x[i] + 3, ly), ln,
                                 fontname="cnb" if key == "name" else "cn",
                                 fontsize=8.5, color=(0.12, 0.12, 0.14))
                ly += 11
        y += rh
        page.draw_line((MARGIN, y - 3), (PW - MARGIN, y - 3),
                       color=(0.90, 0.91, 0.93), width=0.4)

    # 页脚
    footer = f"AI赛事百晓生 · {snap} · 扫码获取可点击报名版本"
    for pno in range(len(doc)):
        pg = doc[pno]
        pg.insert_text((MARGIN, PH - 20), footer, fontname="cn", fontsize=8,
                       color=(0.55, 0.55, 0.58))
        pg.insert_text((PW - MARGIN - 40, PH - 20), f"{pno + 1}/{len(doc)}",
                       fontname="cn", fontsize=8, color=(0.55, 0.55, 0.58))

    # 字体子集化：只嵌入实际用到的字形，体积从数十 MB 降到几百 KB
    try:
        doc.subset_fonts()
    except Exception as e:
        print(f"[warn] 字体子集化跳过: {e}", file=sys.stderr)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    doc.save(args.out, garbage=4, deflate=True)
    doc.close()
    print(f"PDF 生成：{args.out}")
    print(f"赛事 {len(events)} 条 / 剔除 {len(dropped)} 类 / 二维码指向 {args.url}")


if __name__ == "__main__":
    main()
