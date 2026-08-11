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

# 多个上游数据源（按优先级排列，前面的源优先使用其台标和EPG信息，URL也优先使用前面的）
# 每个源可以是 M3U 或 TXT 格式
# 注意：GitHub Actions 运行在海外服务器，raw.githubusercontent.com 的链接更稳定
# vbskycn 放在首位，因为其URL通常更可靠、多源更丰富
SOURCE_URLS = [
    # vbskycn/iptv - 主源，带台标和EPG，多源丰富
    # 使用 GitHub 镜像加速地址，避免国内 CDN 在海外无法访问
    "https://gh-proxy.com/raw.githubusercontent.com/vbskycn/iptv/refs/heads/master/tv/iptv4.m3u",

    # fanmingming/live - 补充源，频道齐全，台标完善
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u",

    # YanG-1989/m3u - 聚合源，收集多个来源
    "https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",

    # YueChan/Live - 另一个常用源
    "https://raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u",

    # drangjchen/IPTV
    "https://raw.githubusercontent.com/drangjchen/IPTV/main/M3U/ipv6.m3u",
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
        "cctv", "CGTN", "央视4K", "央视8K", "CCTV",
    ],
    "卫视频道": [
        "卫视频道", "卫视", "卫星频道", "卫视高清", "卫视标清",
        "卫视台", "省级卫视", "卫视高清台",
    ],
    "地方频道": [
        "地方频道", "地方台", "地方",
        "各省卫视", "省台", "地市台", "市县台",
        "地市频道", "本地", "城市频道",
    ],
    "港澳台频道": [
        "港澳台频道", "港澳台", "香港", "澳门", "台湾", "港台", "海外",
        "香港台", "澳门台", "台湾台", "凤凰", "华语影院",
        "香港频道", "澳门频道", "台湾频道",
    ],
    "少儿频道": [
        "少儿频道", "少儿", "儿童", "卡通", "动漫", "动画",
        "少儿台", "动漫秀场", "卡通台", "亲子", "育儿",
    ],
    "体育频道": [
        "体育频道", "体育", "赛事", "体育台",
        "体育赛事", "竞技", "体育竞技",
    ],
    "电影频道": [
        "电影频道", "电影", "影视", "影视台",
        "CHC", "动作电影", "家庭影院", "电影台",
        "影院", "影视剧",
    ],
    "音乐频道": [
        "音乐频道", "音乐", "音乐台",
    ],
    "纪录频道": [
        "纪录频道", "纪录", "纪录片", "纪实", "科教",
        "纪实台", "科教台", "探索", "纪录电影",
    ],
    "付费频道": [
        "付费频道", "付费", "数字付费", "收费频道", "VIP频道",
        "数字频道", "付费台", "付费电视",
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
    # 轮播解说频道（非正式电视节目）
    "解说", "轮播",
]

# 需要排除的频道名称（精确匹配）
EXCLUDE_NAMES = [
    "支持作者",
]

# 需要在特定分类中排除的频道关键词
# {分类名: [关键词列表]}
CATEGORY_EXCLUDE_KEYWORDS = {
    "纪录频道": [
        "新闻", "综合", "一套", "二套", "经济", "法制",
        "汉语", "维吾尔", "哈萨克",
        "兵团", "白山", "玛纳斯", "磐石", "靖宇",
        "东丰", "九台", "龙井", "双辽", "柳河", "桦甸", "汪清", "通化县",
    ],
    "电影频道": [
        "电视剧", "美剧", "动漫", "恐怖", "漫威",
    ],
    "央视频道": [
        # 保留兵器科技，它是CCTV旗下付费频道
    ],
}

# 省级卫视白名单（只有这些才能进入"卫视频道"分类）
# 深圳卫视虽然不是省级，但用户明确要求保留在卫视频道
PROVINCIAL_SATELLITE_TV = [
    "北京卫视", "天津卫视", "河北卫视", "山西卫视", "内蒙古卫视",
    "辽宁卫视", "吉林卫视", "黑龙江卫视", "东方卫视", "上海卫视",
    "江苏卫视", "浙江卫视", "安徽卫视", "东南卫视", "福建卫视",
    "江西卫视", "山东卫视", "河南卫视", "湖北卫视", "湖南卫视",
    "广东卫视", "广西卫视", "海南卫视", "重庆卫视",
    "四川卫视", "贵州卫视", "云南卫视", "西藏卫视",
    "陕西卫视", "甘肃卫视", "青海卫视", "宁夏卫视", "新疆卫视",
    "深圳卫视",  # 非省级但保留
    "三沙卫视",  # 地级市卫视，但考虑到特殊性，保留在卫视
    "厦门卫视",  # 地级市卫视，但考虑到特殊性，保留在卫视
]

