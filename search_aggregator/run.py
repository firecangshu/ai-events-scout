#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run.py :: 百晓生搜索层统一入口（别人装好 skill 后只需这一条命令）
================================================================

设计目标：**零配置、零 API key、零外部依赖、无硬编码路径**。
别人安装 skill 后，工作目录任意，运行：

  python <skill目录>/search_aggregator/run.py --query "AI hackathon" --snap 2026-11-19

会自动完成：
  1. 调 global_event_radar 跑免费全球雷达（GDELT/HN/GitHub/arXiv/Devfolio/站点扫描）
  2. 归一化候选赛事链接，导出 urls.txt 供 scripts/check_links.py 探活
  3. 输出 candidates.json（统一 schema）+ 人类可读的 html/md 报告

所有输出写到 --out 指定目录（默认 <skill目录>/output），路径全部相对脚本自身解析，
不依赖任何本机绝对路径、不依赖额外安装的服务或 Skill。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import aggregate_search as ag  # noqa: E402
import global_event_radar as radar  # noqa: E402

# 明显不是报名/资讯的链接后缀，导出探活清单时剔除
JUNK_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js", ".pdf", ".zip", ".ico")
# 在这些域名上的通用讨论/首页，优先级降低但保留（可能是官网）
SOCIAL_HOME = {"twitter.com", "x.com", "facebook.com", "instagram.com", "linkedin.com"}


def pick_event_urls(results: List[Dict[str, Any]], limit: int) -> List[str]:
    urls: List[str] = []
    seen = set()
    for item in results:
        url = (item.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        if url.lower().split("?")[0].endswith(JUNK_SUFFIX):
            continue
        key = ag.normalize_url(url)
        if key in seen:
            continue
        seen.add(key)
        urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def build_candidates(report: Dict[str, Any], urls: List[str], snap: str) -> Dict[str, Any]:
    url_set = set(urls)
    picked = [r for r in report["results"] if (r.get("url") or "").strip() in url_set]
    return {
        "snap": snap,
        "query": report["meta"]["query"],
        "generated_at": report["meta"]["generated_at"],
        "note": "雷达发现层输出：需按 rules.md 复核报名截止/身份档/网页入口后再入 events_data.json",
        "source_status": [
            {"engine": e["engine"], "label": e["label"], "status": e["status"], "count": e["count"], "message": e["message"]}
            for e in report["engines"]
        ],
        "raw_count": report["meta"]["raw_count"],
        "candidate_count": len(picked),
        "candidates": picked,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="百晓生搜索层：免费全球赛事发现（一条命令）")
    p.add_argument("--query", default="AI hackathon", help="检索主题，可用中文如 'AI 黑客松 报名'")
    p.add_argument("--snap", default=None, help="快照日期 YYYY-MM-DD，默认今天")
    p.add_argument("--max", dest="max_results", type=int, default=40, help="候选数上限")
    p.add_argument("--urls", type=int, default=40, help="导出探活 URL 数上限")
    p.add_argument("--out", default=None, help="输出目录，默认 <skill目录>/output")
    p.add_argument("--timeout", type=int, default=15)
    p.add_argument("--workers", type=int, default=6)
    args = p.parse_args(argv)

    snap = args.snap or ag.dt.datetime.now().strftime("%Y-%m-%d")
    out = Path(args.out).resolve() if args.out else (SKILL_ROOT / "output")
    out.mkdir(parents=True, exist_ok=True)

    ctx = {
        "query": args.query.strip(),
        "sources": radar.DEFAULT_SOURCES,
        "max_results": max(1, args.max_results),
        "fresh": None,
        "boost_terms": ag.split_csv("报名,registration,deadline,截止,hackathon,黑客松,competition,大赛"),
        "timeout": args.timeout,
        "workers": max(1, args.workers),
    }
    report = radar.build_report(ctx)

    urls = pick_event_urls(report["results"], args.urls)
    candidates = build_candidates(report, urls, snap)

    stamp = re.sub(r"[^0-9]", "", snap)
    radar_path = out / f"radar_{stamp}.json"
    cand_path = out / f"candidates_{stamp}.json"
    urls_path = out / "urls.txt"
    html_path = out / f"radar_{stamp}.html"
    md_path = out / f"radar_{stamp}.md"

    radar_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    cand_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    urls_path.write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")
    html_path.write_text(ag.render_html(report), encoding="utf-8")
    md_path.write_text(ag.render_markdown(report), encoding="utf-8")

    print(f"[百晓生搜索层] 主题：{ctx['query']}  快照：{snap}")
    print(f"原始 {report['meta']['raw_count']} 条 → 去重候选 {report['meta']['result_count']} 条")
    for e in report["engines"]:
        print(f"  - {e['label']:<18} {e['status']:<8} {e['count']:>3} 条")
    print(f"[输出] {cand_path}")
    print(f"[输出] {urls_path}  （供 scripts/check_links.py --file 探活）")
    print(f"[输出] {html_path}")
    print(f"[下一步] python <skill目录>/scripts/check_links.py --file {urls_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
