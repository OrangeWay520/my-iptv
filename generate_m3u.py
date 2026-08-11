"""
自定义IPTV播放列表生成器
从多个上游源获取直播源，按分类筛选合并，生成个性化M3U播放列表
"""

import re
import urllib.request
import urllib.error
import os
import sys
import time
from datetime import datetime

# ============================================================
# 配置区域 - 你可以按需修改
# ============================================================

# 多个上游数据源（按优先级排列，前面的源优先使用其台标和EPG信息）
# 每个源可以是 M3U 或 TXT 格式
# 注意：GitHub Actions 运行在海外服务器，raw.githubusercontent.com 的链接更稳定
SOURCE_URLS = [
    # fanmingming/live - 热门源，频道齐全，台标完善
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u",

    # YanG-1989/m3u - 聚合源，收集多个来源
    "https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",

    # YueChan/Live - 另一个常用源
    "https://raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u",

    # drangjchen/IPTV
    "https://raw.githubusercontent.com/drangjchen/IPTV/main/M3U/ipv6.m3u",

    # vbskycn/iptv - 补充源，带台标和EPG
    # 使用 GitHub 镜像加速地址，避免国内 CDN 在海外无法访问
    "https://gh-proxy.com/raw.githubusercontent.com/vbskycn/iptv/refs/heads/master/tv/iptv4.m3u",
]

# 输出文件
OUTPUT_FILE = "my_channels.m3u"

# 需要的频道分类（按此顺序排列）
# 脚本会自动匹配不同源中近似的分类名
WANTED_CATEGORIES = [
    "央视频道",
    "卫视频道",
    "地方频道",
    "港澳台频道",
    "少儿频道",
    "体育频道",
    "电影频道",
    "音乐频道",
    "纪录频道",
    "付费频道",
]

# 分类名映射：不同源对同一分类可能有不同叫法
# 注意：匹配顺序影响结果，更具体的分类应放在前面
# 使用精确匹配避免误分类
CATEGORY_ALIASES = {
    "央视频道": [
        "央视频道", "央视", "cctv", "中央频道", "央视高清", "央视标清",
        "cctv", "CGTN", "央视4K",
    ],
    "卫视频道": [
        "卫视频道", "卫视", "卫星频道", "卫视高清", "卫视标清",
        "卫视台", "省级卫视",
    ],
    "地方频道": [
        "地方频道", "地方台", "地方",
        "各省卫视", "省台", "地市台", "市县台",
    ],
    "港澳台频道": [
        "港澳台频道", "港澳台", "香港", "澳门", "台湾", "港台", "海外",
        "香港台", "澳门台", "台湾台",
    ],
    "少儿频道": [
        "少儿频道", "少儿", "儿童", "卡通", "动漫", "动画",
        "少儿台", "动漫秀场", "卡通台",
    ],
    "体育频道": [
        "体育频道", "体育", "赛事", "体育台",
        "体育赛事", "竞技",
    ],
    "电影频道": [
        "电影频道", "电影", "影视", "影视台",
        "CHC", "动作电影", "家庭影院",
    ],
    "音乐频道": [
        "音乐频道", "音乐", "音乐台",
    ],
    "纪录频道": [
        "纪录频道", "纪录", "纪录片", "纪实", "科教",
        "纪实台", "科教台",
    ],
    "付费频道": [
        "付费频道", "付费", "数字付费", "收费频道", "VIP频道",
        "数字频道", "付费台",
    ],
}

