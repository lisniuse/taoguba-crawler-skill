import os
import sys
import json
import requests
import re
import time
import base64
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv
from io import BytesIO
from urllib.parse import urljoin

# 加载环境变量
load_dotenv()

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# 基础URL
BASE_URL = "https://www.tgb.cn"


def get_headers():
    """从环境变量获取请求头"""
    return {
        "Cookie": os.getenv("COOKIE", ""),
        "User-Agent": os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    }


def crawl_articles(url="https://www.tgb.cn/bbs/1/1"):
    """爬取文章列表"""
    headers = get_headers()

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'
    except requests.RequestException as e:
        print(f"请求失败: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')

    # 选择 class 为 "overhide mw300" 的 a 标签
    articles = soup.select('a.overhide.mw300')

    result = []
    for article in articles:
        href = article.get('href', '')
        title = article.get('title', '') or article.get_text(strip=True)

        # 构建完整URL
        if href and not href.startswith('http'):
            # 如果 href 以 a/ 或 /a/ 开头，直接拼接到 BASE_URL
            if href.startswith('a/') or href.startswith('/a/'):
                full_url = urljoin(BASE_URL, href)
            else:
                full_url = f"{BASE_URL}/bbs/{href}"
        else:
            full_url = href

        result.append({
            "title": title,
            "url": full_url,
            "href": href
        })

    return result


def save_to_json(data):
    """保存到 output 文件夹，以日期为文件名"""
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)

    filename = "bbs_" + datetime.now().strftime("%Y-%m-%d") + ".json"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"已保存到: {filepath}")
    return filepath


def download_image(img_url, headers):
    """下载图片并返回 BytesIO 对象"""
    try:
        # 处理相对路径
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif not img_url.startswith('http'):
            img_url = urljoin(BASE_URL, img_url)

        response = requests.get(img_url, headers=headers, timeout=10)
        response.raise_for_status()
        return BytesIO(response.content)
    except Exception as e:
        print(f"  下载图片失败 {img_url}: {e}")
        return None


