"""
Configuration constants and data structures.

所有可調參數與部署設定集中管理。
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field


# ── 應用程式常數 ──────────────────────────────────────────────

APP_TITLE = "Hermes Agent 一鍵部署工具"
APP_VERSION = "7.1.0"

DEFAULT_REPO_ID = "davisc1/hermes-agent-space"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_PROVIDER = "openai-codex"
DEFAULT_CONTEXT_LENGTH = "1000000"

HF_TOKEN_URL = "https://huggingface.co/settings/tokens"
HF_SIGNUP_URL = "https://huggingface.co/join"

# 外部整合申請指引 URL
TG_GUIDE_URL = "https://isite.tw/2016/09/16/16847"
DISCORD_GUIDE_URL = "https://discord.com/developers/applications"
LINE_GUIDE_URL = "https://developers.line.biz/console/"
NOTEBOOKLM_GUIDE_URL = "https://github.com/win4r/notebooklm-py"
OBSIDIAN_GUIDE_URL = "https://github.com/coddingtonbear/obsidian-local-rest-api"
CLOUDFLARE_GUIDE_URL = "https://dash.cloudflare.com/profile/api-tokens"

HERMES_AGENT_PIP_URL = (
    "hermes-agent @ https://github.com/NousResearch/hermes-agent/archive/refs/heads/main.zip"
)

# ── 部署設定 ──────────────────────────────────────────────────


@dataclass
class DeployConfig:
    """使用者填入的部署參數."""

    repo_id: str = DEFAULT_REPO_ID
    project_dir: pathlib.Path = field(
        default_factory=lambda: pathlib.Path.cwd() / "hermes-agent-space"
    )
    model: str = DEFAULT_MODEL
    provider: str = DEFAULT_PROVIDER
    private: bool = True
    hf_token: str = ""
    hermes_auth_path: pathlib.Path = field(
        default_factory=lambda: pathlib.Path.home() / ".hermes" / "auth.json"
    )
    codex_auth_path: pathlib.Path = field(
        default_factory=lambda: pathlib.Path.home() / ".codex" / "auth.json"
    )
    include_codex_auth: bool = True

    # 安全性
    gateway_token: str = "admin123"

    # 外部機器人與工具金鑰
    tg_token: str = ""
    telegram_proxy: str = ""
    telegram_base_url: str = ""
    telegram_allowed_users: str = ""
    cloudflare_workers_token: str = ""
    cloudflare_proxy_url: str = ""
    discord_token: str = ""
    discord_webhook_url: str = ""
    discord_allowed_users: str = ""
    line_token: str = ""
    line_secret: str = ""
    notebooklm_cookie: str = ""
    obsidian_url: str = "http://127.0.0.1:27124"
    obsidian_token: str = ""
    obsidian_email: str = ""
    obsidian_password: str = ""
    obsidian_vault: str = ""
    obsidian_passphrase: str = ""

    def validate(self) -> list[str]:
        """回傳驗證錯誤清單。空代表全部通過。"""
        errors: list[str] = []
        if not self.repo_id or "/" not in self.repo_id or "請點擊驗證" in self.repo_id:
            errors.append("請先點擊『🔍 驗證 Token』以取得並設定正確的 HF Space 名稱 (帳號/專案名)")
        if not self.hf_token:
            errors.append("請貼上 Hugging Face Write Token")
        if not self.cloudflare_workers_token:
            errors.append("請填寫 Cloudflare Workers API Token（必填，用於 Telegram 代理連線）")
        if not self.gateway_token:
            errors.append("請填寫 Gateway Token（登入密碼）")
        return errors

    @property
    def space_url(self) -> str:
        return f"https://huggingface.co/spaces/{self.repo_id}"


