# 🍊 橙子网络电视 - 自定义IPTV播放列表

一个自动化聚合多路公开直播源、按需筛选分类、自动去重合并的 **M3U/TXT 播放列表生成项目**。

由 [generate_m3u.py](generate_m3u.py) 脚本驱动，配合 GitHub Actions **每 6 小时自动更新**，为 [橙子网络电视（OrangeIPTV.Car）](https://github.com/OrangeWay520/OrangeIPTV.Car) 提供播放列表数据，也可用于任何支持 M3U/TXT 订阅的播放器。

> ⚠️ **免责声明**：本仓库仅用于技术学习与个人娱乐，所有直播流均引用自下方开源项目，**不存储、不录制、不传播任何原始视频内容**。播放源随时可能失效，请以各上游源实时数据为准。

---

## 📡 数据来源与致谢

本项目聚合了以下开源直播源项目的数据。**在此对各位作者的无私分享表示由衷的感谢！** 🙏

| 数据源 | 说明 | 提供内容 | 链接 |
| --- | --- | --- | --- |
| **vbskycn/iptv** | 主数据源，国内频道丰富，带台标与EPG | 央视/卫视/地方/少儿/体育/电影等国内频道，多线路播放地址 | [GitHub](https://github.com/vbskycn/iptv) |
| **vbskycn/iptv 镜像**（live.zbds.top） | 主源的备用 CDN，内容一致 | 同上数据的 M3U/TXT 双格式 | [GitHub](https://github.com/vbskycn/iptv) |
| **iptv-org/iptv** | 全球最大的公开 IPTV 聚合项目，频道直链稳定 | 中国大陆频道高清源、香港/澳门/台湾知名频道（凤凰、TVB系、澳广视、台视/华视/民视等） | [GitHub](https://github.com/iptv-org/iptv) · [网站](https://iptv-org.github.io) |
| **sammy0101/hk-iptv-auto** | 香港本地自动维护源 | 翡翠台、明珠台、無線新聞、TVB Plus 等 TVB 系列频道（版权严格，仅此源收录） | [GitHub](https://github.com/sammy0101/hk-iptv-auto) |

**再次感谢以上所有项目的维护者与贡献者**，正是你们的持续维护，才有了这份播放列表。

> 上游数据源获取逻辑详见 [generate_m3u.py](generate_m3u.py) 中的 `SOURCE_URLS` 配置。

---

## ✨ 特性

- ✅ **多源聚合**：自动抓取 4 个上游项目、8 路数据流，跨源合并同名频道
- ✅ **多源播放**：每个频道保留全部可用播放地址，失效自动切换（如 CCTV1 常有 8+ 个源）
- ✅ **智能分类**：按类别自动归类（央视/卫视/地方/港澳台/少儿/体育/电影/音乐/纪录/付费）
- ✅ **去重归一**：跨源频道名自动归一化（`CCTV-1 (1080p)` → `CCTV1`），剔除捐赠/广告/轮播等无用频道
- ✅ **清晰度优先**：播放源按 4K/1080p/720p/标清 排序，高清源优先播放
- ✅ **车机友好**：自动过滤 `rtp://` 组播与 IPv6 地址（车机网络不可用）
- ✅ **港澳台精选**：内置凤凰、翡翠台、明珠台、澳广视、台视等知名频道
- ✅ **中文拼音排序**：所有分类按频道名拼音自然排序
- ✅ **自动更新**：GitHub Actions 每 6 小时自动刷新，无需手动维护
- ✅ **台标 + EPG**：携带 `tvg-logo` 台标与 `x-tvg-url` 节目预告数据

---

## 📋 频道分类

| 分类 | 说明 |
| --- | --- |
| 央视频道 | CCTV 系列、CGTN、CETV 等 |
| 卫视频道 | 各省/直辖市省级卫视（非省级卫视自动移至地方频道） |
| 地方频道 | 各省市地方台 |
| 港澳台频道 | 香港/澳门/台湾知名频道（翡翠台、凤凰、澳视、台视等） |
| 少儿频道 | 央视少儿及各地少儿/动漫频道 |
| 体育频道 | 央视体育及各地体育频道 |
| 电影频道 | 央视电影、CHC 系列及各地影视频道 |
| 音乐频道 | 央视音乐及各地音乐频道 |
| 纪录频道 | 央视纪录/科教及各地纪实频道 |
| 付费频道 | 风云剧场、兵器科技等付费频道 |

---

## 🔗 订阅地址

> ⚠️ **注意**：本仓库默认分支为 `master`，订阅地址中的分支名必须写 `master`（写 `main` 会返回 404）。

**M3U 格式（推荐，带台标和 EPG）：**

```
https://raw.githubusercontent.com/OrangeWay520/my-iptv/master/my_channels.m3u
```

**TXT 格式：**

```
https://raw.githubusercontent.com/OrangeWay520/my-iptv/master/my_channels.txt
```

**加速镜像（jsDelivr，国内访问更快，注意缓存可能延迟）：**

```
https://cdn.jsdelivr.net/gh/OrangeWay520/my-iptv@master/my_channels.m3u
https://cdn.jsdelivr.net/gh/OrangeWay520/my-iptv@master/my_channels.txt
```

---

## 📱 在橙子网络电视（OrangeIPTV.Car）中使用

1. 打开 App → 设置 → 播放列表设置
2. 将「播放列表地址」改为上述 M3U 链接
3. 返回首页，自动加载频道

App 支持 M3U+TXT 双源合并：在设置中开启「合并播放列表源」开关，再填入 TXT 订阅地址即可让每个频道同时拥有 M3U 与 TXT 的播放源。

---

## 🛠️ 自定义修改

编辑 [generate_m3u.py](generate_m3u.py)，按需调整以下配置：

| 配置项 | 作用 |
| --- | --- |
| `SOURCE_URLS` | 上游数据源列表（M3U/TXT 均可），按优先级排列 |
| `WANTED_CATEGORIES` | 需要的频道分类及顺序 |
| `CATEGORY_ALIASES` | 不同源的分类名映射 |
| `CHANNEL_NAME_ALIASES` | 跨源频道名归一化映射 |
| `EXCLUDE_KEYWORDS` | 排除的频道关键词（捐赠/广告/轮播等） |
| `EXCLUDE_NAMES` | 精确排除的频道名 |
| `PROVINCIAL_SATELLITE_TV` | 省级卫视白名单 |
| `CHANNEL_CATEGORY_OVERRIDE` | 频道归属强制覆盖 |
| `HKMOTW_KNOWN_CHANNELS` | 港澳台知名频道名映射表 |
| `LOCAL_PLACE_NAMES` | 地方频道前缀识别表 |

修改完成后，手动执行 `python generate_m3u.py` 生成播放列表，或推送代码后由 GitHub Actions 自动重新生成。

---

## 🔄 自动更新机制

`.github/workflows/update.yml` 工作流：

- ⏱️ **定时触发**：每 6 小时自动运行一次
- 📡 运行 `generate_m3u.py` 拉取上游最新数据
- 📝 生成 `my_channels.m3u` / `my_channels.txt`
- 🚀 有更新时自动提交并推送，无变化则跳过
- 👆 也可在仓库 Actions 页面手动触发「Run workflow」

---

## 📄 项目结构

```
.
├── generate_m3u.py          # 播放列表生成脚本（核心）
├── my_channels.m3u          # 生成的 M3U 播放列表（带台标+EPG）
├── my_channels.txt          # 生成的 TXT 播放列表
└── .github/workflows/
    └── update.yml           # 每6小时自动更新工作流
```

---

## 📝 许可证与声明

- 本项目代码仅供学习交流，请在遵守当地法律法规的前提下使用
- 所有直播源版权归原权利人所有，数据引用遵循各上游项目许可
- 播放地址可能因网络环境/版权原因失效，如遇失效请等待自动更新或更换播放源

---

⭐ 如果这个项目对你有帮助，欢迎 Star 支持！也感谢所有上游开源项目！
