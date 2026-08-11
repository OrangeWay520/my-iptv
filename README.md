# 橙子网络电视 - 自定义IPTV播放列表

从 [vbskycn/iptv](https://github.com/vbskycn/iptv) 自动筛选生成个性化M3U播放列表。

## 频道分类

- 央视频道
- 卫视频道
- 地方频道
- 港澳台频道
- 少儿频道
- 体育频道
- 电影频道
- 音乐频道
- 纪录频道
- 付费频道

## 订阅地址

M3U格式（推荐，带台标和EPG）：
```
https://raw.githubusercontent.com/你的用户名/你的仓库名/main/my_channels.m3u
```

TXT格式：
```
https://raw.githubusercontent.com/你的用户名/你的仓库名/main/my_channels.txt
```

## 在橙子网络电视中使用

1. 打开App设置 → 播放列表设置
2. 将"播放列表地址"改为上述M3U链接
3. 返回首页，自动加载

## 自定义修改

编辑 `generate_m3u.py` 文件：

- 修改 `WANTED_CATEGORIES` 列表可以调整频道分类
- 修改 `EXCLUDE_KEYWORDS` 列表可以屏蔽不需要的频道
- 修改 `SOURCE_URL` 可以切换数据源（IPv4/IPv6/混合）

## 自动更新

GitHub Actions 每6小时自动更新一次，也可以在仓库的 Actions 页面手动触发更新。