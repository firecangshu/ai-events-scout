#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
global_event_radar.py :: 免费全球 AI 赛事 / 黑客松雷达
=====================================================

目标：在**不接搜索服务商 API、不按次付费**的前提下，尽可能覆盖全球平台与公域资讯。

数据源分三层：
1. 公开免费端点（无需 key / 无需登录）：GDELT 全球新闻、Hacker News Algolia、
   arXiv API、GitHub Search API、Devfolio 公开页面。
2. 已有免费搜索层：web_search / multi_search / wechat_article_search，
   用 site: 查询补 Devpost / Kaggle / MLH / Reddit / 中文平台。
3. 可选本地工具：FreeSearch API（localhost:8000）、Agent Reach CLI（如已安装）。

输出复用 aggregate_search.py 的统一 schema / 去重 / 排序 / HTML/MD 渲染。

用法：
  python global_event_radar.py "AI hackathon" --max 30 \
      --json-out output/radar.json --html-out output/radar.html
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import html
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import aggregate_search as ag  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"

SOURCE_META = {
    "gdelt": {"label": "GDELT 全球新闻", "group": "news"},
    "hn_algolia": {"label": "Hacker News", "group": "community"},
    "arxiv": {"label": "arXiv", "group": "academic"},
    "github": {"label": "GitHub", "group": "code"},
    "devfolio": {"label": "Devfolio", "group": "platform"},
    "site_scan": {"label": "站点扫描", "group": "web"},
    "freesearch": {"label": "FreeSearch 本地服务", "group": "web"},
    "agent_reach": {"label": "Agent Reach", "group": "social"},
}

DEFAULT_SOURCES = ["gdelt", "hn_algolia", "arxiv", "github", "devfolio", "site_scan", "freesearch", "agent_reach"]

SITE_QUERIES = [
    "Devpost AI hackathon registration open {year}",
    "Kaggle AI competition {year}",
    "MLH Major League Hacking AI hackathon {year}",
    "AI黑客松 报名 截止 {year}",
    "AI大赛 征集 报名 {year}",
]


# ---------------------------------------------------------------- helpers

def fetch(url: str, timeout: int = 15, headers: Optional[Dict[str, str]] = None,
          retries: int = 1) -> str:
    """带轻量重试的 GET。并发扇出时网络抖动常见，重试一次可显著提升别人机器的开箱成功率。"""
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    last: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            try:
                return raw.decode(charset, errors="replace")
            except LookupError:
                return raw.decode("utf-8", errors="replace")
        except Exception as exc:
            last = exc
            if attempt < retries:
                time.sleep(1)
    assert last is not None
    raise last


