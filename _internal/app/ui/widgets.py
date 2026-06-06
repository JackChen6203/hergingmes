"""
Custom UI widgets.

自訂元件：步驟追蹤器、深色 Log 面板等。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.ui.theme import Colors, Fonts
from app.core.deployer import StepStatus, STEP_INFO, STEP_NAMES


class StepTracker(tk.Frame):
    """
    步驟追蹤器元件.

    顯示所有部署步驟，並以 emoji 標示目前狀態。
    """

    STATUS_ICONS = {
        StepStatus.PENDING: "⚪",
        StepStatus.RUNNING: "⏳",
        StepStatus.SUCCESS: "✅",
        StepStatus.FAILED: "❌",
        StepStatus.SKIPPED: "⏭️",
    }

    STATUS_STYLES = {
        StepStatus.PENDING: "StatusPending.TLabel",
        StepStatus.RUNNING: "StatusRunning.TLabel",
        StepStatus.SUCCESS: "StatusSuccess.TLabel",
        StepStatus.FAILED: "StatusError.TLabel",
        StepStatus.SKIPPED: "StatusPending.TLabel",
    }

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=Colors.BG_CARD, **kwargs)
        self._labels: dict[str, ttk.Label] = {}
        self._build()

    def _build(self):
        for idx, name in enumerate(STEP_NAMES):
            title, _ = STEP_INFO[name]
            icon = self.STATUS_ICONS[StepStatus.PENDING]

            label = ttk.Label(
                self,
                text=f"  {icon}  {title}",
                style="StatusPending.TLabel",
                anchor="w",
            )
            label.pack(fill="x", padx=8, pady=2)
            self._labels[name] = label

    def update_step(self, step_name: str, status: StepStatus):
        """更新指定步驟的狀態."""
        if step_name not in self._labels:
            return

        title, _ = STEP_INFO[step_name]
        icon = self.STATUS_ICONS.get(status, "⚪")
        style = self.STATUS_STYLES.get(status, "StatusPending.TLabel")

        label = self._labels[step_name]
        label.configure(text=f"  {icon}  {title}", style=style)

    def reset_all(self):
        """重置所有步驟為 PENDING."""
        for name in STEP_NAMES:
            self.update_step(name, StepStatus.PENDING)


class DarkLogPanel(tk.Frame):
    """
    深色 Log 面板.

    帶 Scrollbar 的文字面板，適合顯示部署過程的 log。
    """

    def __init__(self, parent, height: int = 14, **kwargs):
        super().__init__(parent, bg=Colors.BG_DARK, **kwargs)

        self.text = tk.Text(
            self,
            wrap="word",
            height=height,
            bg=Colors.BG_INPUT,
            fg=Colors.TEXT_PRIMARY,
            insertbackground=Colors.TEXT_PRIMARY,
            font=(Fonts.FAMILY_MONO[0], Fonts.SIZE_LOG),
            relief="flat",
            borderwidth=8,
            selectbackground=Colors.ACCENT_BLUE,
            selectforeground="#ffffff",
            state="disabled",
        )
        self.text.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(self, command=self.text.yview, style="Vertical.TScrollbar")
        scroll.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=scroll.set)

        # 文字顏色標記
        self.text.tag_configure("success", foreground=Colors.STATUS_SUCCESS)
        self.text.tag_configure("error", foreground=Colors.STATUS_ERROR)
        self.text.tag_configure("warning", foreground=Colors.STATUS_WARNING)
        self.text.tag_configure("info", foreground=Colors.ACCENT_BLUE)
        self.text.tag_configure("header", foreground=Colors.ACCENT_PURPLE, font=(Fonts.FAMILY_MONO[0], Fonts.SIZE_LOG, "bold"))

    def append(self, message: str) -> None:
        """新增一行 log，自動上色."""
        self.text.configure(state="normal")

        # 根據內容自動選擇顏色標記
        tag = None
        if "✅" in message or "成功" in message or "完成" in message:
            tag = "success"
        elif "❌" in message or "失敗" in message or "ERROR" in message:
            tag = "error"
        elif "⚠️" in message or "WARNING" in message:
            tag = "warning"
        elif message.startswith("===") or message.startswith("  →"):
            tag = "header"
        elif message.startswith("["):
            tag = "info"

        if tag:
            self.text.insert("end", message.rstrip() + "\n", tag)
        else:
            self.text.insert("end", message.rstrip() + "\n")

        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self) -> None:
        """清空 log."""
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


class TokenEntry(tk.Frame):
    """
    Token 輸入元件.

    帶有顯示/隱藏切換的密碼輸入框。
    """

    def __init__(self, parent, textvariable: tk.StringVar, **kwargs):
        super().__init__(parent, bg=Colors.BG_CARD, **kwargs)

        self._var = textvariable
        self._show_password = False

        self.entry = tk.Entry(
            self,
            textvariable=textvariable,
            show="•",
            bg=Colors.BG_INPUT,
            fg=Colors.TEXT_PRIMARY,
            insertbackground=Colors.TEXT_PRIMARY,
            font=(Fonts.FAMILY[0], Fonts.SIZE_BODY),
            relief="flat",
            borderwidth=6,
            selectbackground=Colors.ACCENT_BLUE,
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.toggle_btn = tk.Button(
            self,
            text="👁",
            command=self._toggle_show,
            bg=Colors.BTN_SECONDARY,
            fg=Colors.TEXT_PRIMARY,
            font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL),
            relief="flat",
            borderwidth=0,
            activebackground=Colors.BTN_SECONDARY_HOVER,
            cursor="hand2",
            width=3,
        )
        self.toggle_btn.pack(side="right")

    def _toggle_show(self):
        self._show_password = not self._show_password
        self.entry.configure(show="" if self._show_password else "•")
        self.toggle_btn.configure(text="🔒" if self._show_password else "👁")
