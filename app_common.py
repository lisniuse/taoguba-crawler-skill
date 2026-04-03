#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
LOG_RETENTION_DAYS = 30


def load_env_file(env_path: Path | None = None) -> None:
    target = env_path or (PROJECT_ROOT / ".env")
    if target.exists():
        for raw_line in target.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    apply_proxy_env()


def apply_proxy_env() -> None:
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        value = os.getenv(key, "").strip()
        if value:
            os.environ[key] = normalize_proxy_url(value)


def normalize_proxy_url(value: str) -> str:
    if "://" in value:
        return value
    return f"http://{value}"


def decode_output(data: bytes) -> str:
    if not data:
        return ""
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


class NotificationClient:
    def __init__(self, exe_path: str, channel: str) -> None:
        self._exe_path = exe_path.strip()
        self._channel = channel.strip() or "feishu"
        self.last_error = ""

    @property
    def enabled(self) -> bool:
        return bool(self._exe_path)

    def send(self, message: str) -> bool:
        if not self._exe_path:
            self.last_error = "PICOCLAW_EXE 未配置"
            return False
        temp_path: str | None = None
        try:
            command = [self._exe_path, "send", "--channel", self._channel]
            if "\n" in message:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
                    f.write(message)
                    temp_path = f.name
                command.extend(["--message-file", temp_path])
            else:
                command.extend(["--message", message])
            result = subprocess.run(command, timeout=30, check=False, capture_output=True)
            self.last_error = (decode_output(result.stderr) or decode_output(result.stdout)).strip()
            return result.returncode == 0
        except Exception as exc:
            self.last_error = str(exc)
            return False
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass


class DailyLogger:
    def __init__(self, directory: Path, prefix: str) -> None:
        self._directory = directory
        self._prefix = prefix

    def log(self, message: str) -> None:
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(line)
        self._cleanup()
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{self._prefix}-{datetime.now().strftime('%Y%m%d')}.log"
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _cleanup(self) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        cutoff = (datetime.now().date() - timedelta(days=LOG_RETENTION_DAYS)).strftime("%Y%m%d")
        for path in self._directory.glob(f"{self._prefix}-*.log"):
            suffix = path.stem.rsplit("-", 1)[-1]
            if len(suffix) == 8 and suffix.isdigit() and suffix < cutoff:
                try:
                    path.unlink()
                except OSError:
                    pass
