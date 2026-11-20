# -*- coding: utf-8 -*-
"""
小红书小工具 1.0.3 数据合并（C 档最广口径）
==============================================
主体：output/events_data.json 的 17 条（2026-11-19 快照核对，今日探活 200）
补充：minitool/dist/assets/data.js 中的 8 条「纯学生限定」赛事
      （2026-11-14 核对，链接取自 output/urls.txt，今日已随 24 条一并探活 200）
输出：minitool/data/events_data_C.json（snap=2026-11-20）
"""
import json
import re

LINKS = {
    "CrossPointX": "https://cpx2026.devpost.com/",
    "荣耀·英特尔": "https://www.honor.com/cn/ai-smart-innovation-challenge/",
    "臺大×華南": "https://luma.com/hccyc199",
    "AI芯智能赛道": "https://m.saikr.com/vse/AI2026ZNCX",
    "Global AI Builder": "https://global-ai-builders-challenge.devpost.com/",
    "Qoder": "https://tianchi.aliyun.com/competition/entrance/532536",
    "SpectoV": "https://snh.hiringspectov.com/",
    "GenHacks": "https://genhacks-open.devpost.com/",
}

# dropped 里对应的学生赛事条目（合并后已收录，需从剔除清单移除，避免自相矛盾）
DROP_KEYS = ["CrossPointX", "荣耀·英特尔", "臺大×華南", "AI芯",
             "Global AI Builder", "Qoder", "SpectoV"]

main = json.load(open("output/events_data.json", encoding="utf-8"))
s = open("minitool/dist/assets/data.js", encoding="utf-8").read()
c14 = json.loads(re.search(r"window\.EVENTS_DATA=(\{.*\});", s, re.S).group(1))

student = [e for e in c14["events"] if "纯学生限定" in str(e.get("eligibility", ""))]
assert len(student) == 8, f"学生赛事应为 8 条，实际 {len(student)}"

events = [dict(e) for e in main["events"]]
exist_names = {e["name"] for e in events}
added = []
for e in student:
    link = None
    for k, u in LINKS.items():
        if k in e["name"]:
            link = u
            break
    assert link, f"未匹配到链接: {e['name']}"
    if e["name"] in exist_names:
        continue
    e = dict(e)
    e["link"] = link
    events.append(e)
    added.append(e["name"])

# dropped 移除已收录的学生赛事条目
dropped = [d for d in main.get("dropped", [])
           if not any(k in str(d.get("name", "")) for k in DROP_KEYS)]

out = {
    "snap": "2026-11-20",
    "title_date": "2026-11-20",
    "today": "2026-11-20",
    "identity": "C",
    "note": "1.0.3 合并数据：11-19 快照 17 条（A 档核对）+ 11-14 核对并今日复验 200 的 8 条纯学生赛事（C 档最广口径）",
    "events": events,
    "dropped": dropped,
}
import os
os.makedirs("minitool/data", exist_ok=True)
json.dump(out, open("minitool/data/events_data_C.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"合并完成：events={len(events)}（新增 {len(added)} 条学生赛事）｜ dropped={len(dropped)} 类")
for n in added:
    print("  +", n)
# 校验：截止日不早于今天、链接齐全
bad = [e["name"] for e in events if not e.get("link") or str(e.get("deadline", ""))[:10] < "2026-11-20"]
print("校验（链接齐全且截止未过）:", "PASS" if not bad else f"FAIL {bad}")
