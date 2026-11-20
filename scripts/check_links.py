# -*- coding: utf-8 -*-
"""
链接探活脚本（ai-events-scout skill 配套）
========================================
逐条核验赛事「网页报名入口」是否可访问（HTTP 200）。按口径，仅网页入口可访问
（探活 200）的赛事才纳入清单；仅邮箱/扫码/公众号文章无清晰网页入口的一律剔除。

用法：
  python check_links.py url1 url2 url3 ...
  # 或从文件读取（每行一个 URL）：
  python check_links.py --file urls.txt

输出：每行 "URL -> 状态码 (耗时ms)"，并对非 200 给出剔除提示。
退出码：全部 200 返回 0，存在非 200 返回 1（便于脚本判断）。
"""
import sys
import time
import argparse

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _check_curl(url, timeout=25):
    """优先用 curl：与既定工作流一致，且在沙箱内对 Devpost 等站点探活可靠。"""
    import subprocess
    try:
        t0 = time.time()
        proc = subprocess.run(
            ["curl", "-L", "-A", UA, "-o", "/dev/null", "-w", "%{http_code}",
             "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout + 10,
        )
        ms = int((time.time() - t0) * 1000)
        out = (proc.stdout or "").strip()
        if out.isdigit():
            return int(out), ms
        return None, ms
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None, 0


def _check_urllib(url, timeout=25):
    """curl 不可用时的回退方案。"""
    import urllib.request
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), int((time.time() - t0) * 1000)
    except Exception:
        return None, int((time.time() - t0) * 1000)


def check(url, timeout=25):
    # 先试 curl，失败（含非数字返回）再回退 urllib
    code, ms = _check_curl(url, timeout)
    if code is not None:
        return code, ms
    return _check_urllib(url, timeout)


def main():
    ap = argparse.ArgumentParser(description="赛事报名入口 HTTP 探活")
    ap.add_argument("urls", nargs="*", help="待核验的 URL 列表")
    ap.add_argument("--file", default=None, help="从文件读取 URL（每行一个）")
    ap.add_argument("--timeout", type=int, default=25)
    args = ap.parse_args()

    urls = list(args.urls)
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
    if not urls:
        sys.stderr.write("未提供任何 URL。用法：python check_links.py url1 url2 ...\n")
        sys.exit(2)

    bad = 0
    for u in urls:
        code, ms = check(u, args.timeout)
        if code == 200:
            print(f"[OK]   {u} -> 200 ({ms}ms)")
        else:
            bad += 1
            print(f"[FAIL] {u} -> {code} ({ms}ms)  ⚠ 非 200，按口径需剔除或换源核验")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