# 需要移到地方频道的卫视（非省级卫视）
# 小城市/非省级卫视，移去地方频道
NON_PROVINCIAL_SATELLITE_TV = [
    "人间卫视", "农林卫视", "延边卫视",
    "大湾区卫视", "南方卫视", "大湾区卫视",
    "长城卫视", "黄河卫视", "泰山卫视",
    "海峡卫视", "旅游卫视", "海南卫视",
]

# 汉字拼音映射表（用于中文频道名称排序）
# 覆盖常用汉字，确保频道按拼音顺序排列
PINYIN_MAP = {
    # 数字
    '一': 'yi', '二': 'er', '三': 'san', '四': 'si', '五': 'wu',
    '六': 'liu', '七': 'qi', '八': 'ba', '九': 'jiu', '十': 'shi',
    '〇': 'ling', '零': 'ling',
    # 省份/直辖市简称（按拼音首字母排序）
    '安': 'an', '徽': 'hui',
    '北': 'bei', '京': 'jing',
    '重': 'chong', '庆': 'qing',
    '福': 'fu', '建': 'jian',
    '甘': 'gan', '肃': 'su',
    '广': 'guang', '东': 'dong', '西': 'xi',
    '贵': 'gui', '州': 'zhou',
    '海': 'hai', '南': 'nan',
    '河': 'he', '北': 'bei', '南': 'nan',
    '黑': 'hei', '龙': 'long', '江': 'jiang',
    '湖': 'hu', '北': 'bei', '南': 'nan',
    '吉': 'ji', '林': 'lin',
    '江': 'jiang', '苏': 'su', '西': 'xi',
    '辽': 'liao', '宁': 'ning',
    '内': 'nei', '蒙': 'meng', '古': 'gu',
    '宁': 'ning', '夏': 'xia',
    '青': 'qing',
    '山': 'shan', '东': 'dong', '西': 'xi',
    '陕': 'shan', '西': 'xi',
    '上': 'shang', '海': 'hai',
    '四': 'si', '川': 'chuan',
    '台': 'tai', '湾': 'wan',
    '天': 'tian', '津': 'jin',
    '西': 'xi', '藏': 'zang',
    '香': 'xiang', '港': 'gang',
    '新': 'xin', '疆': 'jiang',
    '澳': 'ao', '门': 'men',
    '云': 'yun', '南': 'nan',
    '浙': 'zhe', '江': 'jiang',
    # 城市名
    '深': 'shen', '圳': 'zhen',
    '厦': 'xia', '门': 'men',
    '延': 'yan', '边': 'bian',
    '大': 'da', '湾': 'wan', '区': 'qu',
    '三': 'san', '沙': 'sha',
    # 频道相关常用字
    '央': 'yang', '视': 'shi',
    '卫': 'wei', '星': 'xing',
    '频': 'pin', '道': 'dao',
    '综': 'zong', '合': 'he',
    '新': 'xin', '闻': 'wen',
    '财': 'cai', '经': 'jing',
    '体': 'ti', '育': 'yu',
    '电': 'dian', '影': 'ying',
    '剧': 'ju', '院': 'yuan',
    '少': 'shao', '儿': 'er',
    '科': 'ke', '教': 'jiao',
    '纪': 'ji', '录': 'lu', '实': 'shi',
    '音': 'yin', '乐': 'le', '悦': 'yue',
    '高': 'gao', '清': 'qing',
    '标': 'biao', '准': 'zhun',
    '时': 'shi', '尚': 'shang',
    '国': 'guo', '际': 'ji',
    '法': 'fa', '制': 'zhi',
    '农': 'nong', '业': 'ye', '村': 'cun',
    '军': 'jun', '事': 'shi',
    '戏': 'xi', '曲': 'qu',
    '奥': 'ao', '林': 'lin', '匹': 'pi', '克': 'ke',
    '数': 'shu', '字': 'zi',
    '付': 'fu', '费': 'fei',
    '收': 'shou', '费': 'fei',
    '动': 'dong', '漫': 'man',
    '卡': 'ka', '通': 'tong',
    '记': 'ji', '录': 'lu',
    '真': 'zhen', '人': 'ren',
    '家': 'jia', '庭': 'ting',
    '作': 'zuo', '战': 'zhan',
    '动': 'dong', '作': 'zuo',
    '公': 'gong', '共': 'gong',
    '生': 'sheng', '活': 'huo',
    '世': 'shi', '界': 'jie',
    '都': 'du', '市': 'shi',
    '旅': 'lv', '游': 'you',
    '老': 'lao',
    '故': 'gu', '宫': 'gong',
    '文': 'wen', '化': 'hua',
    '探': 'tan', '索': 'suo',
    '发': 'fa', '现': 'xian',
    '大': 'da',
    '风': 'feng', '云': 'yun',
    '资': 'zi', '讯': 'xun',
    '气': 'qi', '象': 'xiang',
    '天': 'tian', '气': 'qi',
    '穿': 'chuan', '越': 'yue',
    '百': 'bai', '科': 'ke',
    '全': 'quan', '球': 'qiu',
    '棋': 'qi', '牌': 'pai',
    '竞': 'jing', '技': 'ji',
    '搏': 'bo', '击': 'ji',
    '武': 'wu', '术': 'shu',
    '篮': 'lan', '球': 'qiu',
    '足': 'zu', '球': 'qiu',
    '乒': 'ping', '乓': 'pang',
    '羽': 'yu', '毛': 'mao',
    '网': 'wang', '球': 'qiu',
    '高': 'gao', '尔': 'er', '夫': 'fu',
    '台': 'tai', '球': 'qiu',
    '斯': 'si', '诺': 'nuo',
    '排': 'pai', '球': 'qiu',
    '田': 'tian', '径': 'jing',
    '游': 'you', '泳': 'yong',
    '滑': 'hua', '雪': 'xue', '冰': 'bing',
    '极': 'ji', '限': 'xian',
    '自': 'zi', '由': 'you',
    '直': 'zhi', '播': 'bo',
    '回': 'hui', '放': 'fang',
    '精': 'jing', '选': 'xuan',
    '导': 'dao',
    '优': 'you', '酷': 'ku',
    '爱': 'ai', '奇': 'qi', '艺': 'yi',
    '腾': 'teng', '讯': 'xun',
    '芒': 'mang', '果': 'guo',
    '咪': 'mi', '咕': 'gu',
    '娱': 'yu', '乐': 'le',
    '金': 'jin', '鹰': 'ying',
    '凤': 'feng', '凰': 'huang',
    '华': 'hua', '夏': 'xia',
    '长': 'chang', '城': 'cheng',
    '兵': 'bing', '团': 'tuan',
    '经': 'jing', '典': 'dian',
    '怀': 'huai', '旧': 'jiu',
    '亲': 'qin', '子': 'zi',
    '成': 'cheng', '语': 'yu',
    '书': 'shu', '画': 'hua',
    '钓': 'diao', '鱼': 'yu',
    '美': 'mei', '食': 'shi',
    '环': 'huan', '球': 'qiu',
    '现': 'xian', '场': 'chang',
    '第': 'di', '一': 'yi',
    '楚': 'chu', '天': 'tian',
    '黄': 'huang', '河': 'he',
    '泰': 'tai', '山': 'shan',
    '海': 'hai', '峡': 'xia',
    '长': 'chang', '城': 'cheng',
    '南': 'nan', '方': 'fang',
    '大': 'da', '湾': 'wan', '区': 'qu',
    '人': 'ren', '间': 'jian',
    'CHC': 'chc',
    'CGTN': 'cgtn',
    'CCTV': 'cctv',
    'CETV': 'cetv',
    'CNR': 'cnr',
    'CNTV': 'cntv',
}

