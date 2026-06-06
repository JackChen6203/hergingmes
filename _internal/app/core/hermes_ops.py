"""
Hermes Agent operations.

安裝 Hermes Agent、啟動 OAuth 登入流程。
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
from typing import Callable, Optional

from app.config import HERMES_AGENT_PIP_URL
from app.core.environment import find_hermes_cli


def find_codex_cli() -> Optional[str]:
    """Find Codex CLI from PATH and common npm global install locations."""
    found = shutil.which("codex")
    if found:
        return found

    appdata = os.environ.get("APPDATA", "")
    candidates = []
    if appdata:
        candidates.append(pathlib.Path(appdata) / "npm" / "codex.cmd")
        candidates.append(pathlib.Path(appdata) / "npm" / "codex")
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def install_hf_hub(log: Callable[[str], None]) -> None:
    """安裝或更新 huggingface_hub."""
    log("  安裝/更新 huggingface_hub...")
    cmd = [sys.executable, "-m", "pip", "install", "-U", "huggingface_hub>=0.33,<2"]
    _run_subprocess(cmd, log=log)
    log("  ✅ huggingface_hub 安裝完成")


def install_hermes_agent(log: Callable[[str], None]) -> Optional[str]:
    """安裝或更新 Hermes Agent，回傳 CLI 路徑."""
    if sys.version_info < (3, 11):
        raise RuntimeError(
            "目前桌面工具的 .venv 使用 Python "
            f"{sys.version_info.major}.{sys.version_info.minor}，但 Hermes Agent 需要 Python 3.11 以上。\n"
            "請關閉本程式後重新執行「先點我_一鍵啟動.bat」，它會自動安裝 Python 3.12 並重建 .venv。"
        )
    log("  安裝 Hermes Agent（只影響本工具的 .venv）...")
    cmd = [sys.executable, "-m", "pip", "install", "--no-cache-dir", "-U", HERMES_AGENT_PIP_URL]
    env = _short_pip_temp_env(log)
    _run_subprocess(cmd, log=log, env=env)
    hermes = find_hermes_cli()
    if hermes:
        log(f"  ✅ Hermes Agent 安裝完成: {hermes}")
    else:
        log("  ⚠️ 安裝後仍找不到 hermes CLI")
    return hermes


def _short_pip_temp_env(log: Callable[[str], None]) -> dict[str, str]:
    """Use a short temp path so pip can unpack Hermes' deep website paths on Windows."""
    env = os.environ.copy()
    if os.name != "nt":
        return env

    root = pathlib.Path(env.get("SystemDrive", "C:") + "\\hm_pip_tmp")
    cache = root / "cache"
    root.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    env["TMP"] = str(root)
    env["TEMP"] = str(root)
    env["PIP_CACHE_DIR"] = str(cache)
    log(f"  使用短暫存目錄避免 Windows 長路徑問題: {root}")
    return env


