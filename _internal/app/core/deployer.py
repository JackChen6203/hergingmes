"""
Deployment orchestrator.

全流程編排：環境檢查 → HF 登入 → 建立 Space → 匯入 Codex 授權 → 上傳 → 重啟。
每個步驟帶有名稱、狀態、回呼，可以從失敗步驟重新開始。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.config import DeployConfig
from app.core import environment, hf_ops, hermes_ops, space_builder


class StepStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DeployStep:
    """部署流程中的一個步驟."""

    name: str
    description: str
    status: StepStatus = StepStatus.PENDING
    error: Optional[str] = None


# ── 部署步驟定義 ──────────────────────────────────────────────

STEP_NAMES = [
    "check_env",
    "install_deps",
    "hf_login",
    "create_space",
    "codex_oauth",
    "check_auth",
    "generate_files",
    "upload_secrets",
    "upload_space",
    "restart_space",
]

STEP_INFO = {
    "check_env":      ("🔍 檢查環境", "確認 Python、CLI 工具都正常"),
    "install_deps":   ("📦 安裝依賴", "安裝 huggingface_hub"),
    "hf_login":       ("🔑 HF 登入", "用 Token 登入 Hugging Face"),
    "create_space":   ("🏗️ 建立 Space", "在 Hugging Face 建立 Docker Space"),
    "codex_oauth":    ("🌐 匯入 OpenAI 授權", "使用本機 Codex/OpenAI auth.json"),
    "check_auth":     ("📋 檢查授權", "確認 auth.json 存在"),
    "generate_files": ("📝 產生檔案", "產生 Space 專案檔案"),
    "upload_secrets": ("🔒 上傳密鑰", "上傳 Secrets 和 Variables"),
    "upload_space":   ("☁️ 上傳 Space", "上傳專案檔案到 HF"),
    "restart_space":  ("🔄 重啟 Space", "重啟 Hugging Face Space"),
}


class Deployer:
    """
    全流程部署編排器.

    提供回呼介面讓 UI 層可以追蹤進度。
    """

    def __init__(
        self,
        cfg: DeployConfig,
        log: Callable[[str], None],
        on_step_change: Optional[Callable[[str, StepStatus], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
        ask_user_to_complete_oauth: Optional[Callable[[], None]] = None,
    ):
        self.cfg = cfg
        self.log = log
        self.on_step_change = on_step_change or (lambda *_: None)
        self.on_progress = on_progress or (lambda *_: None)
        self.ask_user_to_complete_oauth = ask_user_to_complete_oauth or (lambda: None)

        self.steps: list[DeployStep] = []
        for name in STEP_NAMES:
            title, desc = STEP_INFO[name]
            self.steps.append(DeployStep(name=name, description=desc))

    def run_full_deploy(self) -> bool:
        """
        執行完整部署流程。回傳 True 表示成功。

        每個步驟會更新狀態並呼叫回呼。
        失敗時會停在當前步驟。
        """
        total = len(self.steps)

        for idx, step in enumerate(self.steps):
            title, _ = STEP_INFO[step.name]
            self.log(f"\n{'='*50}")
            self.log(f"[{idx+1}/{total}] {title}")
            self.log(f"{'='*50}")

            step.status = StepStatus.RUNNING
            self.on_step_change(step.name, StepStatus.RUNNING)
            self.on_progress(idx, total)

            try:
                self._execute_step(step.name)
                step.status = StepStatus.SUCCESS
                self.on_step_change(step.name, StepStatus.SUCCESS)
                self.log(f"  → 完成 ✅")
            except Exception as exc:
                step.status = StepStatus.FAILED
                step.error = str(exc)
                self.on_step_change(step.name, StepStatus.FAILED)
                self.log(f"  → 失敗 ❌: {exc}")
                return False

        self.on_progress(total, total)
        return True

    def _execute_step(self, step_name: str) -> None:
        """根據步驟名稱執行對應操作."""
        cfg = self.cfg

        if step_name == "check_env":
            environment.check_environment(cfg.hermes_auth_path, cfg.codex_auth_path, self.log)

        elif step_name == "install_deps":
            try:
                import huggingface_hub  # type: ignore  # noqa: F401
                self.log("  huggingface_hub 已安裝，跳過")
            except ImportError:
                hermes_ops.install_hf_hub(self.log)

        elif step_name == "hf_login":
            hf_ops.hf_login(cfg.hf_token, self.log)

        elif step_name == "create_space":
            hf_ops.create_space(cfg, self.log)

        elif step_name == "codex_oauth":
            if not hermes_ops.import_codex_auth(
                cfg.hermes_auth_path, cfg.codex_auth_path, self.log
            ):
                raise FileNotFoundError(
                    f"找不到可匯入的 Codex auth.json：{cfg.codex_auth_path}\n"
                    "請先用 Codex CLI 或既有 Codex/OpenAI 登入工具完成登入，"
                    "讓本機產生 ~/.codex/auth.json，再重新部署。"
                )

        elif step_name == "check_auth":
            hermes_ok, _ = hermes_ops.check_auth_files(
                cfg.hermes_auth_path, cfg.codex_auth_path, self.log
            )
            if not hermes_ok:
                raise FileNotFoundError("Hermes auth.json 不存在，無法繼續。")

        elif step_name == "generate_files":
            space_builder.generate_space_files(cfg, self.log)

        elif step_name == "upload_secrets":
            hf_ops.upload_secrets_and_variables(cfg, self.log)

        elif step_name == "upload_space":
            hf_ops.upload_space_files(cfg, self.log)

        elif step_name == "restart_space":
            hf_ops.restart_space(cfg, self.log)

        else:
            raise ValueError(f"未知步驟: {step_name}")
