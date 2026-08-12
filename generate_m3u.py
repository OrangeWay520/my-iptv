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

    # vbskycn/iptv (镜像) - 备用CDN，同上数据
    "https://live.zbds.top/tv/iptv4.m3u",

    # vbskycn/iptv (TXT源) - 补充多源地址（如CCTV1有5个IPv4源），与m3u配合实现多源
    "https://live.zbds.top/tv/iptv4.txt",

    # iptv-org/iptv (中国频道) - 补充CCTV/卫视直链源，频道名带清晰度后缀
    "https://iptv-org.github.io/iptv/countries/cn.m3u",

    # AudiHub/iptv (migu) - 咪咕稳定源，补充央视和卫视
    "https://gh-proxy.org/https://raw.githubusercontent.com/AudiHub/iptv/main/m3u/migu.m3u",

    # iptv-org/iptv (港澳台) - 补充香港/澳门/台湾知名频道
    "https://iptv-org.github.io/iptv/countries/hk.m3u",
    "https://iptv-org.github.io/iptv/countries/mo.m3u",
    "https://iptv-org.github.io/iptv/countries/tw.m3u",

    # sammy0101/hk-iptv-auto - 香港本地源，含翡翠台/明珠台/TVB系列（TVB版权严格，仅此源收录）
    "https://raw.githubusercontent.com/sammy0101/hk-iptv-auto/refs/heads/main/hk_live.m3u",
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
        # iptv-org 英文分类
        "kids",
    ],
    "体育频道": [
        "体育频道", "体育", "赛事", "体育台",
        "体育赛事", "竞技", "体育竞技",
        # iptv-org 英文分类
        "sports",
    ],
    "电影频道": [
        "电影频道", "电影", "影视", "影视台",
        "CHC", "动作电影", "家庭影院", "电影台",
        "影院", "影视剧",
        # iptv-org 英文分类
        "movies", "cinema",
    ],
    "音乐频道": [
        "音乐频道", "音乐", "音乐台",
        # iptv-org 英文分类
        "music",
    ],
    "纪录频道": [
        "纪录频道", "纪录", "纪录片", "纪实", "科教",
        "纪实台", "科教台", "探索", "纪录电影",
        # iptv-org 英文分类
        "documentary",
    ],
    "付费频道": [
        "付费频道", "付费", "数字付费", "收费频道", "VIP频道",
        "数字频道", "付费台", "付费电视",
    ],
}

