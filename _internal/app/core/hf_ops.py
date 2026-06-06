"""
Hugging Face operations.

HF 登入、建立 Space、上傳 Secrets/Variables、上傳檔案、重啟 Space。
"""

from __future__ import annotations

import base64
import pathlib
from typing import Callable

from app.config import DeployConfig


class HfOpsError(RuntimeError):
    """HF 操作錯誤."""


def _import_hf():
    """延遲 import huggingface_hub，避免啟動時就需要安裝."""
    try:
        from huggingface_hub import HfApi, login, whoami  # type: ignore

        return HfApi, login, whoami
    except ImportError as exc:
        raise HfOpsError(
            "找不到 huggingface_hub。請先按『安裝/更新 huggingface_hub』。"
        ) from exc


def hf_login(token: str, log: Callable[[str], None]) -> str:
    """登入 Hugging Face，回傳使用者名稱."""
    _, login_fn, whoami_fn = _import_hf()
    if not token:
        raise HfOpsError("請先貼上 Hugging Face Write Token。")
    log("  正在登入 Hugging Face...")
    login_fn(token=token, add_to_git_credential=False)
    info = whoami_fn(token=token)
    username = info.get("name", str(info))
    log(f"  ✅ 登入成功：{username}")
    return username


def hf_whoami(token: str | None, log: Callable[[str], None]) -> dict:
    """取得目前登入者資訊."""
    _, _, whoami_fn = _import_hf()
    info = whoami_fn(token=token or None)
    log(f"  HF whoami: {info}")
    return info


def create_space(cfg: DeployConfig, log: Callable[[str], None]) -> str:
    """建立或確認 HF Space 存在，回傳 Space URL."""
    HfApi, _, _ = _import_hf()
    api = HfApi(token=cfg.hf_token or None)
    log(f"  建立/確認 Space: {cfg.repo_id}")
    url = api.create_repo(
        repo_id=cfg.repo_id,
        repo_type="space",
        space_sdk="docker",
        private=cfg.private,
        exist_ok=True,
    )
    log(f"  ✅ Space 已就緒: {url}")
    return str(url)


