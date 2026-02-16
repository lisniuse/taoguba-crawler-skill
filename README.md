# Taoguba Crawler - 淘股吧爬虫

爬取[淘股吧](https://www.tgb.cn)文章内容，提取楼主主帖及跟帖，下载图片并生成 HTML 文件。

## 功能

- **BBS 板块爬取** (`crawler_bbs.py`) — 爬取论坛板块文章列表（HTML 解析）
- **首页推荐爬取** (`crawler_home.py`) — 爬取首页推荐文章（JSON API）
- 自动提取楼主主帖 + 楼主跟帖内容
- 下载文章图片并以 base64 嵌入 HTML
- 输出 JSON（文章列表）和 HTML（完整内容）

## 环境要求

- Python 3.8+

## 安装

```bash
git clone https://github.com/your-username/Taoguba-crawler.git
cd Taoguba-crawler
pip install -r requirements.txt
```

## 配置

在项目根目录创建 `.env` 文件：

```env
COOKIE=你的淘股吧Cookie
USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
```

> 登录淘股吧后，从浏览器开发者工具中复制 Cookie。

## 使用

```bash
# 爬取 BBS 板块
python crawler_bbs.py

# 爬取首页推荐
python crawler_home.py
```

## 输出

所有结果保存在 `output/` 目录下：

| 文件 | 说明 |
|------|------|
| `bbs_YYYY-MM-DD.json` | BBS 文章列表 |
| `bbs_YYYY-MM-DD_HHMMSS.html` | BBS 文章内容（含图片） |
| `home_YYYY-MM-DD.json` | 首页文章列表 |
| `home_YYYY-MM-DD_HHMMSS.html` | 首页文章内容（含图片） |

## 项目结构

```
Taoguba-crawler/
├── crawler_bbs.py       # BBS 板块爬虫
├── crawler_home.py      # 首页推荐爬虫
├── requirements.txt     # Python 依赖
├── .env                 # 配置文件（不要提交到仓库）
└── output/              # 输出目录
```

## 注意事项

- 请求间隔 0.5~1 秒，避免频繁访问被封
- `.env` 文件包含敏感信息，已在 `.gitignore` 中排除
- 本项目仅供学习交流使用

## License

MIT