# 频道名归一化映射：不同源对同一频道可能有不同叫法
# 统一为标准化名称，方便跨源合并
CHANNEL_NAME_ALIASES = {
    # CCTV-1
    "CCTV-1": "CCTV1",
    "CCTV-1 综合": "CCTV1",
    "CCTV1 综合": "CCTV1",
    "CCTV-1综合": "CCTV1",
    "CCTV-1高清": "CCTV1",
    "CCTV1高清": "CCTV1",
    # CCTV-2
    "CCTV-2": "CCTV2",
    "CCTV-2 财经": "CCTV2",
    "CCTV2 财经": "CCTV2",
    "CCTV-2财经": "CCTV2",
    "CCTV-2高清": "CCTV2",
    "CCTV2高清": "CCTV2",
    # CCTV-3
    "CCTV-3": "CCTV3",
    "CCTV-3 综艺": "CCTV3",
    "CCTV3 综艺": "CCTV3",
    "CCTV-3综艺": "CCTV3",
    "CCTV-3高清": "CCTV3",
    "CCTV3高清": "CCTV3",
    # CCTV-4
    "CCTV-4": "CCTV4",
    "CCTV-4 中文国际": "CCTV4",
    "CCTV4 中文国际": "CCTV4",
    "CCTV-4中文国际": "CCTV4",
    "CCTV-4高清": "CCTV4",
    "CCTV4高清": "CCTV4",
    # CCTV-5
    "CCTV-5": "CCTV5",
    "CCTV-5 体育": "CCTV5",
    "CCTV5 体育": "CCTV5",
    "CCTV-5体育": "CCTV5",
    "CCTV-5高清": "CCTV5",
    "CCTV5高清": "CCTV5",
    # CCTV-5+
    "CCTV-5+": "CCTV5+",
    "CCTV-5+ 体育赛事": "CCTV5+",
    "CCTV5+ 体育赛事": "CCTV5+",
    "CCTV-5+体育赛事": "CCTV5+",
    "CCTV-5+高清": "CCTV5+",
    "CCTV5+高清": "CCTV5+",
    # CCTV-6
    "CCTV-6": "CCTV6",
    "CCTV-6 电影": "CCTV6",
    "CCTV6 电影": "CCTV6",
    "CCTV-6电影": "CCTV6",
    "CCTV-6高清": "CCTV6",
    "CCTV6高清": "CCTV6",
    # CCTV-7
    "CCTV-7": "CCTV7",
    "CCTV-7 国防军事": "CCTV7",
    "CCTV7 国防军事": "CCTV7",
    "CCTV-7国防军事": "CCTV7",
    "CCTV-7高清": "CCTV7",
    "CCTV7高清": "CCTV7",
    # CCTV-8
    "CCTV-8": "CCTV8",
    "CCTV-8 电视剧": "CCTV8",
    "CCTV8 电视剧": "CCTV8",
    "CCTV-8电视剧": "CCTV8",
    "CCTV-8高清": "CCTV8",
    "CCTV8高清": "CCTV8",
    # CCTV-9
    "CCTV-9": "CCTV9",
    "CCTV-9 纪录": "CCTV9",
    "CCTV9 纪录": "CCTV9",
    "CCTV-9纪录": "CCTV9",
    "CCTV-9高清": "CCTV9",
    "CCTV9高清": "CCTV9",
    # CCTV-10
    "CCTV-10": "CCTV10",
    "CCTV-10 科教": "CCTV10",
    "CCTV10 科教": "CCTV10",
    "CCTV-10科教": "CCTV10",
    "CCTV-10高清": "CCTV10",
    "CCTV10高清": "CCTV10",
    # CCTV-11
    "CCTV-11": "CCTV11",
    "CCTV-11 戏曲": "CCTV11",
    "CCTV-11戏曲": "CCTV11",
    "CCTV-11高清": "CCTV11",
    "CCTV11高清": "CCTV11",
    # CCTV-12
    "CCTV-12": "CCTV12",
    "CCTV-12 社会与法": "CCTV12",
    "CCTV-12社会与法": "CCTV12",
    "CCTV12 社会与法": "CCTV12",
    "CCTV12社会与法": "CCTV12",
    "CCTV-12高清": "CCTV12",
    "CCTV12高清": "CCTV12",
    # CCTV-13
    "CCTV-13": "CCTV13",
    "CCTV-13 新闻": "CCTV13",
    "CCTV13 新闻": "CCTV13",
    "CCTV-13新闻": "CCTV13",
    "CCTV-13高清": "CCTV13",
    "CCTV13高清": "CCTV13",
    # CCTV-14
    "CCTV-14": "CCTV14",
    "CCTV-14 少儿": "CCTV14",
    "CCTV14 少儿": "CCTV14",
    "CCTV-14少儿": "CCTV14",
    "CCTV-14高清": "CCTV14",
    "CCTV14高清": "CCTV14",
    # CCTV-15
    "CCTV-15": "CCTV15",
    "CCTV-15 音乐": "CCTV15",
    "CCTV15 音乐": "CCTV15",
    "CCTV-15音乐": "CCTV15",
    "CCTV-15高清": "CCTV15",
    "CCTV15高清": "CCTV15",
    # CCTV-16
    "CCTV-16": "CCTV16",
    "CCTV-16 奥林匹克": "CCTV16",
    "CCTV-16奥林匹克": "CCTV16",
    "CCTV16 奥林匹克": "CCTV16",
    "CCTV-16高清": "CCTV16",
    "CCTV16高清": "CCTV16",
    # CCTV-17
    "CCTV-17": "CCTV17",
    "CCTV-17 农业农村": "CCTV17",
    "CCTV17 农业农村": "CCTV17",
    "CCTV-17农业农村": "CCTV17",
    "CCTV-17高清": "CCTV17",
    "CCTV17高清": "CCTV17",
}

