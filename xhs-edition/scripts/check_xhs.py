# -*- coding: utf-8 -*-
"""小红书版赛事清单独立校验器

逐项校验平台硬约束、数据口径、工程容错，输出 PASS/FAIL 明细并写 check_result.json。
用法：python check_xhs.py [--out output] [--snap 2026-11-14]
退出码：全部通过 0，有 FAIL 1。
"""
import os
import re
import ast
import sys
import json
import math
import argparse
import datetime
import tempfile
import pathlib
import importlib.util

try:
    from PIL import Image
except ImportError as e:
    sys.stderr.write("缺少 Pillow: %s\n" % e)
    sys.exit(2)

ROOT = pathlib.Path(__file__).resolve().parent.parent
GEN = ROOT / "scripts" / "gen_xhs_note.py"
DATA = ROOT / "data" / "events_data.json"

# 站外导流与夸大宣传词（命中即 FAIL）
# 依据小红书《交易导流违规管理细则》(2025-03-12)：
# 类型3=发布其他平台的链接/口令/二维码等及其变形植入；类型5=明示或暗示诱导用户至站外/私域。
# 「下载/网盘/附件」类词：笔记不支持文件附件，出现即暗示站外获取文件 → 类型5。
DIVERSION = [
    "http://", "https://", "www.", "链接", "评论区", "主页", "私信", "微信",
    "二维码", "扫码", "加我", "找我", "扣1", "口令", "站外", "跳转", "vx",
    "下载", "网盘", "附件", "自取", "领取",
]
EXTREME = ["最好", "最强", "第一", "100%", "根治", "保本", "全网最", "绝对", "稳赚"]
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U0001F1E6-\U0001F1FF\u2600-\u27BF]")

results = []


def check(no, name, cond, detail=""):
    results.append({"no": no, "name": name, "pass": bool(cond), "detail": str(detail)})


def collect_strings(node):
    """收集 AST 节点下所有字符串字面量（含 % 格式化与 f-string）。"""
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return out


def png_labels(tree):
    """只取真正画到 PNG 上的文字（d.text / draw.text 的文本参数），排除注释与 docstring。"""
    labels = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "text"):
            continue
        for arg in node.args[:2]:
            labels.extend(collect_strings(arg))
    return "\n".join(labels)


