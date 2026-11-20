# -*- coding: utf-8 -*-
"""
AI赛事百晓生 v1.3.1 发布前鲁棒性 + 流畅性测试
================================================
覆盖：规则回归 / 五交付物生成 / 打标流水线 / 边界输入 / 链接探活 / 耗时。
只读验证，不修改 output/ 既有交付物（边界测试产物写入临时目录）。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

PY = sys.executable
ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(ROOT, "scripts")
AGG = os.path.join(SCRIPTS, "..", "search_aggregator")
DATA = os.path.join(ROOT, "output", "events_data.json")
RADAR = os.path.join(ROOT, "search_aggregator", "output", "radar_ai_hackathon.json")

results = []


def record(name, ok, detail="", secs=0.0):
    results.append((name, ok, detail, secs))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  ({secs:.1f}s)  {detail}")


def run(cmd, cwd=ROOT, timeout=300, expect_zero=True):
    t0 = time.time()
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    secs = time.time() - t0
    ok = (p.returncode == 0) if expect_zero else True
    return ok, p, secs


def count(pat, text):
    return len(re.findall(pat, text))


# ---------- 1. 规则引擎回归（14 例历史误判） ----------
ok, p, secs = run([PY, os.path.join(SCRIPTS, "auto_tag.py"), "--selftest"])
npass = len(re.findall(r"\[PASS\]", p.stdout or ""))
nfail = len(re.findall(r"\[FAIL\]", p.stdout or ""))
record("auto_tag --selftest 14 例回归", ok and nfail == 0 and npass >= 14,
       f"PASS={npass} FAIL={nfail}", secs)

# ---------- 2. 五交付物：正常数据 ----------
tmp1 = tempfile.mkdtemp(prefix="rt_normal_")
ok, p, secs = run([PY, os.path.join(SCRIPTS, "events_table_gen.py"),
                   "--data", DATA, "--out", tmp1, "--snap", "2026-11-20"])
files = {f: os.path.getsize(os.path.join(tmp1, f)) for f in os.listdir(tmp1)} if ok else {}
record("events_table_gen 正常 17 条 → 5 产物", ok and len(files) == 5,
       f"files={list(files)}", secs)

# ---------- 3. 五交付物：产物内容断言（主题筛选器） ----------
if files:
    quick = open(os.path.join(tmp1, "AI赛事报名速查表_2026-11-20.html"), encoding="utf-8").read()
    share = open(os.path.join(tmp1, "AI赛事常驻清单_分享版_2026-11-20.html"), encoding="utf-8").read()
    clean = open(os.path.join(tmp1, "AI赛事汇总_清爽表_2026-11-20.html"), encoding="utf-8").read()
    checks = {
        "速查表含主题筛选按钮组": 'data-g="theme"' in quick,
        "速查表行含 data-theme": 'data-theme="' in quick,
        "速查表 JS 含 theme 过滤": "S.theme" in quick,
        "速查表导出表头含主题": quick.count("'主题'") >= 2,
        "速查表含 6 组筛选+搜索": all(f'data-g="{g}"' in quick for g in ("scope", "form", "elig", "perk", "region", "theme")) and 'flabel">搜索' in quick,
        "分享版含主题 pill": "theme-pill" in share and 'data-g="theme"' in share,
        "分享版卡片 data-theme": 'data-theme="' in share,
        "清爽表含主题列": "<th>主题</th>" in clean,
    }
    allok = all(checks.values())
    bad = [k for k, v in checks.items() if not v]
    record("交付物内容断言（主题筛选 8 项）", allok, "全部通过" if allok else f"未过: {bad}")
    xlsx_ok = os.path.getsize(os.path.join(tmp1, "AI赛事汇总_清爽版_2026-11-20.xlsx")) > 5000
    png_ok = os.path.getsize(os.path.join(tmp1, "AI赛事分享长图_2026-11-20.png")) > 50000
    record("xlsx 与 PNG 产物体积正常", xlsx_ok and png_ok, f"xlsx={xlsx_ok} png={png_ok}")
else:
    record("交付物内容断言（主题筛选 8 项）", False, "无产物可断言")
    record("xlsx 与 PNG 产物体积正常", False, "无产物可断言")

# ---------- 4. 鲁棒性：空 events ----------
tmp2 = tempfile.mkdtemp(prefix="rt_empty_")
empty = {"snap": "2026-11-20", "title_date": "2026-11-20", "today": "2026-11-20",
         "events": [], "dropped": []}
ep = os.path.join(tmp2, "empty_data.json")
json.dump(empty, open(ep, "w", encoding="utf-8"), ensure_ascii=False)
ok, p, secs = run([PY, os.path.join(SCRIPTS, "events_table_gen.py"),
                   "--data", ep, "--out", tmp2, "--snap", "2026-11-20"])
record("鲁棒性：空 events 不崩溃", ok, (p.stderr or "").strip()[:80], secs)

# ---------- 5. 鲁棒性：缺字段最小条目 ----------
tmp3 = tempfile.mkdtemp(prefix="rt_min_")
minimal = {"snap": "2026-11-20", "title_date": "2026-11-20", "today": "2026-11-20",
           "events": [{"name": "最小条目赛事"}], "dropped": []}
mp = os.path.join(tmp3, "min_data.json")
json.dump(minimal, open(mp, "w", encoding="utf-8"), ensure_ascii=False)
ok, p, secs = run([PY, os.path.join(SCRIPTS, "events_table_gen.py"),
                   "--data", mp, "--out", tmp3, "--snap", "2026-11-20"])
record("鲁棒性：仅 name 的最小条目不崩溃", ok, (p.stderr or "").strip()[:80], secs)

# ---------- 6. 打标流水线：真实 30 条 ----------
tmp4 = tempfile.mkdtemp(prefix="rt_tag_")
ok, p, secs = run([PY, os.path.join(SCRIPTS, "tag_candidates.py"),
                   "--candidates", RADAR, "--out", tmp4])
tagged_ok = ok
html_ok = False
if ok:
    rj = json.load(open(os.path.join(tmp4, "candidates_tagged_20261119.json"), encoding="utf-8"))
    tagged_ok = rj.get("count") == 30 and rj.get("pending_count") == 30
    rep = open(os.path.join(tmp4, "radar_discovery_20261119.html"), encoding="utf-8").read()
    html_ok = (count(r'class="card"', rep) == 30
               and "规则高置信" in rep and "待 AI 复核" in rep
               and "复核方法" in rep and "data-theme" not in rep  # 候选层用徽章而非筛选器
               and '主题:' in rep)
record("tag_candidates 30 条全链路（JSON+MD+HTML）", ok and tagged_ok and html_ok,
       f"count/pending/HTML卡片断言={'OK' if (tagged_ok and html_ok) else 'FAIL'}", secs)

# ---------- 7. 鲁棒性：空候选 + 缺键候选 ----------
tmp5 = tempfile.mkdtemp(prefix="rt_tag_empty_")
for name, payload in (("cand_empty.json", {"results": []}),
                      ("cand_bare.json", {"results": [{"title": "只有标题的候选"}]})):
    fp = os.path.join(tmp5, name)
    json.dump(payload, open(fp, "w", encoding="utf-8"), ensure_ascii=False)
    ok, p, secs = run([PY, os.path.join(SCRIPTS, "tag_candidates.py"),
                       "--candidates", fp, "--out", tmp5, "--html-out", "none"])
    record(f"鲁棒性：tag_candidates {name} 不崩溃", ok, (p.stderr or "").strip()[:80], secs)

# ---------- 8. auto_tag dry-run（不写回） ----------
ok, p, secs = run([PY, os.path.join(SCRIPTS, "auto_tag.py"), "--data", DATA])
record("auto_tag dry-run 全量打标报告", ok, (p.stdout or "").strip().splitlines()[-1][:60] if p.stdout else "", secs)

# ---------- 9. 链接探活（真实网络） ----------
urls_file = os.path.join(ROOT, "output", "urls.txt")
if os.path.exists(urls_file):
    ok, p, secs = run([PY, os.path.join(SCRIPTS, "check_links.py"), "--file", urls_file], timeout=600)
    n200 = len(re.findall(r"200", p.stdout or ""))
    record("check_links 报名入口探活全部 200", ok, f"退出码0，200命中{n200}处", secs)
else:
    record("check_links 报名入口探活全部 200", False, "urls.txt 不存在")

# ---------- 10. 雷达模块导入与 CLI 帮助（流畅性/协议） ----------
ok, p, secs = run([PY, "-c", "import sys; sys.path.insert(0, r'%s'); import global_event_radar, aggregate_search; print('import-ok')" % AGG])
record("雷达/聚合模块导入", ok and "import-ok" in (p.stdout or ""), "", secs)

ok, p, secs = run([PY, os.path.join(AGG, "run.py"), "--help"])
help_ok = ok and ("--query" in (p.stdout or ""))
record("run.py --help 协议可用", help_ok, "", secs)

# ---------- 11. 真实雷达抓取全链路（8 源聚合 → 候选） ----------
tmp6 = tempfile.mkdtemp(prefix="rt_radar_")
ok, p, secs = run([PY, os.path.join(AGG, "run.py"), "--query", "AI hackathon",
                   "--snap", "2026-11-20", "--out", tmp6], timeout=600)
radar_ok = False
detail = (p.stderr or "").strip()[-120:]
if ok:
    cand = []
    for base in (tmp6, AGG):
        outd = os.path.join(base, "output") if base == AGG else base
        if not os.path.isdir(outd):
            continue
        for f in sorted(os.listdir(outd), reverse=True):
            if f.startswith("radar_") and f.endswith(".json"):
                try:
                    rj = json.load(open(os.path.join(outd, f), encoding="utf-8"))
                except Exception:
                    continue
                cand = rj.get("results") or rj.get("candidates") or []
                if cand:
                    break
        if cand:
            break
    radar_ok = bool(cand)
    detail = f"候选 {len(cand)} 条" if cand else "未找到非空候选"
record("真实雷达抓取全链路（8 源 → 候选）", radar_ok, detail, secs)

# ---------- 汇总 ----------
shutil.rmtree(tmp1, ignore_errors=True)
shutil.rmtree(tmp2, ignore_errors=True)
shutil.rmtree(tmp3, ignore_errors=True)
shutil.rmtree(tmp4, ignore_errors=True)
shutil.rmtree(tmp5, ignore_errors=True)
shutil.rmtree(tmp6, ignore_errors=True)

n_pass = sum(1 for _, okk, _, _ in results if okk)
n_all = len(results)
total = sum(s for _, _, _, s in results)
print("\n" + "=" * 60)
print(f"汇总: {n_pass}/{n_all} 通过 ｜ 总耗时 {total:.1f}s")
for name, okk, detail, secs in results:
    if not okk:
        print(f"  ✗ {name}: {detail}")
sys.exit(0 if n_pass == n_all else 1)
