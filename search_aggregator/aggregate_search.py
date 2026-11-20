#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aggregate_search.py :: 10 引擎聚合搜索入口
==========================================

把 tavily / exa / perplexity / gemini / web-search / multi-search-engine /
wechat-article-search / aiskill-wechat-search / xiaohongshu / douyin 的结果
归一到统一 schema，做路由、并发扇出、失败降级、去重合并、加权排序。

用法：
  python aggregate_search.py "AI 黑客松 报名 2026" --engines auto --max 10 \
      --json-out output.json --html-out output.html --md-out output.md

凭证门禁：
  - 免费引擎：web_search / multi_search / wechat_article_search
  - 付费或需 key 引擎：必须同时满足 key 已配置 + 显式 --allow-paid
  - 不会自动激活账号、不会自动充值、不会读取或打印凭证明文
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = Path(os.environ.get("WORKBUDDY_SKILLS_DIR", str(Path.home() / ".workbuddy" / "skills")))

ALL_ENGINES = [
    "tavily",
    "exa",
    "perplexity",
    "gemini",
    "web_search",
    "multi_search",
    "wechat_article_search",
    "aiskill_wechat_search",
    "xiaohongshu",
    "douyin",
]

FREE_ENGINES = {"web_search", "multi_search", "wechat_article_search"}

ENGINE_META = {
    "tavily": {"label": "Tavily", "group": "web", "trust": 0.95, "kind": "api"},
    "exa": {"label": "Exa", "group": "web", "trust": 0.95, "kind": "api"},
    "perplexity": {"label": "Perplexity", "group": "answer", "trust": 0.90, "kind": "api"},
    "gemini": {"label": "Gemini", "group": "answer", "trust": 0.90, "kind": "api"},
    "web_search": {"label": "Web Search", "group": "web", "trust": 0.82, "kind": "free"},
    "multi_search": {"label": "Multi Search", "group": "web", "trust": 0.76, "kind": "free"},
    "wechat_article_search": {"label": "公众号搜索", "group": "wechat", "trust": 0.80, "kind": "free"},
    "aiskill_wechat_search": {"label": "10万+公众号", "group": "wechat", "trust": 0.92, "kind": "paid"},
    "xiaohongshu": {"label": "小红书", "group": "xhs", "trust": 0.78, "kind": "paid"},
    "douyin": {"label": "抖音", "group": "douyin", "trust": 0.78, "kind": "paid"},
}

KEY_REQUIREMENTS = {
    "tavily": ["TAVILY_API_KEY"],
    "exa": ["EXA_API_KEY"],
    "perplexity": ["PERPLEXITY_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "xiaohongshu": ["REDFOX_API_KEY"],
    "douyin": ["GUAIKEI_API_TOKEN"],
    "aiskill_wechat_search": ["PROXY_API_KEY"],
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "gbraid", "wbraid", "spm", "scm", "from", "src",
    "token", "sign", "signature", "timestamp", "nonce",
}


# ---------------------------------------------------------------- utilities

def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def clean_text(value: Any, limit: Optional[int] = None) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(x) for x in value if x is not None)
    text = html.unescape(str(value))
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[:limit].rstrip() + "..."
    return text


def strip_tags(value: str) -> str:
    value = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return clean_text(value)


