#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from app_common import NotificationClient
from scripts import crawler_bbs, crawler_home


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output"
STATE_DIR = PROJECT_ROOT / "state"
REPORT_RETENTION_DAYS = 30


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str
    model: str


@dataclass(frozen=True)
class TaogubaConfig:
    source: str
    bbs_url: str
    home_max_pages: int
    article_delay_seconds: float
    max_chars: int
    llm: LLMConfig
    notification_exe: str
    notification_channel: str

    @classmethod
    def from_env(cls) -> "TaogubaConfig":
        source = os.getenv("TAOGUBA_SOURCE", "bbs").strip().lower() or "bbs"
        if source not in {"bbs", "home"}:
            raise ValueError(f"TAOGUBA_SOURCE 只支持 bbs/home，当前值: {source}")
        return cls(
            source=source,
            bbs_url=os.getenv("TAOGUBA_BBS_URL", "https://www.tgb.cn/bbs/1/1").strip(),
            home_max_pages=max(1, int(os.getenv("TAOGUBA_HOME_MAX_PAGES", "2"))),
            article_delay_seconds=max(0.0, float(os.getenv("TAOGUBA_ARTICLE_DELAY_SECONDS", "0.5"))),
            max_chars=max(2000, int(os.getenv("TAOGUBA_LLM_MAX_CHARS", "100000"))),
            llm=LLMConfig(
                api_key=os.getenv("DASHSCOPE_API_KEY", "").strip(),
                base_url=os.getenv("DASHSCOPE_BASE_URL", "https://coding.dashscope.aliyuncs.com/v1").strip(),
                model=os.getenv("DASHSCOPE_MODEL", "qwen3.5-plus").strip(),
            ),
            notification_exe=os.getenv("PICOCLAW_EXE", "").strip(),
            notification_channel=os.getenv("PICOCLAW_CHANNEL", "feishu").strip(),
        )