def parse_gdelt_date(value: str) -> str:
    m = re.match(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z", value or "")
    if not m:
        return ""
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{m.group(6)}"


ZH_TO_EN = {
    "黑客松": "hackathon", "大赛": "competition", "竞赛": "competition",
    "比赛": "competition", "赛事": "competition", "报名": "registration",
    "截止": "deadline", "人工智能": "AI", "人工智能大赛": "AI competition",
    "智能体": "agent", "创新": "innovation", "挑战赛": "challenge",
}


def to_english_query(query: str) -> str:
    """把中文主题粗翻成英文，供 HN/arXiv/GitHub/GDELT 等国际源使用。"""
    q = query.strip()
    if not ag.is_zh(q):
        return q
    out = q
    # 长词优先替换，避免「人工智能」被拆坏
    for zh in sorted(ZH_TO_EN, key=len, reverse=True):
        out = out.replace(zh, ZH_TO_EN[zh])
    tokens = [t for t in re.split(r"[\s,，、/]+", out) if t]
    # 中英混合时可能仍有残留中文词，剔除后保底给 AI hackathon
    tokens = [t for t in tokens if not ag.is_zh(t)]
    result = " ".join(dict.fromkeys(tokens)).strip()
    return result or "AI hackathon"


def query_variants(query: str, year: int) -> List[str]:
    q = query.strip()
    out = [q]
    lower = q.lower()
    if "hackathon" not in lower and "黑客松" not in q:
        out.append(f"{q} hackathon")
    if "competition" not in lower and "赛事" not in q and "大赛" not in q:
        out.append(f"{q} competition")
    if "registration" not in lower and "报名" not in q:
        out.append(f"{q} registration open {year}")
    return list(dict.fromkeys(out))[:4]


def boost_for_event(item: Dict[str, Any]) -> None:
    text = " ".join([
        item.get("title", ""), item.get("snippet", ""), item.get("content", ""),
        " ".join(item.get("tags", [])),
    ]).lower()
    reasons = item.get("score_reasons", [])
    bonus = 0.0
    strong = ("registration open", "apply now", "报名", "征集", "deadline", "截止", "submit", "申请")
    platform = ("devpost", "kaggle", "devfolio", "mlh.io", "hackathon.com", "dorahacks", "github.com")
    if any(k in text for k in strong):
        bonus += 5.0
        reasons.append("含报名/截止信号")
    if any(k in text for k in platform):
        bonus += 3.0
        reasons.append("赛事平台来源")
    if bonus:
        item["score"] = round(min(100.0, item.get("score", 0) + bonus), 1)
        item["score_reasons"] = reasons


# ---------------------------------------------------------------- sources

def src_gdelt(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "gdelt"
    started = time.time()
    variants = query_variants(to_english_query(ctx["query"]), dt.datetime.now().year)[:2]
    items: List[Dict[str, Any]] = []
    gdelt_limited = False
    for idx, q in enumerate(variants):
        if idx > 0 and not items:
            time.sleep(2)
        query = f'"{q}"' if " " in q else q
        url = (
            "https://api.gdeltproject.org/api/v2/doc/doc?"
            + urllib.parse.urlencode({
                "query": query,
                "mode": "artlist",
                "format": "json",
                "maxrecords": min(ctx["max_results"] * 2, 60),
                "sort": "datedesc",
            })
        )
        try:
            data = json.loads(fetch(url, timeout=ctx["timeout"]))
        except Exception as exc:
            if "429" in str(exc):
                gdelt_limited = True
            continue
        for row in data.get("articles", []) or []:
            title = ag.clean_text(row.get("title"), 220)
            url_value = ag.clean_text(row.get("url"), 1000)
            if not title or not url_value:
                continue
            items.append(ag.make_item(
                name, q, title=title, url=url_value,
                snippet=f"{row.get('domain','')} · {row.get('language','')} · {row.get('sourcecountry','')}",
                content=title,
                published_at=parse_gdelt_date(row.get("seendate", "")),
                source=row.get("domain") or "GDELT",
                source_type="news",
                tags=[row.get("language", ""), row.get("sourcecountry", ""), "global-news"],
                raw=row,
            ))
    if items:
        return ag.outcome(name, "ok", items,
                          message=f"GDELT 全球新闻，{len(variants)} 组查询",
                          elapsed_ms=int((time.time() - started) * 1000))
    return ag.outcome(name, "skipped", items,
                      message="GDELT 暂无结果或触发 429 限流（共享 IP 常见），已跳过",
                      elapsed_ms=int((time.time() - started) * 1000))


def src_hn(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "hn_algolia"
    started = time.time()
    items: List[Dict[str, Any]] = []
    eq = to_english_query(ctx["query"])
    for q in query_variants(eq, dt.datetime.now().year)[:2]:
        url = "https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode({
            "query": q, "tags": "story", "hitsPerPage": min(ctx["max_results"], 30),
        })
        try:
            data = json.loads(fetch(url, timeout=ctx["timeout"], retries=1))
        except Exception:
            continue
        for row in data.get("hits", []) or []:
            object_id = row.get("objectID") or ""
            if not object_id:
                continue
            link = row.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
            items.append(ag.make_item(
                name, q, title=row.get("title") or row.get("story_title"),
                url=link, snippet=row.get("story_text") or "Hacker News 讨论",
                published_at=row.get("created_at") or "",
                author=row.get("author"), source="Hacker News",
                source_type="community", tags=["hn", "tech-community"],
                metrics={"like": row.get("points") or 0, "comment": row.get("num_comments") or 0,
                         "interaction": int(row.get("points") or 0) + int(row.get("num_comments") or 0)},
                raw=row,
            ))
    return ag.outcome(name, "ok" if items else "skipped", items,
                      message="Hacker News Algolia 公开 API",
                      elapsed_ms=int((time.time() - started) * 1000))


def src_arxiv(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "arxiv"
    started = time.time()
    eq = to_english_query(ctx["query"])
    q = f'all:"{eq}"' if " " in eq else f'all:{eq}'
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode({
        "search_query": q, "max_results": min(ctx["max_results"], 20), "sortBy": "submittedDate", "sortOrder": "descending",
    })
    try:
        raw = fetch(url, timeout=ctx["timeout"])
        root = ET.fromstring(raw)
    except Exception as exc:
        return ag.outcome(name, "error", message=f"arXiv 请求失败：{type(exc).__name__}")
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items = []
    for entry in root.findall("a:entry", ns):
        title = ag.clean_text(entry.findtext("a:title", default="", namespaces=ns), 220)
        link_el = entry.find("a:link", ns)
        link = link_el.attrib.get("href", "") if link_el is not None else ""
        if not title or not link:
            continue
        items.append(ag.make_item(
            name, ctx["query"], title=title, url=link,
            snippet=ag.clean_text(entry.findtext("a:summary", default="", namespaces=ns), 500),
            content=ag.clean_text(entry.findtext("a:summary", default="", namespaces=ns), 2000),
            published_at=entry.findtext("a:published", default="", namespaces=ns),
            author=", ".join(a.findtext("a:name", default="", namespaces=ns) for a in entry.findall("a:author", ns)),
            source="arXiv", source_type="academic", tags=["arxiv", "research"],
        ))
    return ag.outcome(name, "ok" if items else "skipped", items,
                      message="arXiv Atom API",
                      elapsed_ms=int((time.time() - started) * 1000))


def src_github(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "github"
    started = time.time()
    q = to_english_query(ctx["query"])
    if "hackathon" not in q.lower():
        q = f"{q} hackathon"
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode({
        "q": q, "per_page": min(ctx["max_results"], 20), "sort": "updated",
    })
    try:
        data = json.loads(fetch(url, timeout=ctx["timeout"], headers={"Accept": "application/vnd.github+json"}))
    except Exception as exc:
        status = "skipped" if ("403" in str(exc) or "429" in str(exc)) else "error"
        return ag.outcome(name, status, message=f"GitHub API 失败/匿名限流：{type(exc).__name__}；不影响其他源")
    items = []
    for row in data.get("items", []) or []:
        items.append(ag.make_item(
            name, ctx["query"], title=row.get("full_name") or row.get("name"),
            url=row.get("html_url"), snippet=row.get("description"),
            content=row.get("description"), published_at=row.get("updated_at"),
            source="GitHub", source_type="code",
            tags=["github"] + (row.get("topics") or [])[:8],
            metrics={"like": row.get("stargazers_count") or 0, "interaction": row.get("stargazers_count") or 0},
            raw={"full_name": row.get("full_name"), "html_url": row.get("html_url")},
        ))
    return ag.outcome(name, "ok" if items else "skipped", items,
                      message="GitHub Search API（匿名限速，失败自动跳过）",
                      elapsed_ms=int((time.time() - started) * 1000))


def src_devfolio(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "devfolio"
    started = time.time()
    try:
        page = fetch("https://devfolio.co/hackathons", timeout=ctx["timeout"])
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page, re.S)
        if not m:
            return ag.outcome(name, "error", message="未找到 Devfolio __NEXT_DATA__")
        data = json.loads(m.group(1))
    except Exception as exc:
        return ag.outcome(name, "error", message=f"Devfolio 解析失败：{type(exc).__name__}")
    rows: List[Dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "open_hackathons" in node and isinstance(node["open_hackathons"], list):
                rows.extend(x for x in node["open_hackathons"] if isinstance(x, dict))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    q_tokens = [t for t in ag.query_tokens(ctx["query"]) if len(t) >= 2]
    items = []
    for row in rows:
        title = ag.clean_text(row.get("name"), 220)
        slug = ag.clean_text(row.get("slug"), 120)
        if not title or not slug:
            continue
        blob = (title + " " + ag.clean_text(row.get("description"))).lower()
        if q_tokens and not any(t in blob for t in q_tokens):
            continue
        items.append(ag.make_item(
            name, ctx["query"], title=title,
            url=f"https://devfolio.co/hackathons/{slug}",
            snippet=ag.clean_text(row.get("description")) or f"Devfolio hackathon · {row.get('type','')}",
            published_at=row.get("starts_at") or "",
            source="Devfolio", source_type="platform",
            tags=["devfolio", "hackathon", f"ends:{row.get('ends_at','')[:10]}"],
            metrics={"interaction": int(row.get("participants_count") or 0)},
            raw={k: row.get(k) for k in ("name", "slug", "starts_at", "ends_at", "is_online", "participants_count")},
        ))
    return ag.outcome(name, "ok" if items else "ok", items,
                      message=f"Devfolio 公开页面，发现 {len(rows)} 个开放赛事，按 query 过滤后 {len(items)} 个",
                      elapsed_ms=int((time.time() - started) * 1000))


def src_site_scan(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "site_scan"
    started = time.time()
    year = dt.datetime.now().year
    queries = [q.format(year=year) for q in SITE_QUERIES]
    items: List[Dict[str, Any]] = []
    sub = dict(ctx)
    # aggregate_search 的适配器需要完整上下文字段，补齐默认值避免 KeyError 被吞掉。
    sub.update({
        "lang": ag.detect_lang(ctx["query"]),
        "mode": "balanced",
        "scope": "auto",
        "intents": ag.detect_intent(ctx["query"]),
        "allow_paid": False,
        "include_domains": [],
        "exclude_domains": [],
        "workers": ctx.get("workers", 4),
    })
    sub["max_results"] = max(4, min(ctx["max_results"], 8))
    sub["timeout"] = min(ctx["timeout"], 8)
    for q in queries:
        sub["query"] = q
        for adapter in (ag.adapter_web_search, ag.adapter_multi_search):
            try:
                res = adapter(sub)
            except Exception:
                continue
            for item in res.get("items", []) or []:
                item["tags"] = list(dict.fromkeys((item.get("tags") or []) + ["site-scan"]))
                items.append(item)
        if len(items) >= 15:
            break
    if not items:
        # 平台词查询在部分搜索引擎上会被改写为空；退回原始 query + 中文 query。
        for q in [ctx["query"], "AI黑客松 报名 截止 2026"]:
            sub["query"] = q
            for adapter in (ag.adapter_web_search, ag.adapter_multi_search):
                try:
                    res = adapter(sub)
                except Exception:
                    continue
                for item in res.get("items", []) or []:
                    item["tags"] = list(dict.fromkeys((item.get("tags") or []) + ["site-scan", "fallback"]))
                    items.append(item)
            if items:
                break
    return ag.outcome(name, "ok" if items else "skipped", items,
                      message=f"site: 扫描 {len(queries)} 组查询（Devpost/Kaggle/MLH/Reddit/中文平台）",
                      elapsed_ms=int((time.time() - started) * 1000))


def src_freesearch(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "freesearch"
    base = os.environ.get("FREESEARCH_URL", "http://127.0.0.1:8000").rstrip("/")
    try:
        fetch(base + "/health", timeout=2)
    except Exception:
        return ag.outcome(name, "skipped", message="未检测到本地 FreeSearch API（默认 127.0.0.1:8000）")
    started = time.time()
    items = []
    for q in query_variants(ctx["query"], dt.datetime.now().year)[:2]:
        url = base + "/search?" + urllib.parse.urlencode({
            "q": q, "max_results": min(ctx["max_results"], 30), "include_answer": "false",
        })
        try:
            data = json.loads(fetch(url, timeout=ctx["timeout"]))
        except Exception as exc:
            return ag.outcome(name, "error", message=f"FreeSearch 调用失败：{type(exc).__name__}")
        for row in data.get("results", []) or []:
            items.append(ag.make_item(
                name, q, title=row.get("title"), url=row.get("url"),
                snippet=row.get("content"), content=row.get("content"),
                published_at=row.get("published_date") or "",
                source=ag.urllib.parse.urlsplit(row.get("url", "")).hostname or "FreeSearch",
                source_type="web",
                tags=list(row.get("engines") or []) + ["freesearch"],
                metrics={"native_score": row.get("score") or 0},
                raw=row,
            ))
    return ag.outcome(name, "ok" if items else "skipped", items,
                      message="本地 FreeSearch API（RRF + 熔断）",
                      elapsed_ms=int((time.time() - started) * 1000))


# Agent Reach 渠道配置：只保留对赛事雷达有价值的渠道。
# login=True 的渠道必须探测到已登录才调用，避免无人值守扫描时弹出登录窗口。
AGENT_REACH_CHANNELS: List[Dict[str, Any]] = [
    {"channel": "bilibili", "zh": True, "label": "B站", "login": False},
    {"channel": "youtube", "zh": False, "label": "YouTube", "login": False},
    {"channel": "xiaohongshu", "zh": True, "label": "小红书", "login": True},
    {"channel": "reddit", "zh": False, "label": "Reddit", "login": True},
    {"channel": "twitter", "zh": False, "label": "X", "login": True},
    {"channel": "web", "zh": True, "label": "网页保底", "login": False},
]

def _ar_probe_channels(exe: str, timeout: int) -> Dict[str, Dict[str, Any]]:
    """运行 agent-reach channels，解析各渠道等级/登录态/可用动作；失败返回空 dict。

    1.6+ 的 channels 输出为 JSON：{"ok": true, "channels": [{name, level, login, actions}, ...]}
    其中 login.logged_in 为 true/false/null，可直接判断登录渠道是否可用。
    """
    code, stdout, _stderr = ag.run_cmd([exe, "channels"], timeout=timeout)
    if code != 0 or not stdout.strip():
        return {}
    data = ag.parse_json_loose(stdout)
    if not isinstance(data, dict) or not isinstance(data.get("channels"), list):
        return {}
    info: Dict[str, Dict[str, Any]] = {}
    for ch in data["channels"]:
        if not isinstance(ch, dict):
            continue
        cname = str(ch.get("name") or "")
        if not cname:
            continue
        login = ch.get("login") if isinstance(ch.get("login"), dict) else {}
        actions = [str(a.get("name")) for a in (ch.get("actions") or [])
                   if isinstance(a, dict) and a.get("name")]
        info[cname] = {
            "level": ch.get("level"),
            "logged_in": login.get("logged_in"),
            "actions": actions,
        }
    return info


def _ar_extract_rows(stdout: str) -> List[Dict[str, Any]]:
    """Agent Reach CLI 输出格式随渠道而变：优先解析 JSON，失败则从文本抽 URL 兜底。"""
    data = ag.parse_json_loose(stdout)
    rows = _ar_rows_from_data(data)
    if rows:
        return rows
    text = ag.clean_text(stdout, 6000)
    for m in re.finditer(r"https?://[^\s)\]>\"']+", text):
        url = m.group(0).rstrip(".,;")
        rows.append({"url": url, "title": "", "snippet": ""})
    return rows


def _ar_rows_from_data(data: Any, depth: int = 0) -> List[Dict[str, Any]]:
    """递归下钻找结果行数组。1.6+ 约定顶层为 {ok, result, error}，结果嵌在 result 里。"""
    if depth > 4:
        return []
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        if "url" in data or "link" in data or "href" in data:
            return [data]
        for key in ("results", "items", "data", "list", "videos", "notes",
                    "posts", "threads", "tweets", "result"):
            val = data.get(key)
            if val is None:
                continue
            got = _ar_rows_from_data(val, depth + 1)
            if got:
                return got
    return []


def _ar_row_to_item(name: str, ch: Dict[str, Any], query: str, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    url = row.get("url") or row.get("link") or row.get("href") or ""
    title = row.get("title") or row.get("name") or row.get("text") or ""
    snippet = (row.get("snippet") or row.get("description") or row.get("summary")
               or row.get("desc") or row.get("text") or row.get("content") or "")
    if not url and not title:
        return None
    published = (row.get("published_at") or row.get("published") or row.get("date")
                 or row.get("created_at") or row.get("publish_time") or "")
    author = (row.get("author") or row.get("user") or row.get("username")
              or row.get("nickname") or "")
    metrics: Dict[str, Any] = {}
    for mk, keys in (("like", ("like", "likes", "like_count", "digg", "star", "stars")),
                     ("comment", ("comment", "comments", "comment_count", "reply", "replies")),
                     ("read", ("read", "views", "view_count", "play", "plays"))):
        for k in keys:
            if row.get(k) is not None:
                try:
                    metrics[mk] = int(row[k])
                except (TypeError, ValueError):
                    pass
                break
    return ag.make_item(
        name, query, title=str(title), url=str(url), snippet=str(snippet), content="",
        published_at=str(published), author=str(author),
        source=f"Agent Reach·{ch['label']}", source_type="social",
        tags=["agent-reach", ch["channel"]], metrics=metrics, raw=row,
    )


def _ar_error_summary(stdout: str, stderr: str = "") -> str:
    """从 Agent Reach 的 JSON 输出里提取简短失败原因，避免整段 JSON 污染报告。"""
    data = ag.parse_json_loose(stdout)
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = " ".join(str(err.get(k) or "") for k in ("code", "message")).strip()
            if msg:
                return ag.clean_text(msg, 160)
        if data.get("ok") is False:
            return "渠道返回 ok=false"
    return ag.clean_text(stderr or stdout, 160)


def src_agent_reach(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "agent_reach"
    exe = shutil.which("agent-reach")
    if not exe:
        return ag.outcome(name, "skipped", message="未安装 Agent Reach CLI（可选，安装后可覆盖 X/Reddit/YouTube/B站/小红书等）")
    started = time.time()
    probe = _ar_probe_channels(exe, timeout=max(ctx["timeout"], 20))
    zh_query = ctx["query"]
    en_query = to_english_query(ctx["query"])
    notes: List[str] = []
    tasks: List[Dict[str, Any]] = []
    for ch in AGENT_REACH_CHANNELS:
        meta = probe.get(ch["channel"])
        if meta is None:
            notes.append(f"{ch['label']} 渠道未添加，跳过")
            continue
        if "search" not in (meta.get("actions") or []):
            notes.append(f"{ch['label']} 无 search 动作，跳过")
            continue
        if ch["login"] and not meta.get("logged_in"):
            # 登录渠道：登录态不为 true 一律不调用，防止无人值守时弹出登录窗口
            notes.append(f"{ch['label']} 未登录，跳过")
            continue
        tasks.append(ch)
    if not tasks:
        return ag.outcome(name, "skipped",
                          message="Agent Reach 已安装，但无可用渠道（登录渠道需先登录）：" + "；".join(notes),
                          elapsed_ms=int((time.time() - started) * 1000))

    def run_channel(ch: Dict[str, Any]):
        q = zh_query if ch["zh"] else en_query
        limit = max(3, min(ctx["max_results"], 10))
        cmd = [exe, ch["channel"], "search", q, "--limit", str(limit),
               "--timeout", str(max(ctx["timeout"], 20))]
        code, stdout, stderr = ag.run_cmd(cmd, timeout=max(ctx["timeout"], 30) + 10)
        if code != 0:
            return ch, None, _ar_error_summary(stdout, stderr)
        rows = _ar_extract_rows(stdout)
        if not rows:
            return ch, None, _ar_error_summary(stdout, stderr)
        items = [it for it in (_ar_row_to_item(name, ch, q, r) for r in rows) if it]
        return ch, items, ""

    items: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(tasks))) as pool:
        futures = [pool.submit(run_channel, ch) for ch in tasks]
        for future in concurrent.futures.as_completed(futures):
            ch, ch_items, err = future.result()
            if err:
                notes.append(f"{ch['label']} 调用失败：{err}")
            elif not ch_items:
                notes.append(f"{ch['label']} 无结果")
            else:
                items.extend(ch_items)
                notes.append(f"{ch['label']} {len(ch_items)} 条")
    return ag.outcome(name, "ok" if items else "skipped", items,
                      message="渠道结果：" + "；".join(notes),
                      elapsed_ms=int((time.time() - started) * 1000))


SOURCE_FUNCS = {
    "gdelt": src_gdelt,
    "hn_algolia": src_hn,
    "arxiv": src_arxiv,
    "github": src_github,
    "devfolio": src_devfolio,
    "site_scan": src_site_scan,
    "freesearch": src_freesearch,
    "agent_reach": src_agent_reach,
}


# ---------------------------------------------------------------- flow

def build_report(ctx: Dict[str, Any]) -> Dict[str, Any]:
    reports: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=ctx["workers"]) as pool:
        futures = {}
        for name in ctx["sources"]:
            futures[pool.submit(SOURCE_FUNCS[name], ctx)] = name
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                report = future.result()
            except Exception as exc:
                report = ag.outcome(name, "error", message=f"{type(exc).__name__}: {exc}")
            reports.append(report)
    order = {name: idx for idx, name in enumerate(ctx["sources"])}
    reports.sort(key=lambda x: order.get(x["engine"], 999))
    for row in reports:
        row["label"] = SOURCE_META.get(row["engine"], {}).get("label", row["engine"])

    all_items: List[Dict[str, Any]] = []
    for report in reports:
        all_items.extend(report.get("items", []) or [])

    for item in all_items:
        ag.score_item(item, ctx["query"], ctx["boost_terms"])
        boost_for_event(item)
    merged = ag.merge_duplicates(all_items)
    merged.sort(key=lambda x: x.get("score", 0), reverse=True)

    return {
        "meta": {
            "query": ctx["query"],
            "generated_at": ag.now_iso(),
            "mode": "global_free",
            "scope": "global",
            "lang": ag.detect_lang(ctx["query"]),
            "sources_requested": ctx["sources"],
            "raw_count": len(all_items),
            "result_count": min(len(merged), ctx["max_results"]),
        },
        "engines": [{k: v for k, v in row.items() if k != "items"} for row in reports],
        "results": merged[:ctx["max_results"]],
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="免费全球 AI 赛事/黑客松雷达（无搜索 API key）")
    p.add_argument("query", help="主题，如 'AI hackathon' 或 'AI 黑客松'")
    p.add_argument("--sources", default=",".join(DEFAULT_SOURCES), help="逗号分隔数据源")
    p.add_argument("--max", dest="max_results", type=int, default=30)
    p.add_argument("--fresh", choices=["day", "week", "month", "year"], default=None)
    p.add_argument("--boost-terms", default="报名,registration,deadline,截止,hackathon,黑客松,competition,大赛")
    p.add_argument("--timeout", type=int, default=20)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--json-out")
    p.add_argument("--html-out")
    p.add_argument("--md-out")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    sources = [x.strip() for x in args.sources.split(",") if x.strip()]
    unknown = [x for x in sources if x not in SOURCE_FUNCS]
    if unknown:
        raise SystemExit(f"未知数据源：{unknown}；可选：{list(SOURCE_FUNCS)}")
    ctx = {
        "query": args.query.strip(),
        "sources": sources,
        "max_results": max(1, args.max_results),
        "fresh": args.fresh,
        "boost_terms": ag.split_csv(args.boost_terms),
        "timeout": args.timeout,
        "workers": max(1, args.workers),
    }
    report = build_report(ctx)
    if args.json_out:
        path = Path(args.json_out); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.html_out:
        path = Path(args.html_out); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ag.render_html(report), encoding="utf-8")
    if args.md_out:
        path = Path(args.md_out); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ag.render_markdown(report), encoding="utf-8")

    print(f"全球雷达查询：{ctx['query']}")
    print(f"原始 {report['meta']['raw_count']} 条，去重后展示 {report['meta']['result_count']} 条")
    for row in report["engines"]:
        print(f"- {row['label']:<20} {row['status']:<8} {row['count']:>3} 条  {row['message']}")
    for idx, item in enumerate(report["results"][:15], 1):
        print(f"{idx:>2}. [{item['score']:>5}] {ag.clean_text(item['title'], 68)}  {item['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
