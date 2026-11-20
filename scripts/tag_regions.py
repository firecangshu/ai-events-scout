# -*- coding: utf-8 -*-
"""按主办方/线下场地为赛事补区域多标签（大湾区⊂珠三角⊂华南，多标签并存）。"""
import io, json, sys, os

REGIONS = {
  1: ["华南", "珠三角"],                                   # 中国电科（北京主办方，全国赛道）→ 线上报名，按主办方华北?电科总部北京
  2: ["华北"],                                             # 工信部火炬中心（北京）
  3: ["国外"],                                             # 沙特麦地那
  4: ["华南", "珠三角", "大湾区"],                          # 群核科技（杭州）→ 线上赛。主办在长三角
  5: ["华东", "长三角"],                                    # 西浦/昆杜/苏大（苏州）
  6: ["华南", "珠三角", "大湾区"],                          # 荣耀（深圳）
  7: ["华东", "中国台湾"],                                      # 臺大（台北）→ 国内口径下归入大中华
  8: ["华北", "华南", "华东", "华中", "西南", "东北"],       # 华为区域赛覆盖北部/南部/中部/西南/西部
  9: ["国外"],                                             # Google/Kaggle
  10: ["全国"],                                            # 线上答题，不限地区
  11: ["国外"],                                            # Refactor The World
  12: ["全国"],                                            # 6G 推进组+OPPO 线上
  13: ["华东"],                                            # 中科大（合肥）
  14: ["华南", "中国台湾"],                                     # 中国台湾佛光大学
  15: ["华东", "长三角"],                                   # 阿里云 Qoder（杭州）
  16: ["国外"],                                            # SpectoV（印度）
  17: ["华东", "长三角", "大湾区"],                          # 支付宝（上海/杭州），线下决赛路演
  18: ["不限"],                                            # AWS 全球合作伙伴
  19: ["国外"],                                            # Devpost/GenHacks
  20: ["全国"],                                            # 线上创作
  21: ["华北"],                                            # 开放原子（北京），真机线下
  22: ["华东", "长三角"],                                   # 天池（杭州）
  23: ["国外"],                                            # 迪拜
  24: ["国外"],                                            # Google/Kaggle
}

def main():
    p = "output/events_data.json"
    d = json.loads(io.open(p, encoding="utf-8").read())
    fixed = 0
    for i, e in enumerate(d["events"], 1):
        regs = REGIONS.get(i)
        if not regs:
            print("缺标注: #%d %s" % (i, e["name"][:30])); sys.exit(1)
        e["regions"] = regs
        fixed += 1
    # 校验：非全国/国外/不限的，必须有宏观区域
    for i, e in enumerate(d["events"], 1):
        r = e["regions"]
        if "全国" in r or "国外" in r or "不限" in r:
            assert len(r) == 1, "#%d 应为单标签: %s" % (i, r)
    io.open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    print("已标注 %d 条区域多标签" % fixed)
    # 统计
    from collections import Counter
    c = Counter()
    for e in d["events"]:
        for r in e["regions"]:
            c[r] += 1
    for k, v in sorted(c.items(), key=lambda x: -x[1]):
        print("  %-4s %d 条" % (k, v))

if __name__ == "__main__":
    main()