def open_hermes_codex_login(log: Callable[[str], None]) -> None:
    """開啟 Hermes openai-codex 登入流程（新視窗）."""
    hermes = find_hermes_cli()
    if not hermes:
        log("  找不到 hermes CLI，嘗試先安裝...")
        hermes = install_hermes_agent(log)

    if not hermes:
        raise RuntimeError("找不到 hermes CLI。請檢查安裝輸出。")

    log("  開啟 Hermes OpenAI/Codex 登入視窗...")
    if os.name == "nt":
        hermes_escaped = hermes.replace("'", "''")
        ps_cmd = (
            f"Write-Host '正在執行: hermes auth add openai-codex'; "
            f"& '{hermes_escaped}' auth add openai-codex; "
            "Write-Host ''; "
            "Write-Host '授權完成後，請回到主程式按 OK'; "
            "Pause"
        )
        subprocess.Popen(
            ["powershell", "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd]
        )
    elif sys.platform == "darwin":
        # Launch AppleScript to open a new macOS Terminal window running hermes login
        escaped_cmd = f"'{hermes}' auth add openai-codex"
        applescript = f'tell application "Terminal" to do script "{escaped_cmd}"'
        subprocess.Popen(["osascript", "-e", applescript])
    else:
        subprocess.Popen([hermes, "auth", "add", "openai-codex"])

    log("  ✅ 登入視窗已開啟。請在瀏覽器完成授權。")


def install_codex_cli(log: Callable[[str], None]) -> Optional[str]:
    """Install OpenAI Codex CLI with npm when it is not already available."""
    codex = find_codex_cli()
    if codex:
        log(f"  OK Codex CLI 已存在: {codex}")
        return codex

    npm = shutil.which("npm")
    if not npm:
        log("  ERROR 找不到 npm，無法自動安裝 Codex CLI。")
        log("  請先安裝 Node.js LTS：https://nodejs.org/")
        return None

    log("  安裝 OpenAI Codex CLI（npm 全域安裝）...")
    _run_subprocess([npm, "install", "-g", "@openai/codex"], log=log)
    codex = find_codex_cli()
    if codex:
        log(f"  OK Codex CLI 安裝完成: {codex}")
    else:
        log("  ⚠️ 安裝後仍找不到 codex CLI，請重新開啟程式或確認 npm global PATH。")
    return codex


def open_codex_login(log: Callable[[str], None]) -> None:
    """Open Codex CLI login flow; produces ~/.codex/auth.json."""
    codex = install_codex_cli(log)
    if not codex:
        raise RuntimeError("找不到 Codex CLI，且自動安裝失敗。")

    log("  開啟 Codex 登入視窗...")
    if os.name == "nt":
        codex_escaped = codex.replace("'", "''")
        ps_cmd = (
            f"Write-Host '正在執行: codex login'; "
            f"& '{codex_escaped}' login; "
            "Write-Host ''; "
            "Write-Host '登入完成後，請回到主程式按「偵測/匯入 Codex 授權」'; "
            "Pause"
        )
        subprocess.Popen(
            ["powershell", "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd]
        )
    elif sys.platform == "darwin":
        escaped_cmd = f"'{codex}' login"
        applescript = f'tell application "Terminal" to do script "{escaped_cmd}"'
        subprocess.Popen(["osascript", "-e", applescript])
    else:
        subprocess.Popen([codex, "login"])

    log("  OK Codex 登入視窗已開啟。完成後會產生 ~/.codex/auth.json。")


def import_codex_auth(
    hermes_auth_path: pathlib.Path,
    codex_auth_path: pathlib.Path,
    log: Callable[[str], None],
) -> bool:
    """Import an existing Codex CLI auth.json into Hermes' auth path."""
    if not codex_auth_path.exists():
        log(f"  ERROR 找不到 Codex auth.json: {codex_auth_path}")
        log("  請先在本機完成 Codex/OpenAI 登入，產生 ~/.codex/auth.json 後再匯入。")
        return False

    hermes_auth_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(codex_auth_path, hermes_auth_path)
    size = hermes_auth_path.stat().st_size
    log(f"  OK 已匯入 Codex auth -> 部署用 Hermes auth: {hermes_auth_path} ({size} bytes)")
    return True


def check_auth_files(
    hermes_auth_path: pathlib.Path,
    codex_auth_path: pathlib.Path,
    log: Callable[[str], None],
) -> tuple[bool, bool]:
    """檢查授權檔案是否存在，回傳 (hermes_ok, codex_ok)."""
    if codex_auth_path.exists() and not hermes_auth_path.exists():
        try:
            hermes_auth_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(codex_auth_path, hermes_auth_path)
            log(f"  💡 偵測到 Codex auth.json，已自動複製至 Hermes: {hermes_auth_path}")
        except Exception as e:
            log(f"  ⚠️ 無法複製 auth.json: {e}")

    hermes_ok = hermes_auth_path.exists()
    codex_ok = codex_auth_path.exists()

    if hermes_ok:
        size = hermes_auth_path.stat().st_size
        log(f"  ✅ Hermes auth.json ({size} bytes)")
    else:
        log(f"  ❌ Hermes auth.json 不存在: {hermes_auth_path}")

    if codex_ok:
        log(f"  ✅ Codex auth.json 存在")
    else:
        log(f"  ⚪ Codex auth.json 不存在（可選）")

    return hermes_ok, codex_ok


def _run_subprocess(
    cmd: list[str],
    log: Callable[[str], None],
    cwd: Optional[pathlib.Path] = None,
    env: Optional[dict[str, str]] = None,
) -> None:
    """執行子程序並串流輸出到 log."""
    log("  $ " + " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    assert proc.stdout is not None
    tail: list[str] = []
    for line in proc.stdout:
        stripped = line.rstrip()
        if stripped:
            tail.append(stripped)
            tail = tail[-12:]
            log(f"    {stripped}")
    code = proc.wait()
    if code != 0:
        detail = "\n".join(tail)
        if detail:
            raise RuntimeError(f"命令失敗，exit code={code}\n\n最後輸出：\n{detail}")
        raise RuntimeError(f"命令失敗，exit code={code}")
