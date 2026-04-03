#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, time as dt_time
from pathlib import Path

from app_common import DailyLogger, load_env_file
from scripts.taoguba_report import TaogubaConfig, TaogubaReporter


PROJECT_ROOT = Path(__file__).resolve().parent
LOG_DIR = PROJECT_ROOT / "logs"
STATE_DIR = PROJECT_ROOT / "state"
CHECK_INTERVAL_SECONDS = 30


class DailySchedulerService:
    def __init__(self) -> None:
        load_env_file()
        self.scrape_time = self._parse_scrape_time(os.getenv("SCRAPE_TIME", "19:00"))
        self.logger = DailyLogger(LOG_DIR, "taoguba-main")
        self.reporter = TaogubaReporter(TaogubaConfig.from_env(), self.logger)
        self.state_path = STATE_DIR / "main_state.json"
        self.last_run_date = self._load_last_run_date()

    def run_forever(self) -> None:
        self.logger.log(f"淘股吧主进程已启动，每日执行时间 {self.scrape_time.strftime('%H:%M')}")
        while True:
            try:
                now = datetime.now()
                if self._should_run(now):
                    report = self.reporter.run_once(send_notification=True)
                    self.last_run_date = now.strftime("%Y-%m-%d")
                    self._save_last_run_date()
                    self.logger.log(f"本轮执行完成 source={report['source']} articles={report['article_count']}")
            except KeyboardInterrupt:
                self.logger.log("收到退出信号，主进程结束")
                raise
            except Exception as exc:
                self.logger.log(f"本轮执行失败: {exc}")
            time.sleep(CHECK_INTERVAL_SECONDS)

    def run_testsend(self, use_existing: bool) -> None:
        mode = "复用最新报告" if use_existing else "实时抓取"
        self.logger.log(f"开始执行 testsend，模式: {mode}")
        report = self.reporter.run_testsend(use_existing=use_existing)
        self.logger.log(f"testsend 已发送 source={report['source']} articles={report['article_count']}")

    def _should_run(self, now: datetime) -> bool:
        today = now.strftime("%Y-%m-%d")
        if self.last_run_date == today:
            return False
        return now.time() >= self.scrape_time

    def _load_last_run_date(self) -> str:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            return ""
        try:
            content = json.loads(self.state_path.read_text(encoding="utf-8"))
            return str(content.get("last_run_date", ""))
        except Exception:
            return ""

    def _save_last_run_date(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps({"last_run_date": self.last_run_date}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _parse_scrape_time(value: str) -> dt_time:
        try:
            return datetime.strptime(value.strip(), "%H:%M").time()
        except ValueError as exc:
            raise ValueError(f"SCRAPE_TIME 配置无效，应为 HH:MM，例如 19:00。当前值: {value}") from exc


def main() -> None:
    service = DailySchedulerService()
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        if command == "testsend":
            service.run_testsend(use_existing=True)
            return
        if command == "testsend-live":
            service.run_testsend(use_existing=False)
            return
    service.run_forever()


if __name__ == "__main__":
    main()