def upload_secrets_and_variables(cfg: DeployConfig, log: Callable[[str], None]) -> None:
    """上傳 Secrets 和 Variables 到 HF Space."""
    HfApi, _, _ = _import_hf()
    api = HfApi(token=cfg.hf_token or None)

    if not cfg.hermes_auth_path.exists():
        raise FileNotFoundError(f"找不到 Hermes auth.json：{cfg.hermes_auth_path}")

    hermes_b64 = base64.b64encode(cfg.hermes_auth_path.read_bytes()).decode("ascii")
    log("  上傳 HERMES_AUTH_JSON_B64...")
    api.add_space_secret(repo_id=cfg.repo_id, key="HERMES_AUTH_JSON_B64", value=hermes_b64)

    if cfg.include_codex_auth:
        if not cfg.codex_auth_path.exists():
            if cfg.provider == "openai-codex":
                raise FileNotFoundError(
                    f"找不到 Codex auth.json：{cfg.codex_auth_path}\n"
                    "請先在主畫面點擊『安裝/登入 Codex』完成登入，"
                    "再點『偵測/匯入 Codex 授權』。"
                )
            else:
                log("  ⚠️ 提示：未偵測到本地 Codex 授權檔，但由於您未選用 openai-codex 提供商，已自動跳過上傳。")
        else:
            codex_b64 = base64.b64encode(cfg.codex_auth_path.read_bytes()).decode("ascii")
            log("  上傳 CODEX_AUTH_JSON_B64...")
            api.add_space_secret(repo_id=cfg.repo_id, key="CODEX_AUTH_JSON_B64", value=codex_b64)

    log("  設定 Space Variables...")
    api.add_space_variable(repo_id=cfg.repo_id, key="HERMES_PROVIDER", value=cfg.provider)
    api.add_space_variable(repo_id=cfg.repo_id, key="HERMES_INFERENCE_PROVIDER", value=cfg.provider)
    api.add_space_variable(repo_id=cfg.repo_id, key="HERMES_MODEL", value=cfg.model)
    api.add_space_variable(repo_id=cfg.repo_id, key="HERMES_CONTEXT_LENGTH", value="1000000")

    # 設定使用者自訂的 GATEWAY_TOKEN 登入密碼
    log("  上傳 GATEWAY_TOKEN Secret...")
    api.add_space_secret(repo_id=cfg.repo_id, key="GATEWAY_TOKEN", value=cfg.gateway_token or "admin123")

    if cfg.hf_token:
        log("  上傳 HF_TOKEN Secret 以啟用備份與持久化機制...")
        api.add_space_secret(repo_id=cfg.repo_id, key="HF_TOKEN", value=cfg.hf_token)

    # 上傳外部整合機敏資訊至環境變數 (Secrets)
    if cfg.tg_token:
        log("  上傳 TG_BOT_TOKEN 和 TELEGRAM_BOT_TOKEN...")
        api.add_space_secret(repo_id=cfg.repo_id, key="TG_BOT_TOKEN", value=cfg.tg_token)
        api.add_space_secret(repo_id=cfg.repo_id, key="TELEGRAM_BOT_TOKEN", value=cfg.tg_token)
        log("  設定 TELEGRAM_MODE=polling（private Space 使用 outbound 輪詢較穩定）")
        api.add_space_variable(repo_id=cfg.repo_id, key="TELEGRAM_MODE", value="polling")
        
    if cfg.telegram_proxy:
        log("  上傳 TELEGRAM_PROXY...")
        api.add_space_secret(repo_id=cfg.repo_id, key="TELEGRAM_PROXY", value=cfg.telegram_proxy)
        
    if cfg.telegram_base_url:
        log("  上傳 TELEGRAM_BASE_URL...")
        api.add_space_secret(repo_id=cfg.repo_id, key="TELEGRAM_BASE_URL", value=cfg.telegram_base_url)

    if cfg.telegram_allowed_users:
        log(f"  上傳 TELEGRAM_ALLOWED_USERS: {cfg.telegram_allowed_users}")
        api.add_space_variable(repo_id=cfg.repo_id, key="TELEGRAM_ALLOWED_USERS", value=cfg.telegram_allowed_users)
        api.add_space_variable(repo_id=cfg.repo_id, key="TELEGRAM_ALLOWED_CHATS", value=cfg.telegram_allowed_users)

    if cfg.cloudflare_workers_token:
        log("  上傳 CLOUDFLARE_WORKERS_TOKEN...")
        api.add_space_secret(repo_id=cfg.repo_id, key="CLOUDFLARE_WORKERS_TOKEN", value=cfg.cloudflare_workers_token)

    if cfg.cloudflare_proxy_url:
        log("  上傳 CLOUDFLARE_PROXY_URL...")
        api.add_space_secret(repo_id=cfg.repo_id, key="CLOUDFLARE_PROXY_URL", value=cfg.cloudflare_proxy_url)
        
        # 嘗試自動獲取與 Bot 互動的使用者 Chat ID 作為白名單
        try:
            import requests
            req_url = f"https://api.telegram.org/bot{cfg.tg_token}/getUpdates"
            if cfg.telegram_base_url:
                req_url = f"{cfg.telegram_base_url.rstrip('/')}/bot{cfg.tg_token}/getUpdates"
            r = requests.get(req_url, timeout=10).json()
            if r.get("ok"):
                chat_ids = {str(u["message"]["chat"]["id"]) for u in r.get("result", []) if "message" in u and "chat" in u["message"]}
                if chat_ids:
                    allowed_chats = ",".join(chat_ids)
                    log(f"  偵測到 Telegram 互動 Chat ID: {allowed_chats}，自動設定為安全白名單")
                    api.add_space_variable(repo_id=cfg.repo_id, key="TELEGRAM_ALLOWED_CHATS", value=allowed_chats)
                    api.add_space_variable(repo_id=cfg.repo_id, key="TELEGRAM_ALLOWED_USERS", value=allowed_chats)
                else:
                    log("  ⚠️ 提示：未偵測到任何與 Telegram Bot 的近期對話紀錄，建議部署後在 Telegram 對 Bot 發送任意訊息以啟用服務。")
        except Exception as e:
            log(f"  ⚠️ 無法自動取得 Telegram 互動 Chat ID: {e}")
    if cfg.discord_token:
        log("  上傳 DISCORD_BOT_TOKEN...")
        api.add_space_secret(repo_id=cfg.repo_id, key="DISCORD_BOT_TOKEN", value=cfg.discord_token)
    if cfg.discord_webhook_url:
        log("  上傳 DISCORD_WEBHOOK_URL...")
        api.add_space_variable(repo_id=cfg.repo_id, key="DISCORD_WEBHOOK_URL", value=cfg.discord_webhook_url)
    if cfg.discord_allowed_users:
        log(f"  上傳 DISCORD_ALLOWED_USERS: {cfg.discord_allowed_users}")
        api.add_space_variable(repo_id=cfg.repo_id, key="DISCORD_ALLOWED_USERS", value=cfg.discord_allowed_users)
    if cfg.line_token:
        log("  上傳 LINE_CHANNEL_ACCESS_TOKEN...")
        api.add_space_secret(repo_id=cfg.repo_id, key="LINE_CHANNEL_ACCESS_TOKEN", value=cfg.line_token)
    if cfg.line_secret:
        log("  上傳 LINE_CHANNEL_SECRET...")
        api.add_space_secret(repo_id=cfg.repo_id, key="LINE_CHANNEL_SECRET", value=cfg.line_secret)
    if cfg.notebooklm_cookie:
        log("  上傳 NOTEBOOKLM_COOKIE...")
        api.add_space_secret(repo_id=cfg.repo_id, key="NOTEBOOKLM_COOKIE", value=cfg.notebooklm_cookie)
    if cfg.obsidian_token:
        log("  上傳 OBSIDIAN_API_KEY...")
        api.add_space_secret(repo_id=cfg.repo_id, key="OBSIDIAN_API_KEY", value=cfg.obsidian_token)
    if cfg.obsidian_url:
        log("  設定 OBSIDIAN_API_URL...")
        api.add_space_variable(repo_id=cfg.repo_id, key="OBSIDIAN_API_URL", value=cfg.obsidian_url)
    if cfg.obsidian_email:
        log("  上傳 OBSIDIAN_EMAIL...")
        api.add_space_secret(repo_id=cfg.repo_id, key="OBSIDIAN_EMAIL", value=cfg.obsidian_email)
    if cfg.obsidian_password:
        log("  上傳 OBSIDIAN_PASSWORD...")
        api.add_space_secret(repo_id=cfg.repo_id, key="OBSIDIAN_PASSWORD", value=cfg.obsidian_password)
    if cfg.obsidian_vault:
        log("  上傳 OBSIDIAN_VAULT...")
        api.add_space_secret(repo_id=cfg.repo_id, key="OBSIDIAN_VAULT", value=cfg.obsidian_vault)
    if cfg.obsidian_passphrase:
        log("  上傳 OBSIDIAN_PASSPHRASE...")
        api.add_space_secret(repo_id=cfg.repo_id, key="OBSIDIAN_PASSPHRASE", value=cfg.obsidian_passphrase)

    log("  ✅ Secrets / Variables 上傳完成")