# ============================================================
# 核心逻辑
# ============================================================

FETCH_TIMEOUT = 15  # 每个源的超时时间（秒）
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def chinese_to_pinyin(text: str) -> str:
    """将汉字转换为拼音（用于排序），非汉字字符保持不变"""
    result = []
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff':  # 中文字符范围
            pinyin = PINYIN_MAP.get(ch)
            if pinyin:
                result.append(pinyin)
            else:
                # 未在映射表中的汉字，用Unicode编码作为排序依据
                result.append(f'zzz{ord(ch):05d}')
        else:
            result.append(ch.lower())
    return ''.join(result)


def natural_sort_key(name: str) -> list:
    """
    生成自然排序键，使 "CCTV1" 排在 "CCTV10" 之前
    支持中文拼音排序，例如: 安徽卫视, 北京卫视, 重庆卫视, 东方卫视...
    例如: CCTV1, CCTV2, CCTV3, ..., CCTV10, CCTV11, ...
    """
    # 先对中文部分进行拼音转换
    pinyin_text = chinese_to_pinyin(name)
    parts = re.split(r'(\d+)', pinyin_text)
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

        # 分类特定排除
        cat_excludes = CATEGORY_EXCLUDE_KEYWORDS.get(std_cat, [])
        if cat_excludes:
            should_skip = False
            for kw in cat_excludes:
                if kw in norm_name or kw in ch["name"]:
                    should_skip = True
                    break
            if should_skip:
                # 尝试放入地方频道
                if "地方频道" in categorized and std_cat != "地方频道":
                    local_entry = categorized["地方频道"]
                    if norm_name not in local_entry:
                        local_entry[norm_name] = {
                            "name": norm_name,
                            "display_name": ch["name"],
                            "urls": [],
                            "logo": ch["logo"],
                            "tvg_id": ch["tvg_id"],
                            "tvg_name": ch["tvg_name"],
                        }
                    if ch["url"] not in local_entry[norm_name]["urls"]:
                        local_entry[norm_name]["urls"].append(ch["url"])
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

    # 第二步：筛选卫视频道，非省级卫视移到地方频道
    if "卫视频道" in categorized and "地方频道" in categorized:
        satellite_entries = categorized["卫视频道"]
        local_entries = categorized["地方频道"]
        # 收集需要移走的频道名
        to_move = []
        for norm_name, entry in satellite_entries.items():
            # 检查是否在省级白名单中
            is_provincial = False
            for prov_name in PROVINCIAL_SATELLITE_TV:
                if norm_name == prov_name or prov_name in norm_name or norm_name in prov_name:
                    is_provincial = True
                    break
            if not is_provincial:
                # 所有不在省级卫视白名单中的频道都移到地方频道
                # 包括：上游源错分类的本地频道（如"北京财经"被放在"北京卫视"分组下）
                to_move.append(norm_name)
        # 执行移动
        for norm_name in to_move:
            entry = satellite_entries.pop(norm_name)
            if norm_name not in local_entries:
                local_entries[norm_name] = entry
            else:
                # 合并到已有的地方频道条目
                existing = local_entries[norm_name]
                for url in entry["urls"]:
                    if url not in existing["urls"]:
                        existing["urls"].append(url)
                if not existing["logo"] and entry["logo"]:
                    existing["logo"] = entry["logo"]
                if not existing["tvg_id"] and entry["tvg_id"]:
                    existing["tvg_id"] = entry["tvg_id"]
                if not existing["tvg_name"] and entry["tvg_name"]:
                    existing["tvg_name"] = entry["tvg_name"]
        if to_move:
            print(f"  将 {len(to_move)} 个非省级卫视移至地方频道: {', '.join(to_move[:5])}...")

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
            display = it["display_name"]

            attrs = ""
            if it["tvg_id"]:
                attrs += f' tvg-id="{it["tvg_id"]}"'
            if it["tvg_name"]:
                attrs += f' tvg-name="{it["tvg_name"]}"'
            if it["logo"]:
                attrs += f' tvg-logo="{it["logo"]}"'
            attrs += f' group-title="{cat}"'

            # 所有URL都作为正式播放源输出，而不是注释
            for url in it["urls"]:
                lines.append(f'#EXTINF:-1{attrs},{display}')
                lines.append(url)

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