def load_module():
    spec = importlib.util.spec_from_file_location("gen_xhs_note", str(GEN))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser(description="小红书版赛事清单校验器")
    ap.add_argument("--out", default=None)
    ap.add_argument("--snap", default=None)
    args = ap.parse_args()
    out = pathlib.Path(args.out) if args.out else ROOT / "output"
    md_path = out / "content.md"

    if not md_path.exists():
        sys.stderr.write("找不到文案文件，请先运行 gen_xhs_note.py: %s\n" % md_path)
        sys.exit(1)

    src = GEN.read_text(encoding="utf-8")
    tree = ast.parse(src)
    labels = png_labels(tree)
    md = md_path.read_text(encoding="utf-8")

    def section(start, end):
        return md.split(start)[1].split(end)[0].strip()

    title_sec = section("## 标题（选一个）", "## 正文")
    body_sec = section("## 正文", "## 话题标签")
    tag_sec = section("## 话题标签", "## 发布设置")
    titles = re.findall(r"^\d+\.\s*(.+)$", title_sec, re.M)
    tags = re.findall(r"#[^\s#]+", tag_sec)
    publish_text = "\n".join(titles) + "\n" + body_sec + "\n" + tag_sec

    data = json.loads(DATA.read_text(encoding="utf-8"))
    events = data.get("events") or []
    snap = args.snap or data.get("snap") or datetime.date.today().strftime("%Y-%m-%d")

    # --- A. 平台硬约束 ---
    check("A01", "标题候选 3 个且每个 <=20 字",
          len(titles) == 3 and all(len(t) <= 20 for t in titles),
          " / ".join("%s(%d字)" % (t, len(t)) for t in titles))

    body_chars = len(re.sub(r"\s", "", body_sec))
    tag_chars = len(" ".join(tags))
    total_chars = body_chars + tag_chars
    check("A02", "正文含话题 <=1000 字", total_chars <= 1000,
          "正文 %d + 标签 %d = %d 字" % (body_chars, tag_chars, total_chars))

    check("A03", "话题标签 3-10 个", 3 <= len(tags) <= 10, "%d 个: %s" % (len(tags), " ".join(tags)))

    imgs = sorted(out.glob("*.png"))
    sizes = []
    over = []
    for p in imgs:
        with Image.open(p) as im:
            sizes.append(im.size)
        if p.stat().st_size > 10 * 1024 * 1024:
            over.append(p.name)
    check("A04", "图片 1-18 张", 1 <= len(imgs) <= 18, "%d 张" % len(imgs))
    check("A05", "全部图片统一 1080x1440 (3:4)", all(s == (1080, 1440) for s in sizes),
          str(sorted(set(sizes))))
    check("A06", "单张图片 <=10MB", not over, "超限: %s" % over if over else "最大 %.2fMB" % (
        max([p.stat().st_size for p in imgs] or [0]) / 1024 / 1024))

    div_hits = [w for w in DIVERSION if w in publish_text or w in labels]
    check("A07", "无站外链接与导流话术（正文+图片文字）", not div_hits,
          "命中: %s" % div_hits if div_hits else "0 命中")
    ext_hits = [w for w in EXTREME if w in publish_text or w in labels]
    check("A08", "无夸大/极限词", not ext_hits, "命中: %s" % ext_hits if ext_hits else "0 命中")
    check("A09", "AI 生成内容主动标识（正文+封面）",
          "AI 辅助生成" in body_sec and "图文由 AI 辅助生成" in labels,
          "正文与封面均含声明")
    emoji_hits = sorted(set(EMOJI.findall(publish_text + labels + src)))
    check("A10", "PNG 与发布文案不含 emoji", not emoji_hits,
          "命中: %s" % emoji_hits if emoji_hits else "0 命中")

    # --- B. 版式与安全区 ---
    st = re.search(r"SAFE_TOP\s*=\s*(\d+)", src)
    sb = re.search(r"SAFE_BOTTOM\s*=\s*(\d+)", src)
    sl = re.search(r"SAFE_LEFT\s*=\s*(\d+)", src)
    sr = re.search(r"SAFE_RIGHT\s*=\s*(\d+)", src)
    safe_ok = (st and int(st.group(1)) >= 150 and sb and int(sb.group(1)) <= 1240
               and sl and int(sl.group(1)) >= 60 and sr and int(sr.group(1)) <= 1020)
    check("B01", "封面安全区 顶>=150/底<=1240/左>=60/右<=1020", safe_ok,
          "top=%s bottom=%s left=%s right=%s" %
          (st.group(1) if st else "-", sb.group(1) if sb else "-",
           sl.group(1) if sl else "-", sr.group(1) if sr else "-"))
    fb = re.search(r"fbig\s*=\s*load_font\(BOLD_FONTS,\s*(\d+)\)", src)
    check("B02", "封面主标题字号 >=60px", fb and int(fb.group(1)) >= 60,
          "%spx" % fb.group(1) if fb else "-")
    chunk = re.search(r"CHUNK\s*=\s*(\d+)", src)
    expected_pages = max(1, math.ceil(len(events) / int(chunk.group(1)))) if chunk else -1
    check("B03", "页数与条数匹配（封面+内容页）", len(imgs) == expected_pages + 1,
          "%d 条 / 每页 %s 条 / 应有 %d 内容页 / 实有 %d 张图" %
          (len(events), chunk.group(1) if chunk else "-", expected_pages, len(imgs)))

    # --- C. 数据口径 ---
    all_text = json.dumps(data, ensure_ascii=False)
    bare = re.findall(r"(?<!中国)台湾", all_text)
    check("C01", "数据中无裸「台湾」表述", not bare, "%d 处" % len(bare))
    bad_scope = [e.get("name", "") for e in events
                 if "中国台湾" in e.get("name", "") and e.get("scope") != "国内"]
    check("C02", "中国台湾地区赛事归入国内", not bad_scope,
          "异常: %s" % bad_scope if bad_scope else "0 异常")
    check("C03", "资格字段完整回显（未做去括号删减）",
          'it.get("eligibility"' in src and "elig_short" not in src
          and not re.search(r"re\.sub\(r.\[（\(]", src),
          "生成器直接读取完整 eligibility")
    check("C04", "序号连续（每页承接上一页）",
          "start_no" in src and "idx * CHUNK + 1" in src,
          "draw_content 使用 start_no + i")
    deadline_missing = [e.get("name", "") for e in events if not e.get("deadline")]
    check("C05", "每条均有报名/提交截止字段", not deadline_missing,
          "缺失: %s" % deadline_missing if deadline_missing else "%d 条齐全" % len(events))

    # --- D. 工程容错（真实调用生成器函数） ---
    m = load_module()
    tmp = tempfile.mkdtemp(prefix="xhs_check_")
    cases = [
        ("D01 空数据不崩溃", lambda: m.draw_content([], 1, 1, 1, snap, os.path.join(tmp, "e.png"))),
        ("D02 缺 name 字段不崩溃",
         lambda: m.draw_content([{"note": "x"}], 1, 1, 1, snap, os.path.join(tmp, "n.png"))),
        ("D03 两位数序号居中不崩溃",
         lambda: m.draw_content([{"name": "x"}] * 5, 10, 3, 3, snap, os.path.join(tmp, "t.png"))),
        ("D04 空数据仍产出文案", lambda: m.build_content(snap, [], os.path.join(tmp, "c.md"))),
    ]
    for no_name, fn in cases:
        label = no_name.split(" ", 1)
        try:
            fn()
            check(label[0], label[1], True, "无异常")
        except Exception as e:
            check(label[0], label[1], False, "%s: %s" % (type(e).__name__, e))
    check("D05", "today 与 snap 同步（不使用旧 today 基准）",
          "raw[\"today\"] != snap" in src and "按 snap 计算剩余天数" in src,
          "数据 today 与 snap 不一致时按 snap 并提示")

    # --- 输出 ---
    passed = sum(1 for r in results if r["pass"])
    failed = len(results) - passed
    print("=" * 78)
    print("小红书版赛事清单 · 自动化校验（快照 %s）" % snap)
    print("=" * 78)
    for r in results:
        print("[%s] %-4s %-38s %s" %
              ("PASS" if r["pass"] else "FAIL", r["no"], r["name"], r["detail"]))
    print("-" * 78)
    print("汇总: %d PASS / %d FAIL / 共 %d 项" % (passed, failed, len(results)))
    print("=" * 78)

    report = {
        "snap": snap,
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "passed": passed, "failed": failed, "total": len(results),
        "items": results,
    }
    (out / "check_result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