def get_article_content(url, headers):
    """获取单篇文章的楼主所有内容（主帖+楼主跟帖）"""
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'
    except requests.RequestException as e:
        print(f"  获取文章失败 {url}: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')

    # 1. 获取文章标题
    # 参考 p.txt: <div class="article-tittle" id="stockTitle">
    title_elem = soup.select_one('#stockTitle')
    if not title_elem:
        title_elem = soup.select_one('.article-tittle')
    
    title = title_elem.get_text(strip=True) if title_elem else "无标题"

    contents = []

    # 2. 获取主帖内容
    # 参考 p.txt: <div class="article-text p_coten" id="first" style="">
    main_content_elem = soup.select_one('#first')
    if not main_content_elem:
        main_content_elem = soup.select_one('.article-text.p_coten')

    if main_content_elem:
        # 主帖内容
        main_content = {
            "type": "main",
            "text": main_content_elem.get_text(strip=True),
            "html": str(main_content_elem),
            "images": []
        }
        # 获取主帖中的图片
        for img in main_content_elem.select('img'):
            # 优先取 data-original，其次取 src
            img_src = img.get('data-original') or img.get('src')
            if img_src and not img_src.endswith('.gif'):  # 排除表情gif
                main_content["images"].append(img_src)
        contents.append(main_content)

    # 3. 获取楼主的跟帖内容
    # 参考 p.txt: 楼主回复在 <div class="comment-data ..."> 中
    comment_blocks = soup.select('.comment-data')
    for block in comment_blocks:
        # 检查是否是楼主的跟帖
        # 楼主标识在 <div class="comment-data-user"> 下的 span 中，内容为 "楼主"
        user_info = block.select_one('.comment-data-user')
        if not user_info:
            continue
            
        is_author = False
        for span in user_info.select('span'):
            if span.get_text(strip=True) == '楼主':
                is_author = True
                break
        
        if is_author:
            # 内容在 <div class="comment-data-text" ...>
            text_elem = block.select_one('.comment-data-text')
            if text_elem:
                reply_content = {
                    "type": "reply",
                    "text": text_elem.get_text(strip=True),
                    "html": str(text_elem),
                    "images": []
                }
                # 获取跟帖中的图片
                for img in text_elem.select('img'):
                    # 优先取 data-original，其次取 src
                    img_src = img.get('data-original') or img.get('src')
                    if img_src and not img_src.endswith('.gif'):
                        reply_content["images"].append(img_src)
                contents.append(reply_content)

    return {
        "title": title,
        "url": url,
        "contents": contents
    }


def image_to_base64(img_bytes):
    """将图片字节转换为base64字符串"""
    if not img_bytes:
        return None
    return base64.b64encode(img_bytes.getvalue()).decode('utf-8')


def create_html(articles_data):
    """根据爬取的文章数据创建 HTML 文件"""
    
    html_content = ["""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>淘股吧文章汇总</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max_width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background-color: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1.doc-title {
            text-align: center;
            color: #d32f2f;
            margin-bottom: 10px;
        }
        .meta-info {
            text-align: center;
            color: #666;
            margin-bottom: 40px;
            font-size: 0.9em;
        }
        .article {
            margin-bottom: 60px;
            border-bottom: 1px solid #eee;
            padding-bottom: 40px;
        }
        .article-title {
            font-size: 24px;
            color: #1a237e;
            margin-bottom: 10px;
            border-left: 5px solid #1a237e;
            padding-left: 15px;
        }
        .source-link {
            font-style: italic;
            color: #666;
            margin-bottom: 20px;
            display: block;
        }
        .section-title {
            font-size: 18px;
            font-weight: bold;
            background-color: #e3f2fd;
            padding: 8px 15px;
            border-radius: 4px;
            margin-top: 30px;
            margin-bottom: 15px;
            color: #0d47a1;
        }
        .content-text {
            white-space: pre-wrap;
            margin-bottom: 20px;
        }
        .content-image {
            text-align: center;
            margin: 20px 0;
        }
        .content-image img {
            max-width: 100%;
            height: auto;
            border-radius: 4px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .error-msg {
            color: red;
            font-size: 0.9em;
        }
        .divider {
            border-top: 2px dashed #ccc;
            margin: 40px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="doc-title">淘股吧文章汇总</h1>
        <div class="meta-info">生成时间: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</div>
    """]

    headers = get_headers()

    for idx, article in enumerate(articles_data, 1):
        if article is None:
            continue

        print(f"  正在处理第 {idx} 篇: {article['title']}")

        # 文章开始
        html_content.append(f"""
        <div class="article">
            <h2 class="article-title">{article['title']}</h2>
            <a href="{article['url']}" class="source-link" target="_blank">来源: {article['url']}</a>
        """)

        # 添加内容
        for content in article.get('contents', []):
            section_name = '主帖内容' if content['type'] == 'main' else '楼主跟帖'
            html_content.append(f'<div class="section-title">{section_name}</div>')
            
            # 添加文本内容
            html_content.append(f'<div class="content-text">{content["text"]}</div>')

            # 添加图片
            for img_url in content.get('images', []):
                img_data = download_image(img_url, headers)
                if img_data:
                    base64_str = image_to_base64(img_data)
                    if base64_str:
                        # 简单的图片类型判断，默认为jpg，实际浏览器能容错
                        img_type = "jpeg"
                        if img_url.lower().endswith('.png'):
                            img_type = "png"
                        elif img_url.lower().endswith('.gif'):
                            img_type = "gif"
                            
                        html_content.append(f"""
                        <div class="content-image">
                            <img src="data:image/{img_type};base64,{base64_str}" alt="图片">
                        </div>
                        """)
                    else:
                        html_content.append(f'<div class="error-msg">[图片转换失败: {img_url}]</div>')
                else:
                    html_content.append(f'<div class="error-msg">[图片加载失败: {img_url}]</div>')

        html_content.append("</div>") # article end

    html_content.append("""
    </div>
</body>
</html>
    """)

    # 保存文档
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    filename = "bbs_" + datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".html"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("".join(html_content))
        
    print(f"已生成 HTML 文件: {filepath}")
    return filepath


def main():
    print("=" * 50)
    print("开始爬取文章列表...")
    print("=" * 50)

    articles = crawl_articles()

    if not articles:
        print("未爬取到任何文章")
        return

    print(f"共爬取到 {len(articles)} 篇文章")

    # 保存文章列表到 JSON
    save_to_json(articles)

    # 打印文章预览
    print("\n文章列表预览:")
    for i, article in enumerate(articles[:5], 1):
        print(f"  {i}. {article['title']}")
    if len(articles) > 5:
        print(f"  ... 还有 {len(articles) - 5} 篇")

    print("\n" + "=" * 50)
    print("开始获取文章详细内容...")
    print("=" * 50)

    headers = get_headers()
    articles_data = []

    for idx, article in enumerate(articles, 1):
        print(f"[{idx}/{len(articles)}] 正在获取: {article['title']}")
        data = get_article_content(article['url'], headers)
        articles_data.append(data)
        # 添加延时，避免请求过快
        time.sleep(0.5)

    print("\n" + "=" * 50)
    print("开始生成 HTML 文件...")
    print("=" * 50)

    # 生成 HTML 文件
    create_html(articles_data)

    print("\n完成!")


if __name__ == "__main__":
    main()
