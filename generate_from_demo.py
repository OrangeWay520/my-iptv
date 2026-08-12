# -*- coding: utf-8 -*-
"""
generate_from_demo.py
======================
按 demo.txt 的频道列表与排序，从上游生成的 my_channels.m3u 中筛选出对应频道，
重新生成最终 my_channels.m3u / my_channels.txt：
  - 只保留 demo.txt 中列出的频道（保留其在源中的全部播放地址/台标）
  - 频道名称使用 demo.txt 中的原始名称（如 CCTV-1，保留连字符）
  - 频道顺序严格按 demo.txt 文本顺序（不做名称排序）
  - demo.txt 中按省份拆分的地方频道，合并为一个"地方频道"分类（广东排最前）

用法：在 generate_m3u.py 之后运行，或单独运行（基于已有的 my_channels.m3u）。
"""

import re
import os

BASE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(BASE, "demo.txt")
SRC_M3U = os.path.join(BASE, "my_channels.m3u")
OUT_M3U = os.path.join(BASE, "my_channels.m3u")
OUT_TXT = os.path.join(BASE, "my_channels.txt")

# 标准主题分类（非省份分类）
STANDARD_CATS = {
    "央视频道", "卫视频道", "港澳台频道", "少儿频道", "体育频道",
    "电影频道", "音乐频道", "纪录频道", "付费频道",
}


def norm(name: str) -> str:
    """归一化频道名：去括号后缀、去连字符/空格、转大写，仅用于跨文件匹配"""
    n = name.strip()
    n = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", n)
    n = n.replace("-", "").replace(" ", "").replace("＋", "+")
    return n.upper()


def strip_emoji(text: str) -> str:
    return re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]", "", text).strip()


def parse_demo(path: str):
    """解析 demo.txt -> [(分类名, [频道名...])]，保留文本顺序"""
    cats = []
    cur = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.endswith("#genre#"):
                cur = strip_emoji(line.split(",")[0])
                cats.append([cur, []])
                continue
            if cur is None:
                continue
            cats[-1][1].append(line)
    return cats


def parse_m3u(path: str):
    """解析 my_channels.m3u -> (epg_url, {归一化名: entry})"""
    epg_url = ""
    index = {}
    cur_attrs = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#EXTM3U"):
                m = re.search(r'x-tvg-url="([^"]*)"', line)
                if m:
                    epg_url = m.group(1)
                continue
            if line.startswith("#EXTINF:"):
                tvg_id = tvg_name = tvg_logo = ""
                mm = re.search(r'tvg-id="([^"]*)"', line)
                if mm: tvg_id = mm.group(1)
                mm = re.search(r'tvg-name="([^"]*)"', line)
                if mm: tvg_name = mm.group(1)
                mm = re.search(r'tvg-logo="([^"]*)"', line)
                if mm: tvg_logo = mm.group(1)
                name = line.split(",", 1)[1].strip() if "," in line else ""
                cur_attrs = {
                    "display": name, "tvg_id": tvg_id,
                    "tvg_name": tvg_name, "tvg_logo": tvg_logo,
                }
                continue
            if line.startswith("#"):
                continue
            if cur_attrs is None:
                continue
            key = norm(cur_attrs["display"])
            if key not in index:
                index[key] = {
                    "urls": [],
                    "tvg_id": cur_attrs["tvg_id"],
                    "tvg_name": cur_attrs["tvg_name"],
                    "tvg_logo": cur_attrs["tvg_logo"],
                }
            entry = index[key]
            if line not in entry["urls"]:
                entry["urls"].append(line)
            if not entry["tvg_logo"] and cur_attrs["tvg_logo"]:
                entry["tvg_logo"] = cur_attrs["tvg_logo"]
            if not entry["tvg_id"] and cur_attrs["tvg_id"]:
                entry["tvg_id"] = cur_attrs["tvg_id"]
    return epg_url, index


def main():
    demo_cats = parse_demo(DEMO)
    epg_url, index = parse_m3u(SRC_M3U)

    ordered = []      # [(分类名, [(频道名, entry)...])]
    local_items = []  # 地方频道合并列表（保持 demo 省份顺序，广东最前）
    missing = []
    matched_count = 0

    for cat, names in demo_cats:
        items = []
        for name in names:
            entry = index.get(norm(name))
            if entry:
                items.append((name, entry))   # 输出名用 demo 原始名（保留连字符等）
            else:
                missing.append(f"{cat}: {name}")
        matched_count += len(items)
        if cat in STANDARD_CATS:
            if items:
                ordered.append([cat, items])
        else:
            local_items.extend(items)

    # 地方频道插到"卫视频道"之后（央视 → 卫视 → 地方 → 港澳台 → ...）
    if local_items:
        insert_pos = len(ordered)
        if ordered and ordered[0][0] == "央视频道":
            insert_pos = 1
            if len(ordered) > 1 and ordered[1][0] == "卫视频道":
                insert_pos = 2
        ordered.insert(insert_pos, ["地方频道", local_items])

    # 写 M3U
    m3u_lines = []
    m3u_lines.append(f'#EXTM3U x-tvg-url="{epg_url}"' if epg_url else "#EXTM3U")
    m3u_lines.append("")
    for cat, items in ordered:
        total_urls = sum(len(it[1]["urls"]) for it in items)
        m3u_lines.append(f"# 分类: {cat} - {len(items)} 个频道, {total_urls} 个播放源")
        m3u_lines.append("")
        for display, entry in items:
            attrs = ""
            if entry["tvg_id"]:
                attrs += f' tvg-id="{entry["tvg_id"]}"'
            if entry["tvg_name"]:
                attrs += f' tvg-name="{entry["tvg_name"]}"'
            if entry["tvg_logo"]:
                attrs += f' tvg-logo="{entry["tvg_logo"]}"'
            attrs += f' group-title="{cat}"'
            for url in entry["urls"]:
                m3u_lines.append(f"#EXTINF:-1{attrs},{display}")
                m3u_lines.append(url)
        m3u_lines.append("")
    with open(OUT_M3U, "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_lines))

    # 写 TXT
    txt_lines = []
    for cat, items in ordered:
        txt_lines.append(f"{cat},#genre#")
        for display, entry in items:
            for url in entry["urls"]:
                txt_lines.append(f"{display},{url}")
        txt_lines.append("")
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines))

    print(f"匹配成功频道数(含多分类重复): {matched_count}")
    print(f"未找到播放源的频道: {len(missing)} 个")
    for m in missing:
        print(f"  ⚠ {m}")
    print(f"\n输出分类顺序:")
    for cat, items in ordered:
        print(f"  {cat}: {len(items)} 个频道")
    print(f"\n已生成: {OUT_M3U}")
    print(f"已生成: {OUT_TXT}")


if __name__ == "__main__":
    main()