# 频道名归一化映射：不同源对同一频道可能有不同叫法
# 统一为标准化名称，方便跨源合并
# 注意：CCTV系列频道的各种后缀变体（如"CCTV1综合"、"CCTV-1 高清"等）
# 由 normalize_name() 中的正则逻辑自动处理，无需在此列出
CHANNEL_NAME_ALIASES = {
    # CGTN频道
    "CGTN": "CGTN",
    "CGTN 中文国际": "CGTN",
    "CGTN Documentary": "CGTN纪录",
    "CGTN纪录": "CGTN纪录",
    # CETV频道
    "CETV-1": "CETV1",
    "CETV1 中国教育": "CETV1",
    "CETV-1 中国教育": "CETV1",
    "CETV1中国教育": "CETV1",
    # CHC电影频道
    "CHC电影": "CHC电影",
    "CHC动作电影": "CHC动作电影",
    "CHC家庭影院": "CHC家庭影院",
    "CHC影迷电影": "CHC影迷电影",
    "CHC高清电影": "CHC电影",
    # iptv-org 英文频道名 → 中文名
    "CCTV-Storm Football": "CCTV风云足球",
    "CCTV-Storm Music": "风云音乐",
    "CCTV-Storm Theater": "风云剧场",
    "CCTV-Weapon & Technology": "兵器科技",
    "CCTV-Nostalgia Theater": "CCTV怀旧剧场",
    "CCTV-The First Theater": "CCTV第一剧场",
    "CCTV-World Geography": "CCTV世界地理",
    "CCTV-Culture of Quality": "CCTV文化精品",
    "CCTV-Billiards": "CCTV台球",
    "CCTV-Golf & Tennis": "CCTV高尔夫网球",
    "CCTV-Health": "CCTV卫生健康",
    "CCTV-Women's Fashion": "CCTV女性时尚",
    "CCTV-4K": "CCTV4K",
    "CCTV-8K": "CCTV8K",
    "BRTV 北京卫视": "北京卫视",
    "BRTV Kaku Childrens Channel": "卡酷少儿",
    # iptv-org 英文地方台名 → 中文名
    "Jiangxi Children's Channel": "江西少儿",
    "QTV-6": "青岛少儿",
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
    # 虎牙等直播平台的轮播频道（"XX「XX」"格式命名，非正式电视频道）
    "「",
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

# 频道归属强制覆盖：手动指定某些频道应归入哪个分类
# 用于修正上游源分类错误的情况
# 键为归一化后的频道名，值为目标分类
CHANNEL_CATEGORY_OVERRIDE = {
    "风云剧场": "付费频道",    # 付费频道，不是央视频道
    "兵器科技": "付费频道",    # 付费频道，不是央视频道
    "中国交通": "地方频道",    # 地方交通频道，不是央视频道
    "熊猫直播": "地方频道",    # 熊猫TV直播，不是央视频道
}

# 地方名称前缀列表（用于检测频道是否属于地方频道）
# 当少儿频道/电影频道中的频道名包含这些前缀时，也归入地方频道（双分类）
LOCAL_PLACE_NAMES = [
    # 直辖市
    "北京", "上海", "天津", "重庆",
    # 省份
    "河北", "山西", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东",
    "河南", "湖北", "湖南", "广东", "海南",
    "四川", "贵州", "云南", "陕西", "甘肃", "青海",
    "内蒙古", "广西", "西藏", "宁夏", "新疆",
    # 主要城市
    "哈尔滨", "长春", "沈阳", "大连", "石家庄", "太原",
    "济南", "青岛", "郑州", "南京", "杭州", "宁波",
    "合肥", "福州", "厦门", "南昌", "武汉", "长沙",
    "广州", "深圳", "南宁", "成都", "贵阳", "昆明",
    "西安", "兰州", "西宁", "海口", "三亚",
    "苏州", "无锡", "佛山", "东莞", "温州", "绍兴",
    "嘉兴", "泉州", "珠海", "中山", "惠州",
    # 地级市/县级市
    "东阳", "延边", "伊犁", "奎屯", "敦化",
    "长白", "长影", "大宁", "白山", "桦甸", "磐石",
    "玛纳斯", "靖宇", "双辽", "柳河", "汪清", "龙井",
    "东丰", "九台", "通化", "江津", "安多",
    # 兵团/特区
    "兵团", "三沙", "澳门", "香港",
]

# 主题分类交叉关键词（双分类）
# 地方频道/卫视频道/港澳台频道中带这些主题关键词的频道，同时归入对应主题分类
# 例如：北京卡酷少儿 → 既在地方频道，也在少儿频道
THEME_CATEGORY_KEYWORDS = {
    "少儿频道": ["少儿", "儿童", "卡通", "动漫", "动画", "亲子", "卡酷", "优漫"],
    "体育频道": ["体育", "赛事", "竞技", "运动"],
    "电影频道": ["电影", "影视", "影院", "影迷", "家庭影院", "CHC"],
    "音乐频道": ["音乐", "演唱会", "MTV"],
    "纪录频道": ["纪录", "纪实", "科教", "纪录片", "探索", "发现"],
}

# 已知频道归属（归一化后名称可能丢失主题信息，需手动指定）
# 键为归一化后的频道名，值为主题分类
# 用于：央视少儿→少儿频道、央视体育→体育频道 等
KNOWN_THEME_CHANNELS = {
    "CCTV14": "少儿频道",    # 央视少儿
    "CCTV5": "体育频道",     # 央视体育
    "CCTV5+": "体育频道",    # 央视体育赛事
    "CCTV6": "电影频道",     # 央视电影
    "CCTV9": "纪录频道",     # 央视纪录
    "CCTV10": "纪录频道",    # 央视科教
    "CCTV15": "音乐频道",    # 央视音乐
    "CGTN纪录": "纪录频道",   # CGTN纪录
}

# 港澳台知名频道（iptv-org 港澳台源，英文名 → 中文显示名）
# 只有这些知名频道才会被归入"港澳台频道"分类，避免混入宗教/小众频道
HKMOTW_KNOWN_CHANNELS = {
    # 香港
    "凤凰中文": "凤凰中文",
    "凤凰资讯": "凤凰资讯",
    "凤凰香港": "凤凰香港",
    "星空衛視": "星空衛視",
    "星空卫视": "星空衛視",
    "HOY TV": "HOY TV",
    "RTHK TV 31": "港台電視31",
    "RTHK TV 32": "港台電視32",
    "Celestial Movies": "天映频道",
    # TVB 系列（翡翠台/明珠台等，版权严格，仅 sammy0101 源收录）
    "翡翠台": "翡翠台",
    "翡翠": "翡翠台",
    "翡翠台北美版": "翡翠台北美版",
    "TVB翡翠台 1080P": "翡翠台",
    "明珠台": "明珠台",
    "無線新聞": "無線新聞",
    "無線 TVB Plus": "無線TVB Plus",
    # 澳门（澳广视 TDM 系列）
    "TDM Ou Mun Macau Ch. 91": "澳视澳门",
    "TDM Info. Macau": "澳视资讯",
    "TDM Entertainment Ch. 95": "澳视综艺",
    "TDM Sports Ch. 93": "澳视体育",
    "Ou-Mun Macau Satellite Ch. 96": "澳视卫星",
    "Canal Macau Ch. 92": "澳门有线92",
    # 台湾
    "台视": "台视",
    "CTS": "华视",
    "FTV": "民视",
    "EBC News": "东森新闻",
    "EBC Financial News": "东森财经新闻",
    "SET News": "三立新闻",
    "TVBS News": "TVBS新闻",
    "CTi Variety": "中天综合台",
}

# 港澳台补充固定源（iptv-org index.m3u 中的频道，不在 hk/mo/tw 子集里）
# 凤凰香港、星空衛視 只存在于完整 index.m3u 中，此处直接固定收录
HKMOTW_FIXED_SOURCES = [
    # 凤凰香港（iptv-org index.m3u，group=Undefined，无子集收录）
    {"name": "凤凰香港", "url": "http://223.110.245.136/PLTV/3/224/3221226975/index.m3u8"},
    # 星空衛視（iptv-org index.m3u）
    {"name": "星空衛視", "url": "http://218.202.220.2:5000/nn_live.ts?id=STARTV"},
]

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
    # 去掉清晰度/限制后缀（如 iptv-org 的 "CCTV-1 (1080p)"、"BRTV 北京卫视 (1080p)"）
    # 统一去掉括号内的内容，如 (1080p)、(720p)、[Not 24/7]、[Geo-blocked]
    n = re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', '', n).strip()
    # 先检查显式别名映射
    if n in CHANNEL_NAME_ALIASES:
        return CHANNEL_NAME_ALIASES[n]
    # 正则匹配CCTV系列频道变体：CCTV{N}{后缀}、CCTV-{N}{后缀}、CCTV {N}{后缀}
    # 自动剥离后缀（综合、高清、财经等），统一为标准名称
    # 使用 (?![A-Za-z]) 负向断言，避免 "CCTV-4K" 被误解析为 "CCTV4"
    m = re.match(r'^(CCTV)[-\s]*(\d+)(?![A-Za-z])\+?[-\s]*(.*?)$', n, re.IGNORECASE)
    if m:
        prefix = m.group(1).upper()
        num = m.group(2)
        result = f"{prefix}{num}"
        if '+' in n:
            result += '+'
        return result
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


def infer_category_from_name(name: str) -> str | None:
    """根据频道名推断分类（用于 iptv-org 等英文分类源）"""
    norm = normalize_name(name)
    lower = norm.lower()
    if lower.startswith('cctv') or 'cgtn' in lower or lower.startswith('cetv'):
        return "央视频道"
    if '卫视' in norm:
        return "卫视频道"
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


def clean_url(url: str) -> str:
    """清洗播放地址：
    - 部分源（如 sammy0101/hk-iptv-auto）在URL后用 $ 附加线路标签，
      如 "http://.../live.m3u8$LR—IPV4【线路4】"，实际播放地址是 $ 之前的部分
    """
    u = url.strip()
    if '$' in u:
        # 只保留 $ 之前的实际播放地址
        u = u.split('$')[0].strip()
    return u


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
                url = clean_url(lines[i + 1].strip())
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
            name, url = parts[0].strip(), clean_url(parts[1].strip())
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

    # 注入港澳台补充固定源（凤凰香港、星空衛視）
    for fixed in HKMOTW_FIXED_SOURCES:
        all_channels.append({
            "name": fixed["name"],
            "url": fixed["url"],
            "category": "港澳台频道",
            "logo": "",
            "tvg_id": "",
            "tvg_name": "",
        })
    print(f"  注入 {len(HKMOTW_FIXED_SOURCES)} 个港澳台固定源")

    # 使用第一个找到的EPG地址
    primary_epg = source_epg_urls[0] if source_epg_urls else ""
    return all_channels, primary_epg


def is_local_channel_name(name: str) -> bool:
    """检查频道名是否包含地方名称前缀，用于判断是否属于地方频道"""
    for place in LOCAL_PLACE_NAMES:
        if name.startswith(place):
            return True
    return False


def merge_entry(target_entries: dict, norm_name: str, entry: dict) -> bool:
    """
    将条目加入目标分类（若已存在则合并URL），返回是否新增
    """
    if norm_name not in target_entries:
        target_entries[norm_name] = {
            "name": norm_name,
            "display_name": entry["display_name"],
            "urls": list(entry["urls"]),
            "url_qualities": list(entry.get("url_qualities", [])),
            "logo": entry["logo"],
            "tvg_id": entry["tvg_id"],
            "tvg_name": entry["tvg_name"],
        }
        return True
    # 合并URL（不重复添加）
    existing = target_entries[norm_name]
    added = 0
    for i, url in enumerate(entry["urls"]):
        if url not in existing["urls"]:
            existing["urls"].append(url)
            qualities = entry.get("url_qualities", [])
            existing["url_qualities"].append(
                qualities[i] if i < len(qualities) else 2
            )
            added += 1
    if added > 0:
        # 同步元数据
        if not existing["logo"] and entry["logo"]:
            existing["logo"] = entry["logo"]
        if not existing["tvg_id"] and entry["tvg_id"]:
            existing["tvg_id"] = entry["tvg_id"]
        if not existing["tvg_name"] and entry["tvg_name"]:
            existing["tvg_name"] = entry["tvg_name"]
    return False


def is_usable_url(url: str) -> bool:
    """过滤车机/家庭网络不可用的播放地址：
    - RTP 组播地址（rtp://239.x.x.x）需要局域网组播支持，普通车机无法播放
    - IPv6 地址（[2409:...] 或裸 IPv6）在多数车机网络环境不可用
    """
    u = url.strip().lower()
    if u.startswith('rtp://'):
        return False
    # IPv6 地址特征：任何包含 [ ] 的 URL（无论是否带端口）
    # 例如 http://[2409:...]:8080/... 或 http://[2409:...]/path
    if '[' in u:
        return False
    return True


def url_quality_priority(name: str) -> int:
    """根据频道名中的清晰度标注计算源优先级（数字越小越靠前）

    iptv-org 等源的频道名带清晰度后缀（如 "CCTV-1 (1080p)"、"东方卫视 (2160p)"）。
    优先级设计：
      0 = 4K/8K/2160p 超高清（首选）
      1 = 1080p 高清
      2 = 无清晰度标注的普通源（vbskycn/咪咕等，质量较稳定）
      3 = 720p
      4 = 576i/540p/480p 等低清晰度（备用）
    """
    n = name.lower()
    if any(k in n for k in ('4k', '8k', '2160p')):
        return 0
    if '1080' in n:
        return 1
    if '720' in n:
        return 3
    if any(k in n for k in ('576i', '576p', '540p', '480p', '360p')):
        return 4
    return 2


def classify_and_merge(channels: list) -> dict:
    """
    将频道按分类归类，跨源合并同名频道
    返回 {category: [{name, urls, logo, tvg_id, tvg_name}]}
    """
    # 第一步：按分类分组
    categorized = {cat: {} for cat in WANTED_CATEGORIES}  # {cat: {normalized_name: entry}}

    for ch in channels:
        # 过滤车机不可用的播放地址（RTP 组播 / IPv6）
        if not is_usable_url(ch["url"]):
            continue
        std_cat = match_category(ch["category"])
        # 名称含主题关键词的频道优先归入主题分类
        # 解决上游"数字"/"其它"/"内蒙频道"等分类匹配不到、或被误归付费频道的问题
        # 例如："动画高清"、"新动漫"、"嘉佳卡通"、"内蒙少儿"
        if std_cat is None or std_cat == "付费频道":
            theme_match = None
            for theme_cat, keywords in THEME_CATEGORY_KEYWORDS.items():
                if any(kw in ch["name"] for kw in keywords):
                    theme_match = theme_cat
                    break
            if theme_match:
                std_cat = theme_match
        # iptv-org 等英文分类源：按频道名推断央视/卫视
        if std_cat is None:
            std_cat = infer_category_from_name(ch["name"])
        # iptv-org 港澳台源：按频道名识别知名港澳台频道
        if std_cat is None:
            cleaned_name = re.sub(r'[\(\[][^\)\]]*[\)\]]', '', ch["name"]).strip()
            if cleaned_name in HKMOTW_KNOWN_CHANNELS:
                std_cat = "港澳台频道"
        if std_cat is None:
            continue
        if should_exclude(ch["name"]):
            continue

        norm_name = normalize_name(ch["name"])
        if not norm_name:
            continue

        # 显示名：iptv-org 等源的频道名带清晰度后缀（如 "CCTV-14 (1080p)"、"东方卫视 (2160p)"），
        # 统一使用标准化名作为显示名，避免同一频道出现多种带后缀的显示名
        # CCTV 系列（CCTV1、CCTV5+、CCTV风云足球等）一律用规范名，保证跨源显示一致
        # 英文频道名（如 "Jiangxi Children's Channel"）映射为中文后使用中文名
        display_name = ch["name"]
        # 港澳台频道：优先使用映射的中文名
        cleaned_name = re.sub(r'[\(\[][^\)\]]*[\)\]]', '', display_name).strip()
        if cleaned_name in HKMOTW_KNOWN_CHANNELS:
            display_name = HKMOTW_KNOWN_CHANNELS[cleaned_name]
        elif re.search(r'[\(\[][^\)\]]*[\)\]]', display_name):
            display_name = norm_name
        elif norm_name.startswith("CCTV") and norm_name != display_name:
            display_name = norm_name
        elif re.search(r'[\u4e00-\u9fff]', norm_name) and not re.search(r'[\u4e00-\u9fff]', display_name):
            display_name = norm_name

        # 频道归属强制覆盖
        override_cat = CHANNEL_CATEGORY_OVERRIDE.get(norm_name)
        if override_cat:
            std_cat = override_cat

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
                            "display_name": display_name,
                            "urls": [],
                            "url_qualities": [],
                            "logo": ch["logo"],
                            "tvg_id": ch["tvg_id"],
                            "tvg_name": ch["tvg_name"],
                        }
                    if ch["url"] not in local_entry[norm_name]["urls"]:
                        local_entry[norm_name]["urls"].append(ch["url"])
                        local_entry[norm_name]["url_qualities"].append(
                            url_quality_priority(ch["name"])
                        )
                continue

        entry = categorized[std_cat]
        if norm_name not in entry:
            entry[norm_name] = {
                "name": norm_name,
                "display_name": display_name,
                "urls": [],
                "url_qualities": [],
                "logo": ch["logo"],
                "tvg_id": ch["tvg_id"],
                "tvg_name": ch["tvg_name"],
            }
        # 添加URL（记录清晰度优先级，后续按优先级排序：高清在前，低清备用）
        if ch["url"] not in entry[norm_name]["urls"]:
            entry[norm_name]["urls"].append(ch["url"])
            entry[norm_name]["url_qualities"].append(url_quality_priority(ch["name"]))
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
                for i, url in enumerate(entry["urls"]):
                    if url not in existing["urls"]:
                        existing["urls"].append(url)
                        qualities = entry.get("url_qualities", [])
                        existing["url_qualities"].append(
                            qualities[i] if i < len(qualities) else 2
                        )
                if not existing["logo"] and entry["logo"]:
                    existing["logo"] = entry["logo"]
                if not existing["tvg_id"] and entry["tvg_id"]:
                    existing["tvg_id"] = entry["tvg_id"]
                if not existing["tvg_name"] and entry["tvg_name"]:
                    existing["tvg_name"] = entry["tvg_name"]
        if to_move:
            print(f"  将 {len(to_move)} 个非省级卫视移至地方频道: {', '.join(to_move[:5])}...")

    # 第三步：双向双分类交叉归类
    # (A) 主题分类交叉：地方频道/卫视频道/港澳台频道/央视频道中
    #     带主题关键词的频道（如"北京卡酷少儿"），同时归入对应主题分类（少儿/体育/电影等）
    THEME_SOURCE_CATS = ["央视频道", "卫视频道", "地方频道", "港澳台频道"]
    cross_count = 0
    for src_cat in THEME_SOURCE_CATS:
        if src_cat not in categorized:
            continue
        src_entries = categorized[src_cat]
        for norm_name, entry in list(src_entries.items()):
            # 1) 已知频道归属（央视少儿/体育等归一化后名称丢失主题信息的频道）
            known_theme = KNOWN_THEME_CHANNELS.get(norm_name)
            if known_theme and known_theme != src_cat and known_theme in categorized:
                if merge_entry(categorized[known_theme], norm_name, entry):
                    cross_count += 1
                continue
            # 2) 关键词匹配（用显示名和归一化名）
            match_text = entry["display_name"] + " " + norm_name
            for theme_cat, keywords in THEME_CATEGORY_KEYWORDS.items():
                if theme_cat == src_cat:
                    continue
                if any(kw in match_text for kw in keywords):
                    if merge_entry(categorized[theme_cat], norm_name, entry):
                        cross_count += 1
                    break  # 一个频道只交叉到第一个匹配的主题分类
    if cross_count > 0:
        print(f"  将 {cross_count} 个频道同时归入主题分类（双分类）")

    # (B) 地方交叉：所有主题分类（少儿/体育/电影/音乐/纪录）中的
    #     地方频道（如"广东少儿"），同时归入地方频道
    local_entries = categorized.get("地方频道", {})
    local_cross_count = 0
    for theme_cat in THEME_CATEGORY_KEYWORDS.keys():
        if theme_cat not in categorized:
            continue
        for norm_name, entry in list(categorized[theme_cat].items()):
            if is_local_channel_name(norm_name) or is_local_channel_name(entry["display_name"]):
                if merge_entry(local_entries, norm_name, entry):
                    local_cross_count += 1
    if local_cross_count > 0:
        print(f"  将 {local_cross_count} 个主题分类中的地方频道同时归入地方频道")

    # 转换为列表格式
    result = {}
    for cat in WANTED_CATEGORIES:
        entry = categorized[cat]
        items = list(entry.values())
        items.sort(key=lambda x: natural_sort_key(x["name"]))
        # 每个频道的播放源按清晰度优先级排序：
        # 4K/1080p 高清源放最前（首选），720p/标清源放最后（备用）
        for it in items:
            if len(it.get("url_qualities", [])) > 1:
                pairs = sorted(zip(it["urls"], it["url_qualities"]), key=lambda p: p[1])
                it["urls"] = [p[0] for p in pairs]
                it["url_qualities"] = [p[1] for p in pairs]
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
    """生成TXT格式（与vbskycn兼容：每个源单独一行，同名频道重复多次）"""
    lines = []
    for cat in WANTED_CATEGORIES:
        items = categorized.get(cat, [])
        if not items:
            continue
        lines.append(f"{cat},#genre#")
        for it in items:
            # 输出该频道全部源地址，同名频道多次出现（App端解析后会合并为多源）
            for url in it["urls"]:
                lines.append(f"{it['display_name']},{url}")
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