# 需要排除的频道关键词
EXCLUDE_KEYWORDS = [
    "求赏", "捐赠", "赞助", "测试", "广告", "推广",
    "打赏", "VIP", "试看", "福利", "收费", "内部",
    "体验", "仅供", "演示", "4KHDR", "8K", "杜比",
    # 游戏直播频道（非体育）
    "B站", "斗鱼", "虎牙", "哔哩哔哩",
]

# 需要排除的频道名称（精确匹配）
EXCLUDE_NAMES = [
    "支持作者",
]

# ============================================================
# 核心逻辑
# ============================================================

FETCH_TIMEOUT = 15  # 每个源的超时时间（秒）
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def natural_sort_key(name: str) -> list:
    """
    生成自然排序键，使 "CCTV1" 排在 "CCTV10" 之前
    例如: CCTV1, CCTV2, CCTV3, ..., CCTV10, CCTV11, ...
    """
    parts = re.split(r'(\d+)', name)
    result = []
    for part in parts:
        if part.isdigit():
            result.append((0, int(part)))  # 数字按数值排序
        else:
            result.append((1, part.lower()))  # 文本按字母排序
    return result


def normalize_name(name: str) -> str:
    """归一化频道名，去掉多余空格和特殊字符"""
    n = name.strip()
    # 应用别名映射
    if n in CHANNEL_NAME_ALIASES:
        return CHANNEL_NAME_ALIASES[n]
    # 去掉开头结尾的标点符号
    n = re.sub(r'^[-—\s]+|[-—\s]+$', '', n)
    return n


def match_category(group_title: str) -> str | None:
    """将源的分类名映射到标准分类名"""
    gt = group_title.strip().lower()
    for std_cat, aliases in CATEGORY_ALIASES.items():
        for alias in aliases:
            if alias.lower() in gt or gt in alias.lower():
                return std_cat
    return None


def fetch_source(url: str) -> str | None:
    """从上游获取M3U/TXT内容，失败返回None"""
    import ssl

    print(f"  正在获取: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        # 创建不验证SSL证书的上下文，避免某些源的证书问题
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT, context=ctx) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            print(f"  ✓ 成功 ({len(content)} 字节)")
            return content
    except Exception as e:
        print(f"  ✗ 失败: {e}")
        return None