def upload_space_files(cfg: DeployConfig, log: Callable[[str], None]) -> None:
    """上傳整個 Space 專案資料夾到 HF."""
    HfApi, _, _ = _import_hf()
    if not cfg.project_dir.exists():
        raise FileNotFoundError(f"找不到專案資料夾：{cfg.project_dir}")

    api = HfApi(token=cfg.hf_token or None)
    log(f"  上傳檔案到 {cfg.repo_id}...")
    api.upload_folder(
        repo_id=cfg.repo_id,
        repo_type="space",
        folder_path=str(cfg.project_dir),
        commit_message="Deploy Hermes Agent openai-codex auth Space",
        ignore_patterns=["*.pyc", "__pycache__/*", ".venv/*", "venv/*", ".hf-secrets", "*.log"],
    )
    log("  ✅ 檔案上傳完成")


def restart_space(cfg: DeployConfig, log: Callable[[str], None]) -> None:
    """重啟 HF Space."""
    HfApi, _, _ = _import_hf()
    api = HfApi(token=cfg.hf_token or None)
    log(f"  重啟 Space: {cfg.repo_id}...")
    try:
        api.restart_space(repo_id=cfg.repo_id, factory_reboot=True)
    except Exception:
        try:
            api.restart_space(repo_id=cfg.repo_id)
        except Exception as e:
            log(f"  ⚠️ 重啟呼叫失敗 (通常 Space 已在重啟中，可忽略): {e}")
            return
    log("  ✅ 重啟請求已送出")