class TaogubaReporter:
    def __init__(self, config: TaogubaConfig, logger) -> None:
        self.config = config
        self.logger = logger
        self.notification = NotificationClient(config.notification_exe, config.notification_channel)
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def run_once(self, send_notification: bool = True) -> dict:
        report = self._build_report()
        self._cleanup_old_files()
        self._save_report(report)
        if send_notification:
            self._send_report(report)
        return report

    def run_testsend(self, use_existing: bool) -> dict:
        if use_existing:
            report = self.load_latest_report()
            if not report:
                raise Exception("未找到可复用的 latest_report.json，请先执行 testsend-live 或等待定时任务跑完。")
        else:
            report = self.run_once(send_notification=False)
        self._send_report(report)
        return report

    def load_latest_report(self) -> dict | None:
        path = STATE_DIR / "latest_report.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _build_report(self) -> dict:
        if not self.config.llm.api_key:
            raise Exception("DASHSCOPE_API_KEY 未配置，无法执行分析。")
        module = crawler_bbs if self.config.source == "bbs" else crawler_home
        source_label = "股吧论坛" if self.config.source == "bbs" else "首页推荐"
        self.logger.log(f"开始抓取 {source_label}")
        with self._project_cwd():
            articles = self._crawl_articles(module)
            json_path = Path(module.save_to_json(articles)).resolve()
            headers = module.get_headers()
            articles_data = []
            for index, article in enumerate(articles, start=1):
                self.logger.log(f"[{index}/{len(articles)}] 抓取正文: {article['title']}")
                article_data = module.get_article_content(article["url"], headers)
                if article_data:
                    articles_data.append(article_data)
                time.sleep(self.config.article_delay_seconds)
            html_path = Path(module.create_html(articles_data)).resolve()

        html_text = html_path.read_text(encoding="utf-8", errors="replace")
        analysis = self._call_llm(self._extract_text_from_html(html_text)).strip()
        report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        titles = [article["title"] for article in articles[:10]]
        return {
            "generated_at": report_time,
            "source": self.config.source,
            "source_label": source_label,
            "article_count": len(articles),
            "titles": titles,
            "json_path": str(json_path),
            "html_path": str(html_path),
            "analysis": analysis,
            "notification_message": self._format_notification_message(
                generated_at=report_time,
                source_label=source_label,
                article_count=len(articles),
                analysis=analysis,
            ),
            "config": {
                "source": self.config.source,
                "bbs_url": self.config.bbs_url,
                "home_max_pages": self.config.home_max_pages,
                "model": self.config.llm.model,
            },
        }

    def _crawl_articles(self, module):
        if self.config.source == "bbs":
            return module.crawl_articles(url=self.config.bbs_url)
        return module.crawl_articles(max_pages=self.config.home_max_pages)

    def _call_llm(self, content: str) -> str:
        system_prompt = (
            "你是一位专业的金融市场分析师，擅长从淘股吧文章里识别投资机会。"
            "请基于用户提供的正文内容，提取涉及的股票、板块、逻辑链条和风险。"
            "输出使用简洁中文 Markdown，必须包含以下章节：今日关注方向、重点个股/板块、主要逻辑、风险提示。"
            "不要输出 #、##、### 标题。"
            "如果使用 Markdown 标题，最高只能使用 ####。"
            "如果没有足够有效的信息，也要明确说明。"
        )
        payload = {
            "model": self.config.llm.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            "temperature": 0.3,
            "max_tokens": 4000,
        }
        headers = {
            "Authorization": f"Bearer {self.config.llm.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.config.llm.base_url.rstrip('/')}/chat/completions"
        response = requests.post(url, headers=headers, json=payload, timeout=180)
        response.raise_for_status()
        data = response.json()
        return self._normalize_markdown(data["choices"][0]["message"]["content"])

    def _normalize_markdown(self, text: str) -> str:
        normalized_lines: list[str] = []
        for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = raw_line.rstrip()
            match = re.match(r"^\s{0,3}(#+)\s*(.*)$", line)
            if match:
                title = match.group(2).strip()
                normalized_lines.append(f"#### {title}" if title else "####")
            else:
                normalized_lines.append(line)
        return "\n".join(normalized_lines).strip()

    def _extract_text_from_html(self, html_content: str) -> str:
        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        normalized = "\n".join(lines)
        if len(normalized) > self.config.max_chars:
            normalized = (
                normalized[: self.config.max_chars]
                + f"\n\n... [正文已截断，原始长度 {len(normalized)} 字符]"
            )
        return normalized

    def _format_notification_message(
        self,
        generated_at: str,
        source_label: str,
        article_count: int,
        analysis: str,
    ) -> str:
        header = [
            f"淘股吧复盘 | {generated_at}",
            f"来源：{source_label} | 文章：{article_count} 篇",
            "",
        ]
        return "\n".join(header) + analysis

    def _save_report(self, report: dict) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        latest_path = STATE_DIR / "latest_report.json"
        dated_path = STATE_DIR / f"report-{timestamp}.json"
        latest_markdown_path = OUTPUT_DIR / "latest_report.md"
        dated_markdown_path = OUTPUT_DIR / f"report-{timestamp}.md"
        payload = json.dumps(report, ensure_ascii=False, indent=2)
        markdown = report.get("notification_message", "").strip() + "\n"
        latest_path.write_text(payload, encoding="utf-8")
        dated_path.write_text(payload, encoding="utf-8")
        latest_markdown_path.write_text(markdown, encoding="utf-8")
        dated_markdown_path.write_text(markdown, encoding="utf-8")

    def _send_report(self, report: dict) -> None:
        message = report.get("notification_message", "").strip()
        if not message:
            raise Exception("报告为空，无法发送通知。")
        if not self.notification.enabled:
            raise Exception("PICOCLAW_EXE 未配置，无法发送通知。")
        if not self.notification.send(message):
            raise Exception(f"通知发送失败: {self.notification.last_error or '未知错误'}")

    def _cleanup_old_files(self) -> None:
        cutoff = datetime.now() - timedelta(days=REPORT_RETENTION_DAYS)
        for path in STATE_DIR.glob("report-*.json"):
            stamp = path.stem.replace("report-", "")
            try:
                file_time = datetime.strptime(stamp, "%Y%m%d-%H%M%S")
            except ValueError:
                continue
            if file_time < cutoff:
                try:
                    path.unlink()
                except OSError:
                    pass
        for path in OUTPUT_DIR.glob("report-*.md"):
            stamp = path.stem.replace("report-", "")
            try:
                file_time = datetime.strptime(stamp, "%Y%m%d-%H%M%S")
            except ValueError:
                continue
            if file_time < cutoff:
                try:
                    path.unlink()
                except OSError:
                    pass

    @contextmanager
    def _project_cwd(self):
        original = Path.cwd()
        os.chdir(PROJECT_ROOT)
        try:
            yield
        finally:
            os.chdir(original)