def parse_m3u(content: str) -> tuple:
    """解析M3U内容，返回 (epg_url, channels_list)"""
    lines = content.splitlines()
    epg_url = ""
    channels = []
    i = 0

    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i < len(lines) and lines[i].strip().startswith("#EXTM3U"):
        first = lines[i].strip()
        m = re.search(r'x-tvg-url="([^"]*)"', first)
        if m:
            epg_url = m.group(1)
        i += 1

    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF:"):
            tvg_id = ""
            tvg_name = ""
            tvg_logo = ""
            group_title = ""

            m = re.search(r'tvg-id="([^"]*)"', line)
            if m: tvg_id = m.group(1)
            m = re.search(r'tvg-name="([^"]*)"', line)
            if m: tvg_name = m.group(1)
            m = re.search(r'tvg-logo="([^"]*)"', line)
            if m: tvg_logo = m.group(1)
            m = re.search(r'group-title="([^"]*)"', line)
            if m: group_title = m.group(1)

            name = line.split(",")[-1].strip() if "," in line else ""
            if not name: name = tvg_name

            if i + 1 < len(lines):
                url = lines[i + 1].strip()
                if url and not url.startswith("#"):
                    channels.append({
                        "name": name,
                        "url": url,
                        "category": group_title,
                        "logo": tvg_logo,
                        "tvg_id": tvg_id,
                        "tvg_name": tvg_name,
                    })
            i += 2
        else:
            i += 1

    return epg_url, channels


def parse_txt(content: str) -> list:
    """解析TXT格式（iptv-api兼容格式）"""
    channels = []
    current_category = "未分类"
    for line in content.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        if trimmed.endswith("#genre#"):
            current_category = trimmed.split(",")[0].strip()
            continue
        parts = trimmed.split(",", 1)
        if len(parts) == 2:
            name, url = parts[0].strip(), parts[1].strip()
            if name and url and not url.startswith("#"):
                channels.append({
                    "name": name, "url": url,
                    "category": current_category,
                    "logo": "", "tvg_id": "", "tvg_name": "",
                })
    return channels


def should_exclude(name: str) -> bool:
    """检查频道是否应该被排除"""
    for keyword in EXCLUDE_KEYWORDS:
        if keyword in name:
            return True
    for exact in EXCLUDE_NAMES:
        if name == exact:
            return True
    return False


def collect_all_channels() -> list:
    """从所有源收集频道，合并到一个列表中"""
    all_channels = []
    source_epg_urls = []

    for url in SOURCE_URLS:
        content = fetch_source(url)
        if content is None:
            continue

        lower = url.lower()
        if content.strip().startswith("#EXTM3U"):
            epg_url, channels = parse_m3u(content)
            if epg_url:
                source_epg_urls.append(epg_url)
        elif lower.endswith(".txt"):
            channels = parse_txt(content)
        else:
            # 自动检测格式
            if content.strip().startswith("#EXTM3U"):
                _, channels = parse_m3u(content)
            else:
                channels = parse_txt(content)

        print(f"  解析到 {len(channels)} 个频道")
        all_channels.extend(channels)

    # 使用第一个找到的EPG地址
    primary_epg = source_epg_urls[0] if source_epg_urls else ""
    return all_channels, primary_epg


def classify_and_merge(channels: list) -> dict:
    """
    将频道按分类归类，跨源合并同名频道
    返回 {category: [{name, urls, logo, tvg_id, tvg_name}]}
    """
    # 第一步：按分类分组
    categorized = {cat: {} for cat in WANTED_CATEGORIES}  # {cat: {normalized_name: entry}}

    for ch in channels:
        std_cat = match_category(ch["category"])
        if std_cat is None:
            continue
        if should_exclude(ch["name"]):
            continue

        norm_name = normalize_name(ch["name"])
        if not norm_name:
            continue

        entry = categorized[std_cat]
        if norm_name not in entry:
            entry[norm_name] = {
                "name": norm_name,
                "display_name": ch["name"],  # 保留原始显示名
                "urls": [],
                "logo": ch["logo"],
                "tvg_id": ch["tvg_id"],
                "tvg_name": ch["tvg_name"],
            }
        # 添加URL
        if ch["url"] not in entry[norm_name]["urls"]:
            entry[norm_name]["urls"].append(ch["url"])
        # 补充元数据（优先使用前面的源）
        if not entry[norm_name]["logo"] and ch["logo"]:
            entry[norm_name]["logo"] = ch["logo"]
        if not entry[norm_name]["tvg_id"] and ch["tvg_id"]:
            entry[norm_name]["tvg_id"] = ch["tvg_id"]
        if not entry[norm_name]["tvg_name"] and ch["tvg_name"]:
            entry[norm_name]["tvg_name"] = ch["tvg_name"]

    # 转换为列表格式
    result = {}
    for cat in WANTED_CATEGORIES:
        entry = categorized[cat]
        items = list(entry.values())
        items.sort(key=lambda x: natural_sort_key(x["name"]))
        result[cat] = items

    return result