def split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def is_zh(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def detect_lang(query: str) -> str:
    return "zh" if is_zh(query) else "en"


def detect_intent(query: str) -> List[str]:
    q = (query or "").lower()
    intents: List[str] = []
    if re.search(r"小红书|笔记|种草|爆款", q):
        intents.append("xhs")
    if re.search(r"抖音|短视频|热榜", q):
        intents.append("douyin")
    if re.search(r"公众号|微信文章|微信爆款", q):
        intents.append("wechat")
    if re.search(r"site:|filetype:|github|代码|api文档|docs", q):
        intents.append("code")
    if re.search(r"总结|综述|是什么|怎么办|原因|对比|研究", q):
        intents.append("answer")
    if re.search(r"黑客松|大赛|比赛|报名|征集|竞赛|hackathon|competition", q):
        intents.append("event")
    return intents


def parse_json_loose(text: str) -> Any:
    if not text:
        return None
    raw = text.strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    starts = [i for i in (raw.find("{"), raw.find("[")) if i >= 0]
    if not starts:
        return None
    start = min(starts)
    ends = [i for i in (raw.rfind("}"), raw.rfind("]")) if i >= 0]
    if not ends:
        return None
    end = max(ends)
    if end <= start:
        return None
    try:
        return json.loads(raw[start:end + 1])
    except Exception:
        return None


def run_cmd(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 30) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        return 124, "", f"timeout after {timeout}s: {exc}"
    except FileNotFoundError as exc:
        return 127, "", f"command not found: {exc}"
    except Exception as exc:
        return 1, "", f"{type(exc).__name__}: {exc}"


def http_get(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        try:
            return data.decode(charset, errors="replace")
        except LookupError:
            return data.decode("utf-8", errors="replace")


def http_post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: int = 30) -> Any:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    all_headers = {"Content-Type": "application/json", "User-Agent": UA}
    all_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=all_headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def key_present(names: Iterable[str]) -> bool:
    return any(bool(os.environ.get(name)) for name in names)


def key_name_present(names: Iterable[str]) -> Optional[str]:
    for name in names:
        if os.environ.get(name):
            return name
    return None


def fresh_days(fresh: Optional[str]) -> Optional[int]:
    return {"day": 1, "week": 7, "month": 30, "year": 365}.get(fresh or "")


def fresh_tavily(fresh: Optional[str]) -> Optional[str]:
    return {"day": "day", "week": "week", "month": "month", "year": "year"}.get(fresh or "")


def fresh_start_date(fresh: Optional[str]) -> str:
    days = fresh_days(fresh) or 30
    return (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y-%m-%d")


def normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parts = urllib.parse.urlsplit(url.strip())
        scheme = "https"
        host = (parts.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        path = re.sub(r"/+", "/", parts.path or "")
        path = path.rstrip("/")
        query = []
        for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=False):
            if k.lower() in TRACKING_PARAMS:
                continue
            query.append((k, v))
        query.sort()
        return urllib.parse.urlunsplit((scheme, host, path, urllib.parse.urlencode(query), ""))
    except Exception:
        return url.strip().lower()


def item_fingerprint(item: Dict[str, Any]) -> str:
    url = clean_text(item.get("url", ""), 1000)
    title = clean_text(item.get("title", ""), 240)
    host = urllib.parse.urlsplit(url).hostname or ""
    is_redirect = (
        host.endswith("weixin.sogou.com")
        or host.endswith("so.com")
        or "/link?" in url
        or "/link/" in url
    )
    if is_redirect and title:
        # 搜狗/360 的跳转链每次 token 不同，URL 归一化不可靠，用标题作为稳定指纹。
        base = "title|" + title
    else:
        base = normalize_url(url) or (title + "|" + clean_text(item.get("snippet", ""))[:120])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def make_item(engine: str, query: str, **kwargs: Any) -> Dict[str, Any]:
    meta = ENGINE_META.get(engine, {"group": "web", "trust": 0.7})
    metrics = kwargs.pop("metrics", {}) or {}
    tags = kwargs.pop("tags", []) or []
    item = {
        "id": "",
        "engine": engine,
        "engines": [engine],
        "engine_group": kwargs.pop("engine_group", meta["group"]),
        "query": query,
        "title": clean_text(kwargs.pop("title", ""), 240),
        "url": clean_text(kwargs.pop("url", ""), 1000),
        "snippet": clean_text(kwargs.pop("snippet", ""), 600),
        "content": clean_text(kwargs.pop("content", ""), 4000),
        "published_at": clean_text(kwargs.pop("published_at", ""), 60),
        "author": clean_text(kwargs.pop("author", ""), 120),
        "source": clean_text(kwargs.pop("source", ""), 120),
        "source_type": kwargs.pop("source_type", meta["group"]),
        "metrics": {
            "read": int(metrics.get("read") or 0),
            "like": int(metrics.get("like") or 0),
            "comment": int(metrics.get("comment") or 0),
            "share": int(metrics.get("share") or 0),
            "interaction": int(metrics.get("interaction") or 0),
            "native_score": float(metrics.get("native_score") or 0),
        },
        "tags": [clean_text(x, 40) for x in tags if clean_text(x, 40)],
        "score": 0.0,
        "score_reasons": [],
        "raw": kwargs.pop("raw", None),
    }
    item["id"] = item_fingerprint(item)
    return item


def outcome(engine: str, status: str, items: Optional[List[Dict[str, Any]]] = None,
            message: str = "", cost_note: str = "", elapsed_ms: int = 0) -> Dict[str, Any]:
    return {
        "engine": engine,
        "label": ENGINE_META.get(engine, {}).get("label", engine),
        "status": status,
        "count": len(items or []),
        "items": items or [],
        "message": clean_text(message, 400),
        "cost_note": clean_text(cost_note, 200),
        "elapsed_ms": elapsed_ms,
    }


# ---------------------------------------------------------------- HTML parsing

def is_search_query_page(url: str) -> bool:
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        path = (parts.path or "").lower()
        search_hosts = (
            "baidu.com", "so.com", "sogou.com", "bing.com", "yahoo.com",
            "brave.com", "ecosia.org", "google.com", "duckduckgo.com",
        )
        if not any(host.endswith(x) for x in search_hosts):
            return False
        query_keys = {"q", "wd", "query", "p", "keyword", "kw"}
        query_present = any(k.lower() in query_keys for k, _ in urllib.parse.parse_qsl(parts.query))
        return query_present and path in ("", "/", "/s", "/search", "/web", "/weixin", "/results")
    except Exception:
        return False


class AnchorParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.items: List[Dict[str, str]] = []
        self._href = ""
        self._text: List[str] = []
        self._in_anchor = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a" or self._in_anchor:
            return
        attr = {k.lower(): (v or "") for k, v in attrs}
        href = attr.get("href", "")
        if not href:
            return
        self._in_anchor = True
        self._href = href
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._in_anchor:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._in_anchor:
            return
        title = clean_text(" ".join(self._text))
        href = urllib.parse.urljoin(self.base_url, self._href)
        if title and href.startswith(("http://", "https://")):
            self.items.append({"title": title, "url": href, "snippet": ""})
        self._in_anchor = False
        self._href = ""
        self._text = []


def parse_result_blocks(page_html: str, base_url: str, engine_key: str) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []

    if engine_key == "bing":
        for block in re.findall(r"(?is)<li[^>]+class=[\"'][^\"']*b_algo[^\"']*[\"'][^>]*>(.*?)</li>", page_html):
            m = re.search(r"(?is)<h2[^>]*>\s*<a[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", block)
            if not m:
                continue
            url = urllib.parse.urljoin(base_url, html.unescape(m.group(1)))
            title = strip_tags(m.group(2))
            p = re.search(r"(?is)<p[^>]*>(.*?)</p>", block)
            snippet = strip_tags(p.group(1)) if p else ""
            if title and url.startswith(("http://", "https://")):
                results.append({"title": title, "url": url, "snippet": snippet})

    elif engine_key == "duckduckgo":
        for m in re.finditer(r"(?is)<a[^>]+class=[\"'][^\"']*result__a[^\"']*[\"'][^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", page_html):
            url = urllib.parse.urljoin(base_url, html.unescape(m.group(1)))
            title = strip_tags(m.group(2))
            tail = page_html[m.end():m.end() + 1200]
            sm = re.search(r"(?is)class=[\"'][^\"']*result__snippet[^\"']*[\"'][^>]*>(.*?)</(?:a|div)>", tail)
            snippet = strip_tags(sm.group(1)) if sm else ""
            if title and url.startswith(("http://", "https://")):
                results.append({"title": title, "url": url, "snippet": snippet})

    elif engine_key in {"baidu", "sogou", "so360", "yahoo", "brave", "ecosia", "generic"}:
        parser = AnchorParser(base_url)
        try:
            parser.feed(page_html)
        except Exception:
            pass
        seen = set()
        skip_terms = ("登录", "注册", "帮助", "设置", "下一页", "首页", "更多", "搜索", "隐私", "关于")
        for row in parser.items:
            url = row["url"]
            title = row["title"]
            host = urllib.parse.urlsplit(url).hostname or ""
            if not host or url in seen:
                continue
            if len(title) < 6 or any(term == title for term in skip_terms):
                continue
            if is_search_query_page(url) or "baidu.php" in url:
                # 过滤搜索引擎自身的「相关搜索/查询词页面」，只保留落地页或跳转链。
                continue
            seen.add(url)
            results.append(row)

    dedup, seen = [], set()
    for row in results:
        key = normalize_url(row["url"])
        if not key or key in seen:
            continue
        seen.add(key)
        dedup.append(row)
    return dedup


SEARCH_TEMPLATES = {
    "baidu": ("https://www.baidu.com/s?wd={q}&rn={n}", "baidu", "zh"),
    "bing_cn": ("https://cn.bing.com/search?q={q}&count={n}&setlang=zh-CN", "bing", "zh"),
    "bing_int": ("https://www.bing.com/search?q={q}&count={n}", "bing", "en"),
    "sogou": ("https://www.sogou.com/web?query={q}", "sogou", "zh"),
    "so360": ("https://www.so.com/s?q={q}", "so360", "zh"),
    "duckduckgo": ("https://html.duckduckgo.com/html/?q={q}", "duckduckgo", "en"),
    "brave": ("https://search.brave.com/search?q={q}", "brave", "en"),
    "yahoo": ("https://search.yahoo.com/search?p={q}", "yahoo", "en"),
    "ecosia": ("https://www.ecosia.org/search?q={q}", "ecosia", "en"),
}


# ---------------------------------------------------------------- score & merge

def query_tokens(query: str) -> List[str]:
    tokens: List[str] = []
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9+\-#]*|\d+(?:\.\d+)?", query or ""):
        token = m.group(0).lower()
        if len(token) >= 2:
            tokens.append(token)
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", query or ""):
        if len(run) <= 4:
            tokens.append(run)
        else:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    out, seen = [], set()
    for token in tokens:
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def parse_datetime(value: Any) -> Optional[dt.datetime]:
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        num = int(value)
        if num > 1_000_000_000_000:
            num //= 1000
        try:
            return dt.datetime.fromtimestamp(num).astimezone()
        except Exception:
            return None
    text = clean_text(value)
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    patterns = [
        r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if not m:
            continue
        try:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            hh, mm, ss = int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0)
            return dt.datetime(y, mo, d, hh, mm, ss).astimezone()
        except Exception:
            return None
    return None


def freshness_factor(published_at: str) -> Tuple[float, str]:
    dt_value = parse_datetime(published_at)
    if not dt_value:
        return 0.35, "发布时间未知"
    days = max(0, (dt.datetime.now().astimezone() - dt_value).days)
    if days <= 7:
        return 1.0, "近7天发布"
    if days <= 30:
        return 0.8, "近30天发布"
    if days <= 180:
        return 0.6, "近半年发布"
    if days <= 365:
        return 0.45, "近一年发布"
    return 0.25, "发布时间较早"


def score_item(item: Dict[str, Any], query: str, boost_terms: List[str]) -> None:
    tokens = query_tokens(query)
    title = clean_text(item.get("title", "")).lower()
    snippet = clean_text(item.get("snippet", "")).lower()
    content = clean_text(item.get("content", ""), 1200).lower()
    blob = " ".join([title * 3, snippet, content])
    if tokens:
        hits = sum(1 for t in tokens if t in blob)
        title_hits = sum(1 for t in tokens if t in title)
        coverage = hits / len(tokens)
        title_coverage = title_hits / len(tokens)
        relevance = min(1.0, 0.7 * coverage + 0.3 * title_coverage)
        reason = f"相关性命中 {hits}/{len(tokens)} 个查询词"
    else:
        relevance = 0.35
        reason = "查询词过短，按基础相关性计"

    boost = [x.lower() for x in boost_terms if clean_text(x)]
    if boost and any(x in blob for x in boost):
        relevance = min(1.0, relevance + 0.08)
        reason += "；命中业务加权词"

    trust = ENGINE_META.get(item.get("engine", ""), {}).get("trust", 0.7)
    fresh, fresh_reason = freshness_factor(item.get("published_at", ""))

    metrics = item.get("metrics", {}) or {}
    interaction = int(metrics.get("interaction") or 0)
    if not interaction:
        interaction = sum(int(metrics.get(k) or 0) for k in ("read", "like", "comment", "share"))
    metric_factor = min(1.0, math.log10(interaction + 1) / 5.0) if interaction else 0.0
    native = float(metrics.get("native_score") or 0)
    if native > 1.5:
        native = min(1.0, native / 15.0)
    metric_factor = max(metric_factor, min(1.0, native))

    score = 100.0 * (0.60 * relevance + 0.20 * float(trust) + 0.10 * fresh + 0.10 * metric_factor)
    item["score"] = round(score, 1)
    item["score_reasons"] = [reason, f"引擎可信度 {trust:.2f}", fresh_reason]
    if interaction:
        item["score_reasons"].append(f"互动数据 {interaction}")


def merge_duplicates(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        key = item.get("id") or item_fingerprint(item)
        groups.setdefault(key, []).append(item)

    merged: List[Dict[str, Any]] = []
    for group in groups.values():
        base = sorted(group, key=lambda x: x.get("score", 0), reverse=True)[0]
        clone = json.loads(json.dumps(base, ensure_ascii=False))
        clone["engines"] = sorted({e for row in group for e in row.get("engines", []) if e})
        if len(clone["engines"]) > 1:
            clone["score"] = round(min(100.0, clone["score"] + 1.5 * (len(clone["engines"]) - 1)), 1)
            clone["score_reasons"].append(f"多引擎交叉命中：{'/'.join(clone['engines'])}")
        for row in group:
            if len(row.get("content", "")) > len(clone.get("content", "")):
                clone["content"] = row["content"]
            if len(row.get("snippet", "")) > len(clone.get("snippet", "")):
                clone["snippet"] = row["snippet"]
            for key_name, value in (row.get("metrics") or {}).items():
                try:
                    clone["metrics"][key_name] = max(float(clone["metrics"].get(key_name) or 0), float(value or 0))
                except Exception:
                    pass
        merged.append(clone)
    return merged


# ---------------------------------------------------------------- adapters

def adapter_tavily(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "tavily"
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return outcome(name, "skipped", message="未配置 TAVILY_API_KEY")
    if not ctx["allow_paid"]:
        return outcome(name, "skipped", message="已配置凭证但未加 --allow-paid，未发起付费调用", cost_note="Tavily 按 API 用量计费")
    started = time.time()
    payload: Dict[str, Any] = {
        "query": ctx["query"],
        "search_depth": "advanced" if ctx["mode"] == "deep" else "basic",
        "max_results": min(ctx["max_results"], 20),
        "topic": "general",
        "include_answer": ctx["mode"] in ("balanced", "deep"),
        "include_published_date": True,
    }
    if ctx.get("fresh"):
        payload["time_range"] = fresh_tavily(ctx["fresh"])
    if ctx.get("include_domains"):
        payload["include_domains"] = ctx["include_domains"]
    if ctx.get("exclude_domains"):
        payload["exclude_domains"] = ctx["exclude_domains"]
    data = http_post_json("https://api.tavily.com/search", payload, {"Authorization": f"Bearer {key}"}, ctx["timeout"])
    items = []
    for row in data.get("results", []) or []:
        items.append(make_item(
            name, ctx["query"],
            title=row.get("title"), url=row.get("url"),
            snippet=row.get("content"), content=row.get("raw_content") or row.get("content"),
            published_at=row.get("published_date"), source=urllib.parse.urlsplit(row.get("url", "")).hostname or "",
            metrics={"native_score": row.get("score") or 0}, raw=row,
        ))
    if data.get("answer"):
        items.append(make_item(
            name, ctx["query"], title=f"Tavily 答案摘要：{ctx['query']}",
            url="https://app.tavily.com/", snippet=data.get("answer"),
            content=data.get("answer"), source_type="answer",
            source="Tavily Answer", tags=["answer"], raw={"answer": data.get("answer")},
        ))
    return outcome(name, "ok", items, elapsed_ms=int((time.time() - started) * 1000))


def adapter_exa(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "exa"
    key = os.getenv("EXA_API_KEY")
    if not key:
        return outcome(name, "skipped", message="未配置 EXA_API_KEY")
    if not ctx["allow_paid"]:
        return outcome(name, "skipped", message="已配置凭证但未加 --allow-paid，未发起付费调用", cost_note="Exa 按 API 用量计费")
    started = time.time()
    contents: Dict[str, Any] = {"highlights": True}
    if ctx["mode"] in ("balanced", "deep"):
        contents["text"] = True
    if ctx["mode"] == "deep":
        contents["summary"] = True
    payload: Dict[str, Any] = {
        "query": ctx["query"],
        "type": "deep" if ctx["mode"] == "deep" else "auto",
        "numResults": ctx["max_results"],
        "contents": contents,
    }
    if ctx.get("fresh"):
        payload["startPublishedDate"] = fresh_start_date(ctx["fresh"]) + "T00:00:00Z"
    if ctx.get("include_domains"):
        payload["includeDomains"] = ctx["include_domains"]
    if ctx.get("exclude_domains"):
        payload["excludeDomains"] = ctx["exclude_domains"]
    data = http_post_json("https://api.exa.ai/search", payload, {"x-api-key": key}, ctx["timeout"])
    items = []
    for row in data.get("results", []) or []:
        highlights = row.get("highlights") or []
        content = row.get("text") or row.get("summary") or ("\n".join(str(x) for x in highlights) if highlights else "")
        source_type = "code" if "code" in ctx["intents"] else "web"
        items.append(make_item(
            name, ctx["query"], title=row.get("title"), url=row.get("url"),
            snippet=row.get("summary") or (highlights[0] if highlights else ""),
            content=content, published_at=row.get("publishedDate"), author=row.get("author"),
            source=urllib.parse.urlsplit(row.get("url", "")).hostname or "Exa",
            source_type=source_type, metrics={"native_score": row.get("score") or 0}, raw=row,
        ))
    return outcome(name, "ok", items, elapsed_ms=int((time.time() - started) * 1000))


def collect_perplexity(data: Any, query: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []

    def walk(node: Any, key_hint: str = "") -> None:
        if isinstance(node, list):
            for row in node:
                walk(row, key_hint)
            return
        if not isinstance(node, dict):
            return
        title = node.get("title") or node.get("name")
        url = node.get("url") or node.get("link") or node.get("href")
        if title or url:
            items.append(make_item(
                "perplexity", query, title=title or url, url=url or "",
                snippet=node.get("snippet") or node.get("description") or node.get("text"),
                content=node.get("text") or node.get("content") or node.get("snippet"),
                published_at=node.get("publishedDate") or node.get("date"),
                source=urllib.parse.urlsplit(str(url or "")).hostname or "Perplexity",
                metrics={"native_score": node.get("score") or 0}, raw=node,
            ))
        answer = node.get("answer") or node.get("output") or (node.get("message") if key_hint == "answer" else None)
        if answer:
            text = clean_text(answer)
            items.append(make_item(
                "perplexity", query, title=f"Perplexity 答案摘要：{query}",
                url="https://www.perplexity.ai/", snippet=text, content=text,
                source_type="answer", source="Perplexity Answer", tags=["answer"],
                raw={"answer": answer},
            ))
        for key, value in node.items():
            if key in ("results", "web_results", "search_results", "citations", "sources"):
                walk(value, key)
            elif key in ("answer", "output"):
                walk({key: value}, key)

    walk(data)
    return items


def adapter_perplexity(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "perplexity"
    if not key_present(KEY_REQUIREMENTS[name]):
        return outcome(name, "skipped", message="未配置 PERPLEXITY_API_KEY")
    if not ctx["allow_paid"]:
        return outcome(name, "skipped", message="已配置凭证但未加 --allow-paid，未发起付费调用", cost_note="Perplexity 按 API 用量计费")
    script = SKILLS_ROOT / "perplexity" / "scripts" / "search.mjs"
    if not script.exists():
        return outcome(name, "error", message=f"脚本不存在：{script}")
    started = time.time()
    code, stdout, stderr = run_cmd(["node", str(script), ctx["query"], "--json"], timeout=ctx["timeout"])
    if code != 0:
        return outcome(name, "error", message=clean_text(stderr or stdout, 300))
    data = parse_json_loose(stdout)
    if data is None:
        return outcome(name, "error", message="无法解析 Perplexity 输出 JSON")
    items = collect_perplexity(data, ctx["query"])
    return outcome(name, "ok", items, elapsed_ms=int((time.time() - started) * 1000))


def adapter_gemini(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "gemini"
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        return outcome(name, "skipped", message="未配置 GEMINI_API_KEY / GOOGLE_API_KEY")
    if not ctx["allow_paid"]:
        return outcome(name, "skipped", message="已配置凭证但未加 --allow-paid，未发起付费调用", cost_note="Gemini Search Grounding 可能按搜索次数计费")
    started = time.time()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    prompt = (
        f"请联网检索并回答：{ctx['query']}\n"
        "要求：给出简明结论，并尽量引用可点击来源；区分事实与推测。"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
    }
    data = http_post_json(url, payload, {"x-goog-api-key": key}, ctx["timeout"])
    items: List[Dict[str, Any]] = []
    candidates = data.get("candidates") or []
    for candidate in candidates:
        parts = (((candidate.get("content") or {}).get("parts")) or [])
        answer = "\n".join(str(p.get("text", "")) for p in parts if p.get("text"))
        if answer:
            items.append(make_item(
                name, ctx["query"], title=f"Gemini 研究摘要：{ctx['query']}",
                url="https://aistudio.google.com/", snippet=answer, content=answer,
                source_type="answer", source="Gemini Answer", tags=["answer", "grounded"],
                raw={"answer": answer},
            ))
        metadata = candidate.get("groundingMetadata") or {}
        for chunk in metadata.get("groundingChunks") or []:
            web = chunk.get("web") or {}
            url_value = web.get("uri") or ""
            if not url_value:
                continue
            items.append(make_item(
                name, ctx["query"], title=web.get("title") or urllib.parse.urlsplit(url_value).hostname or "Gemini 来源",
                url=url_value, snippet=web.get("title") or "", source="Gemini Grounding",
                source_type="web", tags=["grounding"], raw=chunk,
            ))
    return outcome(name, "ok", items, elapsed_ms=int((time.time() - started) * 1000))


def parse_web_search_text(text: str, query: str) -> List[Dict[str, Any]]:
    pattern = re.compile(
        r"(?ms)^\s*(\d+)\.\s+(.*?)\n\s+(https?://\S+)\n\s+(.*?)(?=\n\s*\d+\.\s+|\Z)"
    )
    items = []
    for m in pattern.finditer(text or ""):
        items.append(make_item(
            "web_search", query, title=m.group(2), url=m.group(3),
            snippet=m.group(4), content=m.group(4),
            source=urllib.parse.urlsplit(m.group(3)).hostname or "",
        ))
    return items


def native_web_search(query: str, engine_keys: List[str], max_results: int, timeout: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for engine_key in engine_keys:
        template, parser_key, lang = SEARCH_TEMPLATES[engine_key]
        url = template.format(q=urllib.parse.quote(query, safe=""), n=max_results)
        try:
            page = http_get(url, timeout=min(timeout, 12))
        except Exception:
            continue
        for row in parse_result_blocks(page, url, parser_key)[:max_results]:
            items.append(make_item(
                "web_search", query, title=row.get("title"), url=row.get("url"),
                snippet=row.get("snippet"), source=urllib.parse.urlsplit(row.get("url", "")).hostname or engine_key,
                tags=[engine_key],
            ))
    return items


def adapter_web_search(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "web_search"
    started = time.time()
    script = SKILLS_ROOT / "web-search" / "scripts" / "web_search.py"
    if script.exists():
        cmd = [sys.executable, str(script), "search", ctx["query"], "--max", str(ctx["max_results"]), "--lang", ctx["lang"]]
        if ctx.get("fresh"):
            cmd += ["--fresh", ctx["fresh"]]
        code, stdout, stderr = run_cmd(cmd, timeout=ctx["timeout"])
        items = parse_web_search_text(stdout, ctx["query"]) if code == 0 else []
        if items:
            return outcome(name, "ok", items, elapsed_ms=int((time.time() - started) * 1000),
                           message="本地 web-search 脚本命中")
    # 当前环境常见情况：requests/bs4/ddgs 未安装。用 stdlib 直接抓 Baidu/Bing 作为降级。
    lang_keys = ["baidu", "bing_cn"] if ctx["lang"] == "zh" else ["bing_int", "duckduckgo"]
    items = native_web_search(ctx["query"], lang_keys, ctx["max_results"], ctx["timeout"])
    message = "web-search 脚本不可用，已用内置 stdlib fallback" if script.exists() else "web-search 脚本不存在，已用内置 stdlib fallback"
    return outcome(name, "ok" if items else "error", items, message=message,
                   elapsed_ms=int((time.time() - started) * 1000))


def adapter_multi_search(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "multi_search"
    started = time.time()
    if ctx.get("scope") == "cn" or ctx["lang"] == "zh":
        engine_keys = ["baidu", "bing_cn", "sogou", "so360", "bing_int"]
    else:
        engine_keys = ["duckduckgo", "bing_int", "brave", "yahoo", "ecosia", "baidu"]
    items: List[Dict[str, Any]] = []
    for engine_key in engine_keys:
        template, parser_key, _lang = SEARCH_TEMPLATES[engine_key]
        url = template.format(q=urllib.parse.quote(ctx["query"], safe=""), n=ctx["max_results"])
        try:
            page = http_get(url, timeout=min(ctx["timeout"], 10))
        except Exception:
            continue
        for row in parse_result_blocks(page, url, parser_key)[:ctx["max_results"]]:
            items.append(make_item(
                name, ctx["query"], title=row.get("title"), url=row.get("url"),
                snippet=row.get("snippet"), source=urllib.parse.urlsplit(row.get("url", "")).hostname or engine_key,
                tags=[engine_key],
            ))
        if len(items) >= ctx["max_results"] * 3:
            break
    return outcome(name, "ok" if items else "error", items,
                   message=f"扇出 {len(engine_keys)} 个网页搜索引擎",
                   elapsed_ms=int((time.time() - started) * 1000))


def adapter_wechat_article(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "wechat_article_search"
    script = SKILLS_ROOT / "wechat-article-search" / "scripts" / "search_wechat.js"
    if not script.exists():
        return outcome(name, "error", message=f"脚本不存在：{script}")
    started = time.time()
    cmd = ["node", str(script), ctx["query"], "-n", str(min(ctx["max_results"], 50))]
    days = fresh_days(ctx.get("fresh"))
    if days:
        cmd += ["-d", str(days)]
    code, stdout, stderr = run_cmd(cmd, timeout=ctx["timeout"])
    if code != 0:
        return outcome(name, "error", message=clean_text(stderr or stdout, 300))
    data = parse_json_loose(stdout)
    if not isinstance(data, dict):
        return outcome(name, "error", message="无法解析公众号搜索输出 JSON")
    items = []
    for row in data.get("articles", []) or []:
        items.append(make_item(
            name, ctx["query"], title=row.get("title"), url=row.get("url"),
            snippet=row.get("summary"), content=row.get("summary"),
            published_at=row.get("datetime") or row.get("date_text"),
            author=row.get("source"), source=row.get("source") or "微信公众号",
            source_type="wechat", raw=row,
        ))
    return outcome(name, "ok", items, elapsed_ms=int((time.time() - started) * 1000))


def adapter_aiskill_wechat(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "aiskill_wechat_search"
    if not ctx["allow_paid"]:
        return outcome(name, "skipped", message="按次计费引擎，需显式 --allow-paid 才调用", cost_note="AISkill 公众号搜索按次计费")
    script = SKILLS_ROOT / "aiskill-wechat-search" / "scripts" / "fetch_gzh_trends.py"
    if not script.exists():
        return outcome(name, "error", message=f"脚本不存在：{script}")
    started = time.time()
    cmd = [sys.executable, str(script), "--keyword", ctx["query"], "--max-items", str(min(ctx["max_results"], 50))]
    days = fresh_days(ctx.get("fresh"))
    if days:
        cmd += ["--publish-time", {1: "day", 7: "week", 30: "month"}.get(days, "year")]
    code, stdout, stderr = run_cmd(cmd, timeout=max(ctx["timeout"], 120))
    data = parse_json_loose(stdout) or {}
    if data.get("onboardingPreview"):
        return outcome(name, "skipped", message="本机尚未开通 AISkill 实时检索，未产生检索结果", cost_note="未调用检索接口")
    if data.get("balanceExhausted") or code == 2:
        return outcome(name, "error", message="服务余额不足；聚合器不自动充值、不自动重试", cost_note="费用状态以服务记录为准")
    if data.get("serviceError") or code == 3:
        return outcome(name, "error", message="服务授权或服务异常；聚合器不自动激活、不自动重试", cost_note="费用状态以服务记录为准")
    if code != 0:
        return outcome(name, "error", message=clean_text(stderr or stdout, 300))
    rows = data.get("items") or data.get("articles") or (data.get("data") or {}).get("items") or []
    items = []
    for row in rows:
        inter = row.get("interaction") or {}
        metrics = {
            "read": inter.get("read_count") or row.get("readCount") or 0,
            "like": inter.get("like_count") or row.get("likeCount") or 0,
            "comment": inter.get("comment_count") or row.get("commentCount") or 0,
            "share": inter.get("share_count") or row.get("shareCount") or 0,
            "interaction": sum([
                int(inter.get("read_count") or row.get("readCount") or 0),
                int(inter.get("like_count") or row.get("likeCount") or 0),
                int(inter.get("wow_count") or row.get("wowCount") or 0),
                int(inter.get("comment_count") or row.get("commentCount") or 0),
                int(inter.get("share_count") or row.get("shareCount") or 0),
                int(inter.get("favorite_count") or row.get("favoriteCount") or 0),
                int(inter.get("star_count") or row.get("starCount") or 0),
            ]),
        }
        items.append(make_item(
            name, ctx["query"], title=row.get("title"), url=row.get("url"),
            snippet=row.get("summary"), content=row.get("summary"),
            published_at=row.get("publishedAt"), author=row.get("author"),
            source=row.get("author") or "微信公众号", source_type="wechat",
            metrics=metrics, raw=row,
        ))
    return outcome(name, "ok", items, elapsed_ms=int((time.time() - started) * 1000))


def adapter_xiaohongshu(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "xiaohongshu"
    if not key_present(KEY_REQUIREMENTS[name]):
        return outcome(name, "skipped", message="未配置 REDFOX_API_KEY")
    if not ctx["allow_paid"]:
        return outcome(name, "skipped", message="已配置凭证但未加 --allow-paid，未发起调用", cost_note="红狐数据接口可能按套餐计费")
    script = SKILLS_ROOT / "xiaohongshu-notes-search" / "scripts" / "fetch_xhs_hot_articles.py"
    if not script.exists():
        return outcome(name, "error", message=f"脚本不存在：{script}")
    started = time.time()
    cmd = [
        sys.executable, str(script), "--keyword", ctx["query"],
        "--start-date", fresh_start_date(ctx.get("fresh")),
        "--page-num", "1", "--page-size", str(min(ctx["max_results"], 50)),
        "--output-format", "json",
    ]
    code, stdout, stderr = run_cmd(cmd, timeout=max(ctx["timeout"], 90))
    if code != 0:
        return outcome(name, "error", message=clean_text(stderr or stdout, 300))
    data = parse_json_loose(stdout) or {}
    rows = data.get("items") or (data.get("data") or {}).get("items") or []
    items = []
    for row in rows:
        items.append(make_item(
            name, ctx["query"], title=row.get("title"), url=row.get("noteLink") or row.get("shareInfoLink"),
            snippet=row.get("desc"), content=row.get("desc"), published_at=row.get("createTime"),
            author=row.get("authorNickname"), source="小红书", source_type="xhs",
            metrics={
                "like": row.get("likedCount") or 0,
                "comment": row.get("commentsCount") or 0,
                "share": row.get("sharedCount") or 0,
                "interaction": row.get("interactiveCount") or 0,
                "native_score": row.get("totalScore") or 0,
            },
            tags=[f"相关性{row.get('relevanceScore', '')}", f"热度{row.get('popularityScore', '')}"],
            raw=row,
        ))
    return outcome(name, "ok", items, elapsed_ms=int((time.time() - started) * 1000))


def find_douyin_rows(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("data", "list", "items", "awemes", "results", "videos"):
        value = data.get(key)
        if isinstance(value, list):
            rows = [x for x in value if isinstance(x, dict)]
            if rows:
                return rows
        elif isinstance(value, dict):
            rows = find_douyin_rows(value)
            if rows:
                return rows
    rows = [x for x in data.values() if isinstance(x, dict) and ("desc" in x or "aweme_id" in x)]
    return rows


def adapter_douyin(ctx: Dict[str, Any]) -> Dict[str, Any]:
    name = "douyin"
    if not key_present(KEY_REQUIREMENTS[name]):
        return outcome(name, "skipped", message="未配置 GUAIKEI_API_TOKEN")
    if not ctx["allow_paid"]:
        return outcome(name, "skipped", message="已配置凭证但未加 --allow-paid，未发起调用", cost_note="抖音数据 API 可能按套餐计费")
    script = SKILLS_ROOT / "douyin-data-assistant" / "src" / "douyin" / "search-cli.js"
    if not script.exists():
        return outcome(name, "error", message=f"脚本不存在：{script}")
    started = time.time()
    cmd = ["node", str(script), "--keyword", ctx["query"], "--limit", str(ctx["max_results"]), "--sort", "1" if "hot" in ctx["intents"] else "0"]
    days = fresh_days(ctx.get("fresh"))
    if days:
        cmd += ["--time", str(1 if days <= 1 else 7 if days <= 7 else 180)]
    code, stdout, stderr = run_cmd(cmd, timeout=ctx["timeout"])
    if code == 3:
        return outcome(name, "error", message="GUAIKEI_API_TOKEN 缺失或无效（auth_required）")
    if code != 0:
        return outcome(name, "error", message=clean_text(stderr or stdout, 300))
    data = parse_json_loose(stdout)
    rows = find_douyin_rows(data)
    items = []
    for row in rows:
        published = row.get("create_time_str") or row.get("create_time")
        metrics = {
            "like": row.get("digg_count") or 0,
            "comment": row.get("comment_count") or 0,
            "share": row.get("share_count") or 0,
            "interaction": sum(int(row.get(k) or 0) for k in ("digg_count", "comment_count", "share_count", "collect_count")),
        }
        items.append(make_item(
            name, ctx["query"], title=row.get("desc") or row.get("title"),
            url=row.get("share_url") or row.get("url"), snippet=row.get("desc"),
            content=row.get("desc"), published_at=published,
            author=row.get("author_nickname"), source="抖音", source_type="douyin",
            metrics=metrics, tags=row.get("tags") or [], raw=row,
        ))
    return outcome(name, "ok", items, elapsed_ms=int((time.time() - started) * 1000))


ADAPTERS = {
    "tavily": adapter_tavily,
    "exa": adapter_exa,
    "perplexity": adapter_perplexity,
    "gemini": adapter_gemini,
    "web_search": adapter_web_search,
    "multi_search": adapter_multi_search,
    "wechat_article_search": adapter_wechat_article,
    "aiskill_wechat_search": adapter_aiskill_wechat,
    "xiaohongshu": adapter_xiaohongshu,
    "douyin": adapter_douyin,
}


# ---------------------------------------------------------------- renderers

def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    lines = [
        f"# 聚合搜索报告：{meta['query']}",
        "",
        f"- 生成时间：{meta['generated_at']}",
        f"- 模式：{meta['mode']} / 范围：{meta['scope']} / 语言：{meta['lang']}",
        f"- 结果数：{meta['result_count']}（原始 {meta['raw_count']} 条，去重后 {meta['result_count']} 条）",
        "",
        "## 引擎状态",
        "",
        "| 引擎 | 状态 | 条数 | 耗时 | 说明 |",
        "|---|---|---:|---:|---|",
    ]
    for row in report["engines"]:
        lines.append(
            f"| {row['label']} | {row['status']} | {row['count']} | {row['elapsed_ms']}ms | {row['message'] or '-'} |"
        )
    lines += ["", "## 结果", ""]
    for idx, item in enumerate(report["results"], 1):
        title = clean_text(item.get("title"), 160) or "无标题"
        url = item.get("url") or ""
        title_md = f"[{title}]({url})" if url else title
        metrics = item.get("metrics", {})
        metric_text = " / ".join(
            f"{label} {metrics.get(key)}" for key, label in (
                ("read", "阅读"), ("like", "点赞"), ("comment", "评论"),
                ("share", "分享"), ("interaction", "互动"),
            ) if metrics.get(key)
        )
        lines.append(f"### {idx}. {title_md}")
        lines.append("")
        lines.append(f"- 评分：{item.get('score')}；来源：{'/'.join(item.get('engines', []))}；类型：{item.get('source_type')}")
        if item.get("source") or item.get("author"):
            lines.append(f"- 作者/来源：{item.get('author') or '-'} / {item.get('source') or '-'}")
        if item.get("published_at"):
            lines.append(f"- 时间：{item['published_at']}")
        if metric_text:
            lines.append(f"- 互动：{metric_text}")
        if item.get("snippet"):
            lines.append(f"- 摘要：{clean_text(item['snippet'], 400)}")
        lines.append("")
    return "\n".join(lines)


def render_html(report: Dict[str, Any]) -> str:
    meta = report["meta"]

    def e(value: Any) -> str:
        return html.escape(str(value or ""))

    status_rows = "".join(
        f"<tr><td>{e(row['label'])}</td><td class='st {e(row['status'])}'>{e(row['status'])}</td>"
        f"<td>{row['count']}</td><td>{row['elapsed_ms']}ms</td><td>{e(row['message'] or '-')}</td></tr>"
        for row in report["engines"]
    )
    cards = []
    for idx, item in enumerate(report["results"], 1):
        title = clean_text(item.get("title"), 180) or "无标题"
        url = item.get("url") or ""
        title_html = f"<a href='{e(url)}' target='_blank' rel='noopener'>{e(title)}</a>" if url else e(title)
        metrics = item.get("metrics", {})
        metric_parts = []
        for key, label in (("read", "阅读"), ("like", "点赞"), ("comment", "评论"), ("share", "分享"), ("interaction", "互动")):
            if metrics.get(key):
                metric_parts.append(f"{label} {e(metrics[key])}")
        badges = "".join(f"<span class='badge'>{e(x)}</span>" for x in item.get("engines", []))
        reason = "；".join(item.get("score_reasons", []))
        cards.append(
            f"<article class='card' data-engine='{e(' '.join(item.get('engines', [])))}' data-type='{e(item.get('source_type'))}'>"
            f"<div class='card-top'><span class='rank'>{idx}</span><div class='card-title'>{title_html}</div>"
            f"<span class='score'>{e(item.get('score'))}</span></div>"
            f"<div class='badges'>{badges}<span class='badge type'>{e(item.get('source_type'))}</span></div>"
            f"<p class='snippet'>{e(item.get('snippet') or item.get('content'))}</p>"
            f"<div class='meta'>{e(item.get('source') or '')} {e(item.get('author') or '')} {e(item.get('published_at') or '')} {' · '.join(metric_parts)}</div>"
            f"<div class='reason'>{e(reason)}</div>"
            f"</article>"
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>聚合搜索报告 - {e(meta['query'])}</title>
<style>
:root {{ --bg:#f6f8fb; --card:#fff; --text:#18212f; --muted:#667085; --line:#e4e9f0; --brand:#2563eb; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; line-height:1.6; }}
.wrap {{ max-width:1080px; margin:0 auto; padding:28px 18px 60px; }}
h1 {{ font-size:28px; margin:0 0 8px; }}
.sub {{ color:var(--muted); margin-bottom:22px; }}
.panel {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:18px; margin-bottom:18px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ color:var(--muted); font-weight:600; }}
.st.ok {{ color:#067647; }} .st.skipped {{ color:#b54708; }} .st.error {{ color:#b42318; }}
.filters {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px; }}
.filters button {{ border:1px solid var(--line); background:#fff; color:var(--text); border-radius:999px; padding:6px 14px; cursor:pointer; }}
.filters button.active {{ background:var(--brand); color:#fff; border-color:var(--brand); }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px 18px; margin-bottom:12px; }}
.card-top {{ display:flex; align-items:flex-start; gap:12px; }}
.rank {{ color:var(--muted); font-weight:700; min-width:24px; }}
.card-title {{ flex:1; font-size:16px; font-weight:700; }}
.card-title a {{ color:var(--text); text-decoration:none; }}
.card-title a:hover {{ color:var(--brand); }}
.score {{ color:var(--brand); font-weight:800; }}
.badges {{ margin:8px 0 0 36px; display:flex; gap:6px; flex-wrap:wrap; }}
.badge {{ font-size:11px; color:#344054; background:#eef2f7; border-radius:999px; padding:2px 8px; }}
.badge.type {{ background:#e8f1ff; color:#175cd3; }}
.snippet {{ margin:10px 0 6px 36px; color:#344054; }}
.meta, .reason {{ margin-left:36px; font-size:12px; color:var(--muted); }}
.reason {{ margin-top:6px; }}
</style>
</head>
<body>
<div class="wrap">
<h1>聚合搜索报告</h1>
<div class="sub">查询：{e(meta['query'])} · 生成时间：{e(meta['generated_at'])} · 原始 {meta['raw_count']} 条 / 去重后 {meta['result_count']} 条</div>
<div class="panel"><h3>引擎状态</h3><table><thead><tr><th>引擎</th><th>状态</th><th>条数</th><th>耗时</th><th>说明</th></tr></thead><tbody>{status_rows}</tbody></table></div>
<div class="filters"><button class="active" data-filter="all">全部</button><button data-filter="web">网页</button><button data-filter="answer">答案</button><button data-filter="wechat">公众号</button><button data-filter="xhs">小红书</button><button data-filter="douyin">抖音</button></div>
<div id="results">{''.join(cards) or '<div class="panel">没有可用结果。</div>'}</div>
</div>
<script>
document.querySelectorAll('.filters button').forEach(function(btn){{
  btn.addEventListener('click', function(){{
    document.querySelectorAll('.filters button').forEach(function(b){{b.classList.remove('active');}});
    btn.classList.add('active');
    var f=btn.dataset.filter;
    document.querySelectorAll('.card').forEach(function(card){{
      card.style.display=(f==='all'||card.dataset.type===f)?'block':'none';
    }});
  }});
}});
</script>
</body>
</html>"""


# ---------------------------------------------------------------- main flow

def build_context(args: argparse.Namespace) -> Dict[str, Any]:
    query = args.query.strip()
    if not query:
        raise SystemExit("查询词不能为空")
    if args.engines in ("auto", "all"):
        engines = list(ALL_ENGINES)
    else:
        engines = [x.strip() for x in args.engines.split(",") if x.strip()]
        unknown = [x for x in engines if x not in ALL_ENGINES]
        if unknown:
            raise SystemExit(f"未知引擎：{', '.join(unknown)}。可选：{', '.join(ALL_ENGINES)}")
    return {
        "query": query,
        "engines": engines,
        "mode": args.mode,
        "scope": args.scope,
        "lang": detect_lang(query),
        "intents": detect_intent(query),
        "max_results": max(1, args.max_results),
        "fresh": args.fresh,
        "allow_paid": args.allow_paid,
        "include_domains": split_csv(args.include_domains),
        "exclude_domains": split_csv(args.exclude_domains),
        "boost_terms": split_csv(args.boost_terms),
        "timeout": args.timeout,
        "workers": max(1, args.workers),
    }


def run_all(ctx: Dict[str, Any]) -> Dict[str, Any]:
    engine_reports: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=ctx["workers"]) as pool:
        futures = {}
        for engine in ctx["engines"]:
            futures[pool.submit(ADAPTERS[engine], ctx)] = engine
        for future in concurrent.futures.as_completed(futures):
            engine = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = outcome(engine, "error", message=f"{type(exc).__name__}: {exc}")
            engine_reports.append(result)

    order = {name: idx for idx, name in enumerate(ctx["engines"])}
    engine_reports.sort(key=lambda x: order.get(x["engine"], 999))

    all_items: List[Dict[str, Any]] = []
    for report in engine_reports:
        all_items.extend(report.get("items", []))

    for item in all_items:
        score_item(item, ctx["query"], ctx["boost_terms"])
    merged = merge_duplicates(all_items)
    merged.sort(key=lambda x: x.get("score", 0), reverse=True)
    results = merged[:ctx["max_results"]]

    return {
        "meta": {
            "query": ctx["query"],
            "generated_at": now_iso(),
            "mode": ctx["mode"],
            "scope": ctx["scope"],
            "lang": ctx["lang"],
            "intents": ctx["intents"],
            "engines_requested": ctx["engines"],
            "allow_paid": ctx["allow_paid"],
            "raw_count": len(all_items),
            "result_count": len(results),
        },
        "engines": [{k: v for k, v in row.items() if k != "items"} for row in engine_reports],
        "results": results,
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="10 引擎聚合搜索：统一 schema + 路由 + 降级 + 去重 + 排序")
    parser.add_argument("query", help="查询词")
    parser.add_argument("--engines", default="auto", help="逗号分隔引擎名；auto/all 表示全部（受凭证门禁约束）")
    parser.add_argument("--mode", choices=["fast", "balanced", "deep"], default="balanced")
    parser.add_argument("--scope", choices=["auto", "web", "cn", "global", "social", "answer"], default="auto")
    parser.add_argument("--max", dest="max_results", type=int, default=10, help="最终返回条数")
    parser.add_argument("--fresh", choices=["day", "week", "month", "year"], default=None)
    parser.add_argument("--allow-paid", action="store_true", help="显式允许调用需 key 或按次计费的引擎")
    parser.add_argument("--include-domains", default=None, help="逗号分隔，限定域名")
    parser.add_argument("--exclude-domains", default=None, help="逗号分隔，排除域名")
    parser.add_argument("--boost-terms", default=None, help="逗号分隔，相关性加权词")
    parser.add_argument("--timeout", type=int, default=30, help="单引擎超时秒数")
    parser.add_argument("--workers", type=int, default=5, help="并发引擎数")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--html-out", default=None)
    parser.add_argument("--md-out", default=None)
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    ctx = build_context(args)
    report = run_all(ctx)

    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.html_out:
        path = Path(args.html_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_html(report), encoding="utf-8")
    if args.md_out:
        path = Path(args.md_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(report), encoding="utf-8")

    print(f"查询：{ctx['query']}")
    print(f"原始结果：{report['meta']['raw_count']}；去重后展示：{report['meta']['result_count']}")
    for row in report["engines"]:
        print(f"- {row['label']:<16} {row['status']:<8} {row['count']:>3} 条  {row['message']}")
    for idx, item in enumerate(report["results"][:10], 1):
        print(f"{idx:>2}. [{item['score']:>5}] {clean_text(item['title'], 70)}  {item['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
