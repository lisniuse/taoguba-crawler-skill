#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import paramiko

from app_common import load_env_file


PROJECT_ROOT = Path(__file__).resolve().parent
REMOTE_DIR = PurePosixPath("/home/nuonuo/app/taoguba-crawler-skill")
ARCHIVE_NAME = "taoguba-crawler-skill-src.tar.gz"
EXCLUDED_NAMES = {
    ".git",
    ".env",
    "logs",
    "state",
    "output",
    "__pycache__",
    ".pytest_cache",
    ".venv",
}


@dataclass(frozen=True)
class DeployConfig:
    host: str
    user: str
    password: str
    remote_dir: PurePosixPath = REMOTE_DIR

    @classmethod
    def from_env(cls) -> "DeployConfig":
        load_env_file()
        host = os.getenv("UPLOAD_HOST", "").strip()
        user = os.getenv("UPLOAD_USER", "").strip()
        password = os.getenv("UPLOAD_PASSWORD", "").strip()
        if not host or not user or not password:
            raise Exception("请先设置 UPLOAD_HOST、UPLOAD_USER、UPLOAD_PASSWORD。")
        return cls(host=host, user=user, password=password)


class SourceDeployer:
    def __init__(self, config: DeployConfig) -> None:
        self.config = config

    def deploy(self) -> None:
        archive_path = self._build_archive()
        remote_tmp = PurePosixPath("/tmp") / ARCHIVE_NAME
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        print(f"Connecting to {self.config.user}@{self.config.host}...")
        try:
            client.connect(self.config.host, username=self.config.user, password=self.config.password)
            with client.open_sftp() as sftp:
                size = archive_path.stat().st_size
                print(f"Uploading {archive_path.name} ({size / 1024:.1f} KB) -> {remote_tmp}...")
                sftp.put(str(archive_path), remote_tmp.as_posix(), callback=self._progress)
                print()
            self._sudo_exec(client, f"mkdir -p {self.config.remote_dir.as_posix()}")
            self._sudo_exec(client, f"tar -xzf {remote_tmp.as_posix()} -C {self.config.remote_dir.as_posix()}")
            self._exec(client, f"rm -f {remote_tmp.as_posix()}")
            self._sudo_exec(client, f"chown -R nuonuo:nuonuo {self.config.remote_dir.as_posix()}")
            print(f"Done: {self.config.remote_dir.as_posix()}")
        finally:
            client.close()
            archive_path.unlink(missing_ok=True)

    def _build_archive(self) -> Path:
        fd, temp_path = tempfile.mkstemp(prefix="taoguba-crawler-skill-", suffix=".tar.gz")
        os.close(fd)
        archive_path = Path(temp_path)
        with tarfile.open(archive_path, "w:gz") as tar:
            for path in self._iter_source_files():
                tar.add(path, arcname=path.relative_to(PROJECT_ROOT).as_posix())
        return archive_path

    def _iter_source_files(self) -> list[Path]:
        files: list[Path] = []
        for path in PROJECT_ROOT.rglob("*"):
            rel_parts = path.relative_to(PROJECT_ROOT).parts
            if any(part in EXCLUDED_NAMES for part in rel_parts):
                continue
            if path.is_file():
                files.append(path)
        return sorted(files)

    @staticmethod
    def _progress(transferred: int, total: int) -> None:
        print(f"  {transferred / 1024:.1f} / {total / 1024:.1f} KB", end="\r")

    @staticmethod
    def _exec(client: paramiko.SSHClient, command: str) -> str:
        _, stdout, stderr = client.exec_command(command)
        exit_code = stdout.channel.recv_exit_status()
        out_text = stdout.read().decode("utf-8", errors="replace")
        err_text = stderr.read().decode("utf-8", errors="replace")
        if exit_code != 0:
            raise Exception(f"远端命令失败: {command}\n{err_text or out_text}".strip())
        return out_text

    def _sudo_exec(self, client: paramiko.SSHClient, command: str) -> str:
        quoted_password = self.config.password.replace("'", "'\"'\"'")
        return self._exec(client, f"echo '{quoted_password}' | sudo -S {command}")


def main() -> None:
    SourceDeployer(DeployConfig.from_env()).deploy()


if __name__ == "__main__":
    main()
