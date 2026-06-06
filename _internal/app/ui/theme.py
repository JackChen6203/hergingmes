"""
UI Theme system.

深色主題、配色、字體定義。讓小學生看起來很酷。
"""

from __future__ import annotations


# ── 色彩系統 ──────────────────────────────────────────────────

class Colors:
    # 主背景
    BG_DARK = "#1a1b2e"
    BG_CARD = "#232442"
    BG_INPUT = "#2a2b4a"

    # 文字
    TEXT_PRIMARY = "#e8e8f0"
    TEXT_SECONDARY = "#9899b3"
    TEXT_MUTED = "#6b6c88"
    TEXT_TITLE = "#ffffff"

    # 強調色
    ACCENT_BLUE = "#5b8def"
    ACCENT_PURPLE = "#8b5cf6"
    ACCENT_CYAN = "#06d6a0"
    ACCENT_ORANGE = "#ff9f43"
    ACCENT_RED = "#ff6b6b"
    ACCENT_GREEN = "#06d6a0"
    ACCENT_YELLOW = "#f5c542"

    # 漸層按鈕
    BTN_PRIMARY = "#5b8def"
    BTN_PRIMARY_HOVER = "#4a7de0"
    BTN_SECONDARY = "#3a3b5c"
    BTN_SECONDARY_HOVER = "#4a4b6c"

    # 狀態色
    STATUS_SUCCESS = "#06d6a0"
    STATUS_WARNING = "#ff9f43"
    STATUS_ERROR = "#ff6b6b"
    STATUS_RUNNING = "#5b8def"
    STATUS_PENDING = "#4a4b6c"

    # 進度條
    PROGRESS_BG = "#2a2b4a"
    PROGRESS_FILL = "#5b8def"

    # 分隔線
    BORDER = "#3a3b5c"


# ── 字體 ──────────────────────────────────────────────────────

class Fonts:
    # Windows 優先使用 Segoe UI，fallback 到其他常見字體
    FAMILY = ("Segoe UI", "Microsoft JhengHei", "微軟正黑體", "Arial")
    FAMILY_MONO = ("Cascadia Code", "Consolas", "Courier New")

    SIZE_TITLE = 20
    SIZE_SUBTITLE = 14
    SIZE_BODY = 12
    SIZE_SMALL = 10
    SIZE_BUTTON = 13
    SIZE_BUTTON_BIG = 16
    SIZE_LOG = 10


# ── 主題配置到 tkinter ────────────────────────────────────────