def send_deploy_notification(cfg: DeployConfig, log: Callable[[str], None]) -> None:
    """Build 完成後向已設定的通訊軟體發送上線通知。"""
    import urllib.request
    import json as _json

    space_url = cfg.space_url
    msg = (
        f"🚀 Hermes Agent 已成功部署上線！\n\n"
        f"🌐 Space: {space_url}\n"
        f"🤖 Model: {cfg.model}\n"
        f"📡 Provider: {cfg.provider}\n"
        f"🔑 Gateway Token: {cfg.gateway_token}\n\n"
        f"請在瀏覽器開啟上方連結並輸入 Gateway Token 登入。"
    )

    sent_any = False

    # ── Telegram 通知 ──
    if cfg.tg_token:
        try:
            base_url = cfg.telegram_base_url.rstrip('/') if cfg.telegram_base_url else "https://api.telegram.org"
            # 先嘗試取得最近的 chat_id
            updates_url = f"{base_url}/bot{cfg.tg_token}/getUpdates?limit=5"
            req = urllib.request.Request(updates_url, headers={"User-Agent": "HuggingMes-Deployer"})
            resp = urllib.request.urlopen(req, timeout=10)
            data = _json.loads(resp.read().decode())
            chat_ids = set()
            if data.get("ok"):
                for u in data.get("result", []):
                    if "message" in u and "chat" in u["message"]:
                        chat_ids.add(str(u["message"]["chat"]["id"]))
            for chat_id in chat_ids:
                send_url = f"{base_url}/bot{cfg.tg_token}/sendMessage"
                payload = _json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": ""}).encode()
                req = urllib.request.Request(send_url, data=payload,
                    headers={"Content-Type": "application/json", "User-Agent": "HuggingMes-Deployer"})
                urllib.request.urlopen(req, timeout=10)
            if chat_ids:
                log(f"  📱 已透過 Telegram 發送上線通知到 {len(chat_ids)} 個聊天")
                sent_any = True
            else:
                log("  ⚠️ Telegram: 未找到近期對話，無法發送通知（請先對 Bot 發送訊息）")
        except Exception as e:
            log(f"  ⚠️ Telegram 通知發送失敗: {e}")

    # ── Discord 通知 ──
    if cfg.discord_token:
        log("  💬 Discord 通知：需要透過 Bot 在 Space 內部完成連線，已跳過本地發送。")

    # ── LINE 通知 ──
    if cfg.line_token:
        try:
            line_url = "https://api.line.me/v2/bot/message/broadcast"
            line_msg = {
                "messages": [{
                    "type": "text",
                    "text": msg
                }]
            }
            payload = _json.dumps(line_msg).encode()
            req = urllib.request.Request(line_url, data=payload, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg.line_token}",
            })
            urllib.request.urlopen(req, timeout=10)
            log("  📱 已透過 LINE 廣播上線通知")
            sent_any = True
        except Exception as e:
            log(f"  ⚠️ LINE 通知發送失敗: {e}")

    if not sent_any:
        log("  ℹ️ 未偵測到已設定的通訊軟體，跳過上線通知。")
