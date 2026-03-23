import os
import sys
import json
import argparse
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()


def call_llm(config, content):
    """调用大模型 API 进行分析"""
    
    system_prompt = """你是一位专业的金融市场分析师，擅长从股票论坛中识别投资机会。
请分析用户提供的HTML内容，提取其中的股票相关信息，并总结和梳理其中的投资机会。

请使用脑图格式输出，使用Markdown的树形结构（-、--、---）来组织层次关系，格式如下：

# 淘股吧投资机会分析

## 一、涉及的股票/板块
- 板块1
  - 个股1
  - 个股2
- 板块2
  - 个股3

## 二、关键信息摘要
- 宏观/市场情绪
  - 要点1
  - 要点2
- 产业/公司动态
  - 要点1
  - 要点2

## 三、投资机会
- 机会类型1
  - 逻辑说明
  - 推荐标的
- 机会类型2
  - 逻辑说明
  - 推荐标的

## 四、风险提示
- 风险1
- 风险2

注意：如果HTML内容中没有有价值的投资相关信息，请明确说明。"""

    provider = config.get("provider", "openai")
    api_key = config.get("api_key")
    base_url = config.get("base_url", "")
    model = config.get("model", "gpt-4o")

    headers = {
        "Content-Type": "application/json"
    }

    if provider == "anthropic":
        url = f"https://api.anthropic.com/v1/messages"
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        payload = {
            "model": model,
            "max_tokens": 4000,
            "temperature": 0.7,
            "system": system_prompt,
            "messages": [{"role": "user", "content": f"请分析以下HTML内容：\n\n{content}"}]
        }
    else:
        if base_url:
            url = f"{base_url.rstrip('/')}/chat/completions"
        else:
            url = "https://api.openai.com/v1/chat/completions"
        
        headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请分析以下HTML内容：\n\n{content}"}
            ],
            "temperature": 0.7,
            "max_tokens": 4000
        }

    import requests
    
    if provider == "anthropic":
        response = requests.post(url, headers=headers, json=payload, timeout=120)
    else:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
    
    response.raise_for_status()
    result = response.json()

    if provider == "anthropic":
        return result["content"][0]["text"]
    else:
        return result["choices"][0]["message"]["content"]


def extract_text_from_html(html_content, max_chars=100000):
    """从HTML中提取纯文本内容，并进行截断"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    for script in soup(["script", "style"]):
        script.decompose()
    
    text = soup.get_text(separator='\n', strip=True)
    
    lines = (line.strip() for line in text.split('\n'))
    lines = [line for line in lines if line]
    text = '\n'.join(lines)
    
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n... [内容已被截断，原始长度: {len(text)} 字符]"
    
    return text


def load_provider_config(provider):
    """从环境变量加载提供商配置"""
    if provider == "custom":
        return {
            "provider": "custom",
            "api_key": os.getenv("CUSTOM_API_KEY", ""),
            "base_url": os.getenv("CUSTOM_BASE_URL", ""),
            "model": os.getenv("CUSTOM_MODEL", "gpt-4o")
        }
    elif provider == "deepseek":
        return {
            "provider": "deepseek",
            "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
            "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        }
    elif provider == "anthropic":
        return {
            "provider": "anthropic",
            "api_key": os.getenv("ANTHROPIC_API_KEY", ""),
            "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        }
    else:
        return {
            "provider": "openai",
            "api_key": os.getenv("OPENAI_API_KEY", ""),
            "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            "model": os.getenv("OPENAI_MODEL", "gpt-4o")
        }


def main():
    parser = argparse.ArgumentParser(description="分析HTML内容并调用大模型识别投资机会")
    parser.add_argument("html_path", help="HTML文件的路径")
    parser.add_argument("--provider", 
                        choices=["openai", "deepseek", "anthropic", "custom"], 
                        default="aliyun", 
                        help="模型提供商")
    parser.add_argument("--model", help="使用的模型名称（可选，将覆盖环境变量中的配置）")
    args = parser.parse_args()

    provider_map = {
        "aliyun": "custom",
        "openai": "openai",
        "deepseek": "deepseek", 
        "anthropic": "anthropic",
        "custom": "custom"
    }
    
    provider = provider_map.get(args.provider, "custom")
    
    if args.provider == "aliyun":
        config = {
            "provider": "custom",
            "api_key": os.getenv("DASHSCOPE_API_KEY", ""),
            "base_url": os.getenv("DASHSCOPE_BASE_URL", "https://coding.dashscope.aliyuncs.com/v1"),
            "model": args.model or os.getenv("DASHSCOPE_MODEL", "qwen3.5-plus")
        }
    else:
        config = load_provider_config(provider)
        if args.model:
            config["model"] = args.model

    html_path = args.html_path
    
    if not os.path.exists(html_path):
        print(f"错误: 文件不存在: {html_path}")
        sys.exit(1)

    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    print(f"已读取HTML文件: {html_path}")
    print(f"HTML文件大小: {len(html_content)} 字符")
    
    text_content = extract_text_from_html(html_content, max_chars=100000)
    print(f"提取文本长度: {len(text_content)} 字符")

    if not config.get("api_key"):
        print(f"错误: 未设置 API Key 环境变量")
        sys.exit(1)

    print(f"正在调用 {args.provider} 大模型 {config.get('model')} 进行分析...")
    print(f"Base URL: {config.get('base_url', '默认')}")
    
    try:
        result = call_llm(config, text_content)
        print("\n" + "="*60)
        print("分析结果:")
        print("="*60)
        print(result)
    except Exception as e:
        print(f"调用大模型失败: {e}")
        try:
            import requests
            test_r = requests.post(
                config.get("base_url", "").rstrip('/') + "/chat/completions",
                headers={"Authorization": f"Bearer {config.get('api_key')}", "Content-Type": "application/json"},
                json={"model": config.get("model"), "messages": [{"role": "user", "content": "hello"}], "max_tokens": 10},
                timeout=10
            )
            print(f"测试调用状态: {test_r.status_code}")
            print(f"测试调用响应: {test_r.text[:500]}")
        except:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