def apply_theme(root) -> None:
    """將深色主題套用到 tkinter root."""
    import tkinter as tk
    from tkinter import ttk

    root.configure(bg=Colors.BG_DARK)

    style = ttk.Style(root)

    # 嘗試使用 clam 主題作為基底（支持更多自訂）
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # ── TFrame ──
    style.configure("TFrame", background=Colors.BG_DARK)
    style.configure("Card.TFrame", background=Colors.BG_CARD)

    # ── TLabel ──
    style.configure(
        "TLabel",
        background=Colors.BG_DARK,
        foreground=Colors.TEXT_PRIMARY,
        font=(Fonts.FAMILY[0], Fonts.SIZE_BODY),
    )
    style.configure(
        "Title.TLabel",
        background=Colors.BG_DARK,
        foreground=Colors.TEXT_TITLE,
        font=(Fonts.FAMILY[0], Fonts.SIZE_TITLE, "bold"),
    )
    style.configure(
        "Subtitle.TLabel",
        background=Colors.BG_DARK,
        foreground=Colors.TEXT_SECONDARY,
        font=(Fonts.FAMILY[0], Fonts.SIZE_SUBTITLE),
    )
    style.configure(
        "Muted.TLabel",
        background=Colors.BG_DARK,
        foreground=Colors.TEXT_MUTED,
        font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL),
    )
    style.configure(
        "CardTitle.TLabel",
        background=Colors.BG_CARD,
        foreground=Colors.TEXT_TITLE,
        font=(Fonts.FAMILY[0], Fonts.SIZE_SUBTITLE, "bold"),
    )
    style.configure(
        "CardBody.TLabel",
        background=Colors.BG_CARD,
        foreground=Colors.TEXT_PRIMARY,
        font=(Fonts.FAMILY[0], Fonts.SIZE_BODY),
    )
    style.configure(
        "CardMuted.TLabel",
        background=Colors.BG_CARD,
        foreground=Colors.TEXT_MUTED,
        font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL),
    )

    # Status labels
    for status_name, color in [
        ("Success", Colors.STATUS_SUCCESS),
        ("Error", Colors.STATUS_ERROR),
        ("Warning", Colors.STATUS_WARNING),
        ("Running", Colors.STATUS_RUNNING),
        ("Pending", Colors.TEXT_MUTED),
    ]:
        style.configure(
            f"Status{status_name}.TLabel",
            background=Colors.BG_CARD,
            foreground=color,
            font=(Fonts.FAMILY[0], Fonts.SIZE_BODY),
        )

    # ── TButton ──
    style.configure(
        "TButton",
        background=Colors.BTN_SECONDARY,
        foreground=Colors.TEXT_PRIMARY,
        font=(Fonts.FAMILY[0], Fonts.SIZE_BUTTON),
        padding=(12, 8),
        borderwidth=0,
    )
    style.map(
        "TButton",
        background=[("active", Colors.BTN_SECONDARY_HOVER), ("pressed", Colors.BTN_SECONDARY_HOVER)],
    )

    style.configure(
        "Primary.TButton",
        background=Colors.BTN_PRIMARY,
        foreground="#ffffff",
        font=(Fonts.FAMILY[0], Fonts.SIZE_BUTTON_BIG, "bold"),
        padding=(20, 14),
        borderwidth=0,
    )
    style.map(
        "Primary.TButton",
        background=[("active", Colors.BTN_PRIMARY_HOVER), ("pressed", Colors.BTN_PRIMARY_HOVER)],
    )

    style.configure(
        "Small.TButton",
        background=Colors.BTN_SECONDARY,
        foreground=Colors.ACCENT_BLUE,
        font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL),
        padding=(8, 4),
        borderwidth=0,
    )

    # ── TEntry ──
    style.configure(
        "TEntry",
        fieldbackground=Colors.BG_INPUT,
        foreground=Colors.TEXT_PRIMARY,
        insertcolor=Colors.TEXT_PRIMARY,
        borderwidth=1,
        padding=(8, 6),
    )

    # ── TLabelframe ──
    style.configure(
        "TLabelframe",
        background=Colors.BG_CARD,
        foreground=Colors.TEXT_PRIMARY,
        borderwidth=1,
        relief="flat",
    )
    style.configure(
        "TLabelframe.Label",
        background=Colors.BG_CARD,
        foreground=Colors.ACCENT_BLUE,
        font=(Fonts.FAMILY[0], Fonts.SIZE_BODY, "bold"),
    )

    # ── TCheckbutton ──
    style.configure(
        "TCheckbutton",
        background=Colors.BG_CARD,
        foreground=Colors.TEXT_PRIMARY,
        font=(Fonts.FAMILY[0], Fonts.SIZE_BODY),
    )
    style.map(
        "TCheckbutton",
        background=[("active", Colors.BG_CARD)],
    )

    # ── Horizontal.TProgressbar ──
    style.configure(
        "Horizontal.TProgressbar",
        background=Colors.PROGRESS_FILL,
        troughcolor=Colors.PROGRESS_BG,
        borderwidth=0,
        thickness=8,
    )

    # ── TNotebook ──
    style.configure(
        "TNotebook",
        background=Colors.BG_DARK,
        borderwidth=0,
    )
    style.configure(
        "TNotebook.Tab",
        background=Colors.BTN_SECONDARY,
        foreground=Colors.TEXT_PRIMARY,
        padding=(16, 8),
        font=(Fonts.FAMILY[0], Fonts.SIZE_BODY),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", Colors.ACCENT_BLUE)],
        foreground=[("selected", "#ffffff")],
    )

    # ── Scrollbar ──
    style.configure(
        "Vertical.TScrollbar",
        background=Colors.BG_INPUT,
        troughcolor=Colors.BG_DARK,
        borderwidth=0,
        arrowsize=0,
    )
