"""
Environment checking utilities.

檢查 Python、hermes CLI、codex CLI、huggingface_hub 等工具是否存在。
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sys
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class EnvReport:
    """環境檢查報告."""

    python_version: str = ""
    python_path: str = ""
    os_name: str = ""
    hf_cli: str = "未找到"
    hermes_cli: str = "未找到"
    codex_cli: str = "未找到"
    hf_hub_version: str = "未安裝"
    hermes_auth_exists: bool = False
    codex_auth_exists: bool = False


def find_hermes_cli() -> Optional[str]:
    """嘗試在 PATH 及 Python Scripts 資料夾找到 hermes CLI."""
    found = shutil.which("hermes")
    if found:
        return found

    scripts_dir = pathlib.Path(sys.executable).parent
    candidates = [
        scripts_dir / ("hermes.exe" if os.name == "nt" else "hermes"),
        scripts_dir / "hermes",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def check_environment(
    hermes_auth_path: pathlib.Path,
    codex_auth_path: pathlib.Path,
    log: Callable[[str], None],
) -> EnvReport:
    """執行完整環境檢查並回傳報告."""
    report = EnvReport()

    report.python_version = sys.version.split()[0]
    report.python_path = sys.executable
    report.os_name = os.name

    log(f"  Python: {report.python_version}")
    log(f"  路徑: {report.python_path}")
    log(f"  OS: {report.os_name}")

    # HF CLI
    hf_guess = pathlib.Path.home() / ".local" / "bin" / "hf.exe"
    hf_exe = shutil.which("hf") or (str(hf_guess) if hf_guess.exists() else None)
    if hf_exe:
        report.hf_cli = hf_exe
    log(f"  hf CLI: {report.hf_cli}")

    # Hermes CLI
    hermes = find_hermes_cli()
    if hermes:
        report.hermes_cli = hermes
    log(f"  hermes CLI: {report.hermes_cli}")

    # Codex CLI
    codex = shutil.which("codex")
    if codex:
        report.codex_cli = codex
    log(f"  codex CLI: {report.codex_cli}")

    # huggingface_hub
    try:
        import huggingface_hub  # type: ignore

        report.hf_hub_version = huggingface_hub.__version__
    except Exception:
        pass
    log(f"  huggingface_hub: {report.hf_hub_version}")

    # Auth files
    report.hermes_auth_exists = hermes_auth_path.exists()
    report.codex_auth_exists = codex_auth_path.exists()
    log(f"  Hermes auth: {'✅ 存在' if report.hermes_auth_exists else '❌ 不存在'}")
    log(f"  Codex auth: {'✅ 存在' if report.codex_auth_exists else '⚪ 不存在（可選）'}")

    return report