def generate_m3u(categorized: dict, epg_url: str) -> str:
    """生成M3U内容"""
    lines = []
    if epg_url:
        lines.append(f'#EXTM3U x-tvg-url="{epg_url}"')
    else:
        lines.append("#EXTM3U")
    lines.append("")

    for cat in WANTED_CATEGORIES:
        items = categorized.get(cat, [])
        if not items:
            continue

        total_urls = sum(len(it["urls"]) for it in items)
        lines.append(f"# 分类: {cat} - {len(items)} 个频道, {total_urls} 个播放源")
        lines.append("")

        for it in items:
            primary = it["urls"][0]
            display = it["display_name"]

            attrs = ""
            if it["tvg_id"]:
                attrs += f' tvg-id="{it["tvg_id"]}"'
            if it["tvg_name"]:
                attrs += f' tvg-name="{it["tvg_name"]}"'
            if it["logo"]:
                attrs += f' tvg-logo="{it["logo"]}"'
            attrs += f' group-title="{cat}"'

            lines.append(f'#EXTINF:-1{attrs},{display}')
            lines.append(primary)

            # 额外URL作为注释备用源
            if len(it["urls"]) > 1:
                for extra in it["urls"][1:]:
                    lines.append(f"# 备用源: {extra}")

        lines.append("")

    return "\n".join(lines)


def generate_txt(categorized: dict, output_path: str):
    """生成TXT格式"""
    lines = []
    for cat in WANTED_CATEGORIES:
        items = categorized.get(cat, [])
        if not items:
            continue
        lines.append(f"{cat},#genre#")
        for it in items:
            lines.append(f"{it['display_name']},{it['urls'][0]}")
        lines.append("")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    print("=" * 55)
    print(f"  橙子网络电视 - 自定义IPTV播放列表生成器")
    print(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  数据源数量: {len(SOURCE_URLS)}")
    print("=" * 55)

    # 第一步：从所有源收集频道
    print("\n📡 正在获取数据源...")
    all_channels, epg_url = collect_all_channels()
    print(f"\n共收集到 {len(all_channels)} 条频道记录")

    # 第二步：分类筛选和合并
    print("\n🔍 正在分类筛选和合并...")
    categorized = classify_and_merge(all_channels)

    # 打印统计
    total_channels = 0
    total_urls = 0
    for cat in WANTED_CATEGORIES:
        items = categorized.get(cat, [])
        urls_count = sum(len(it["urls"]) for it in items)
        total_channels += len(items)
        total_urls += urls_count
        if items:
            samples = ", ".join(it["display_name"] for it in items[:4])
            print(f"  {cat}: {len(items)} 个频道 ({urls_count} 个播放源) - {samples}...")
        else:
            print(f"  {cat}: 0 个频道")

    print(f"\n合计: {total_channels} 个频道, {total_urls} 个播放源")

    # 第三步：生成M3U
    m3u = generate_m3u(categorized, epg_url)
    output_dir = os.path.dirname(os.path.abspath(__file__))
    m3u_path = os.path.join(output_dir, OUTPUT_FILE)
    with open(m3u_path, "w", encoding="utf-8") as f:
        f.write(m3u)
    print(f"\n✅ 已生成: {m3u_path}")
    print(f"   文件大小: {os.path.getsize(m3u_path) / 1024:.1f} KB")

    # 第四步：生成TXT
    txt_path = m3u_path.replace(".m3u", ".txt")
    generate_txt(categorized, txt_path)
    print(f"✅ 已生成TXT: {txt_path}")
    print(f"   文件大小: {os.path.getsize(txt_path) / 1024:.1f} KB")


if __name__ == "__main__":
    main()