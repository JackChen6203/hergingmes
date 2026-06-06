"""
Main application window - Wizard-style UI.
"""

from __future__ import annotations

import pathlib
import queue
import threading
import webbrowser

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app.config import (
    APP_TITLE, APP_VERSION, DEFAULT_MODEL, DEFAULT_PROVIDER,
    DEFAULT_REPO_ID, HF_SIGNUP_URL, HF_TOKEN_URL, DeployConfig,
)
from app.core.deployer import Deployer, StepStatus
from app.core import environment, hf_ops, hermes_ops, space_builder
from app.ui.theme import Colors, Fonts, apply_theme
from app.ui.widgets import StepTracker, DarkLogPanel, TokenEntry


class AppWindow(tk.Tk):
    """主視窗：精靈式 UI."""

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1100x860")
        self.minsize(960, 740)

        apply_theme(self)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self._deploying = False

        # ── Variables ──
        home = pathlib.Path.home()
        self.repo_id_var = tk.StringVar(value="請點擊驗證token取得使用者名稱(可自定義space名稱)")
        self.project_dir_var = tk.StringVar(value=str(pathlib.Path.cwd() / "hermes-agent-space"))
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.provider_var = tk.StringVar(value=DEFAULT_PROVIDER)
        self.private_var = tk.BooleanVar(value=True)
        self.hf_token_var = tk.StringVar(value="")
        self.hermes_auth_path_var = tk.StringVar(value=str(home / ".hermes" / "auth.json"))
        self.codex_auth_path_var = tk.StringVar(value=str(home / ".codex" / "auth.json"))
        self.include_codex_auth_var = tk.BooleanVar(value=True)

        # 外部整合金鑰變數 (皆不進行任何預填，由使用者手動輸入)
        self.tg_token_var = tk.StringVar(value="")
        self.telegram_proxy_var = tk.StringVar(value="")
        self.telegram_base_url_var = tk.StringVar(value="")
        self.cloudflare_workers_token_var = tk.StringVar(value="")
        self.cloudflare_proxy_url_var = tk.StringVar(value="")
        self.telegram_allowed_users_var = tk.StringVar(value="")
        self.discord_token_var = tk.StringVar(value="")
        self.discord_webhook_url_var = tk.StringVar(value="")
        self.discord_allowed_users_var = tk.StringVar(value="")
        self.line_token_var = tk.StringVar(value="")
        self.line_secret_var = tk.StringVar(value="")
        self.notebooklm_cookie_var = tk.StringVar(value="")
        self.obsidian_url_var = tk.StringVar(value="http://127.0.0.1:27124")  # 容器內部預設存取網址
        self.obsidian_token_var = tk.StringVar(value="")                       # Obsidian API Key
        self.obsidian_email_var = tk.StringVar(value="")
        self.obsidian_password_var = tk.StringVar(value="")
        self.obsidian_vault_var = tk.StringVar(value="")
        self.obsidian_passphrase_var = tk.StringVar(value="")
        self.gateway_token_var = tk.StringVar(value="admin123")

        self._load_tokens()
        self._build_ui()
        self.after(100, self._drain_log_queue)

    # ── UI Construction ──────────────────────────────────────

    def _build_ui(self) -> None:
        outer = tk.Frame(self, bg=Colors.BG_DARK, padx=16, pady=12)
        outer.pack(fill="both", expand=True)

        self._build_header(outer)

        # 1. 建立日誌標題列 (永遠置底顯示)
        self.log_header = tk.Frame(outer, bg=Colors.BG_DARK)
        self.log_header.pack(side="bottom", fill="x", pady=(8, 0))

        tk.Label(self.log_header, text="📝 Log 日誌資訊", bg=Colors.BG_DARK, fg=Colors.TEXT_SECONDARY,
                 font=(Fonts.FAMILY[0], Fonts.SIZE_BODY, "bold")).pack(side="left")

        # 顯示/隱藏與清除按鈕
        tk.Button(self.log_header, text="清除", command=self._clear_log,
                  bg=Colors.BTN_SECONDARY, fg=Colors.TEXT_MUTED, relief="flat",
                  font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL), cursor="hand2").pack(side="right", padx=(4, 0))

        self._log_visible = True
        self.log_toggle_btn = tk.Button(self.log_header, text="👁️ 隱藏日誌", command=self._toggle_log,
                  bg=Colors.BTN_SECONDARY, fg=Colors.TEXT_MUTED, relief="flat",
                  font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL), cursor="hand2")
        self.log_toggle_btn.pack(side="right")

        # 2. 建立垂直分欄器 (PanedWindow) 以供使用者縮放 log 視窗，並用 BORDER 顏色高亮分隔線
        self.pane = tk.PanedWindow(outer, orient="vertical", bg=Colors.BORDER, bd=0, sashwidth=8, sashrelief="flat")
        self.pane.pack(fill="both", expand=True, pady=(8, 0))

        # 上半部主內容 (步驟精靈 + 右側進度)
        content = tk.Frame(self.pane, bg=Colors.BG_DARK)
        self.pane.add(content, minsize=200, stretch="always")

        # 下半部日誌視窗 (設小 minsize 以便用戶可以縮小至僅剩標題列，甚至設為 0 以便拉到不見)
        self.log_container = tk.Frame(self.pane, bg=Colors.BG_DARK)
        self.pane.add(self.log_container, minsize=0, stretch="never")

        # 右側進度欄 (必須優先 pack 以確保在右側佔用固定的 285px 寬度，並且垂直填滿)
        right = tk.Frame(content, bg=Colors.BG_CARD, width=285)
        right.pack(side="right", fill="y")

        # 左側精靈外框，內嵌可滾動的 Canvas (後 pack 且設 expand=True 以便佔滿賸餘的所有寬度)
        left_container = tk.Frame(content, bg=Colors.BG_DARK)
        left_container.pack(side="left", fill="both", expand=True, padx=(0, 8))

        canvas = tk.Canvas(left_container, bg=Colors.BG_DARK, bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_container, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        scroll_content = tk.Frame(canvas, bg=Colors.BG_DARK)
        canvas_frame = canvas.create_window((0, 0), window=scroll_content, anchor="nw")

        # 設定滾動邊界與寬度自動調整
        scroll_content.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_frame, width=e.width))

        # 滑鼠滾輪事件綁定，避免全域滾輪衝突
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        self._build_wizard(scroll_content)
        self._build_sidebar(right)
        self._build_log_panel(self.log_container)

    def _build_header(self, parent) -> None:
        header = tk.Frame(parent, bg=Colors.BG_DARK)
        header.pack(fill="x")

        tk.Label(
            header, text="🚀 Hermes Agent 一鍵部署",
            bg=Colors.BG_DARK, fg=Colors.TEXT_TITLE,
            font=(Fonts.FAMILY[0], Fonts.SIZE_TITLE, "bold"),
        ).pack(side="left")

        tk.Label(
            header, text=f"v{APP_VERSION}",
            bg=Colors.BG_DARK, fg=Colors.TEXT_MUTED,
            font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL),
        ).pack(side="left", padx=(8, 0), pady=(6, 0))

        tk.Label(
            header,
            text="只要 3 步：① 貼 Token 與整合  ② 本地授權  ③ 右側一鍵部署",
            bg=Colors.BG_DARK, fg=Colors.TEXT_SECONDARY,
            font=(Fonts.FAMILY[0], Fonts.SIZE_BODY),
        ).pack(side="right")

    def _build_wizard(self, parent) -> None:
        # ── Step 1: HF Token ──
        card1 = self._card(parent, "第 1 步：Hugging Face 帳號與 Token 設定")

        hf_instruct = tk.Label(
            card1, text=(
                "💡 說明：\n"
                "1. 若沒有帳號，請點選『📝 註冊帳號』建立免費帳號。\n"
                "2. 點選『📋 取得 Token』，新增一個類型為『Write』(寫入) 的 Token。\n"
                "   ⚠️ 請務必選擇 Write，若選成 Read，部署時會因權限不足而失敗！\n"
                "3. 將產生的 Token 貼入下方，並可點擊『🔍 驗證 Token』測試登入狀態。"
            ),
            bg=Colors.BG_CARD, fg=Colors.TEXT_SECONDARY, justify="left", anchor="w",
            font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL), pady=4
        )
        hf_instruct.pack(fill="x", padx=12, pady=(0, 6))

        row1 = tk.Frame(card1, bg=Colors.BG_CARD)
        row1.pack(fill="x", padx=12, pady=(0, 4))
        tk.Label(row1, text="HF Write Token", bg=Colors.BG_CARD, fg=Colors.TEXT_PRIMARY,
                 font=(Fonts.FAMILY[0], Fonts.SIZE_BODY)).pack(side="left")

        btn_frame1 = tk.Frame(row1, bg=Colors.BG_CARD)
        btn_frame1.pack(side="right")

        tk.Button(btn_frame1, text="🔍 驗證 Token", command=self._cmd_verify_hf_token,
                  bg=Colors.BTN_PRIMARY, fg="#ffffff", relief="flat",
                  font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL), cursor="hand2").pack(side="left", padx=2)

        tk.Button(btn_frame1, text="📋 取得 Token", command=lambda: webbrowser.open(HF_TOKEN_URL),
                  bg=Colors.BTN_SECONDARY, fg=Colors.ACCENT_BLUE, relief="flat",
                  font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL), cursor="hand2").pack(side="left", padx=2)

        tk.Button(btn_frame1, text="📝 註冊帳號", command=lambda: webbrowser.open(HF_SIGNUP_URL),
                  bg=Colors.BTN_SECONDARY, fg=Colors.ACCENT_CYAN, relief="flat",
                  font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL), cursor="hand2").pack(side="left", padx=2)

        self.token_entry = TokenEntry(card1, textvariable=self.hf_token_var)
        self.token_entry.pack(fill="x", padx=12, pady=(0, 8))

        row1_sub = tk.Frame(card1, bg=Colors.BG_CARD)
        row1_sub.pack(fill="x", padx=12, pady=(0, 4))
        tk.Label(row1_sub, text="HF Space 名稱 (帳號/專案名)", bg=Colors.BG_CARD, fg=Colors.TEXT_PRIMARY,
                 font=(Fonts.FAMILY[0], Fonts.SIZE_BODY)).pack(side="left")

        tk.Entry(card1, textvariable=self.repo_id_var, bg=Colors.BG_INPUT, fg=Colors.TEXT_PRIMARY,
                 insertbackground=Colors.TEXT_PRIMARY, font=(Fonts.FAMILY[0], Fonts.SIZE_BODY),
                 relief="flat", borderwidth=6).pack(fill="x", padx=12, pady=(0, 8))

        # ── Step 2: Security & Required Settings ──
        card_sec = self._card(parent, "第 2 步：安全性與必要設定 (必填)")

        sec_instruct = tk.Label(
            card_sec, text="🔒 以下為必填欄位，Gateway Token 為登入密碼，Cloudflare Workers Token 用於 Telegram 代理連線。",
            bg=Colors.BG_CARD, fg=Colors.ACCENT_YELLOW, justify="left", anchor="w",
            font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL, "bold"), pady=4
        )
        sec_instruct.pack(fill="x", padx=12, pady=(0, 6))

        sec_cols = tk.Frame(card_sec, bg=Colors.BG_CARD)
        sec_cols.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        sec_left = tk.Frame(sec_cols, bg=Colors.BG_CARD)
        sec_left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        sec_right = tk.Frame(sec_cols, bg=Colors.BG_CARD)
        sec_right.pack(side="left", fill="both", expand=True)

        def _make_required_row(parent_frame, label_text, var, btn_cmd=None, btn_text="💡 說明"):
            row = tk.Frame(parent_frame, bg=Colors.BG_CARD)
            row.pack(fill="x", pady=2)
            lbl_row = tk.Frame(row, bg=Colors.BG_CARD)
            lbl_row.pack(fill="x")
            tk.Label(lbl_row, text="⚠️ " + label_text + " (必填)", bg=Colors.BG_CARD, fg=Colors.ACCENT_YELLOW,
                     font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL, "bold")).pack(side="left")
            if btn_cmd:
                tk.Button(lbl_row, text=btn_text, command=btn_cmd,
                          bg=Colors.BTN_SECONDARY, fg=Colors.ACCENT_CYAN, relief="flat",
                          font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL), cursor="hand2", bd=0, pady=0).pack(side="right")
            entry = TokenEntry(row, textvariable=var)
            entry.pack(fill="x", pady=(2, 4))
            return entry

        _make_required_row(sec_left, "Gateway Token (登入密碼)", self.gateway_token_var,
                           btn_cmd=lambda: messagebox.showinfo("Gateway Token 說明",
                               "此 Token 為您登入 Hermes Agent 網頁介面時的密碼。\n\n"
                               "預設值為 admin123，建議您自行修改為較安全的密碼。\n"
                               "部署後可在瀏覽器 Unlock 頁面輸入此密碼登入。"))

        _make_required_row(sec_right, "Cloudflare Workers API Token", self.cloudflare_workers_token_var,
                           btn_cmd=lambda: self._show_cloudflare_guide(), btn_text="📋 註冊與申請教學")

        # ── Step 3: External Integrations ──
        card2 = self._card(parent, "第 3 步：聊天機器人與外部工具整合 (選填)")

        tools_instruct = tk.Label(
            card2, text="💡 說明：填入對應 Token 可讓 Hermes 自動串接您的機器人或讀取您的知識庫。不需要的可留空。",
            bg=Colors.BG_CARD, fg=Colors.TEXT_SECONDARY, justify="left", anchor="w",
            font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL), pady=4
        )
        tools_instruct.pack(fill="x", padx=12, pady=(0, 6))

        # 左右雙欄版面配置
        col_container = tk.Frame(card2, bg=Colors.BG_CARD)
        col_container.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        col_left = tk.Frame(col_container, bg=Colors.BG_CARD)
        col_left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        col_right = tk.Frame(col_container, bg=Colors.BG_CARD)
        col_right.pack(side="left", fill="both", expand=True)

        def make_entry_row(parent_frame, label_text, var, show_btn=True, btn_cmd=None, btn_text="💡 申請說明"):
            row = tk.Frame(parent_frame, bg=Colors.BG_CARD)
            row.pack(fill="x", pady=2)
            
            lbl_row = tk.Frame(row, bg=Colors.BG_CARD)
            lbl_row.pack(fill="x")
            
            tk.Label(lbl_row, text=label_text, bg=Colors.BG_CARD, fg=Colors.TEXT_PRIMARY,
                     font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL, "bold")).pack(side="left")
                     
            if show_btn and btn_cmd:
                tk.Button(lbl_row, text=btn_text, command=btn_cmd,
                          bg=Colors.BTN_SECONDARY, fg=Colors.ACCENT_CYAN, relief="flat",
                          font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL), cursor="hand2", bd=0, pady=0).pack(side="right")
                          
            entry = TokenEntry(row, textvariable=var)
            entry.pack(fill="x", pady=(2, 4))
            return entry

        # 左欄：通訊與聊天機器人 (Bots)
        make_entry_row(col_left, "Telegram Bot Token", self.tg_token_var, 
                       btn_cmd=lambda: self._show_telegram_guide(), btn_text="📋 註冊教學")

        make_entry_row(col_left, "Telegram 允許使用者 ID (必填，逗號分隔)", self.telegram_allowed_users_var,
                       btn_cmd=lambda: messagebox.showinfo("Telegram User ID 取得方法",
                           "如何取得您的 Telegram 使用者 ID：\n\n"
                           "1. 在 Telegram 中搜尋 @userinfobot\n"
                           "2. 對該 Bot 發送任意訊息\n"
                           "3. Bot 會回覆您的數字 User ID\n\n"
                           "格式：單一 ID 或多個以逗號分隔\n"
                           "例如：123456789 或 123456789,987654321\n\n"
                           "❗ 未填寫此欄位將允許任何人使用您的 Bot！"), btn_text="💡 如何取得 ID")
                       
        make_entry_row(col_left, "Telegram API 代理 (Base URL - 選填)", self.telegram_base_url_var,
                       btn_cmd=lambda: messagebox.showinfo("Telegram Base URL 說明", "選填。如果部署在 Hugging Face Spaces 且與 Telegram 連線逾時，可改填您的 Telegram 代理 API 網址。\n例如自己架設的 Cloudflare Worker 轉發網址：\nhttps://your-worker.workers.dev\n留空則使用預設的官方 api.telegram.org"), btn_text="💡 說明")

        make_entry_row(col_left, "Telegram Proxy (SOCKS5/HTTP - 選填)", self.telegram_proxy_var,
                       btn_cmd=lambda: messagebox.showinfo("Telegram Proxy 說明", "選填。可用於繞過 Telegram 網路限制。格式為：\nsocks5://user:pass@host:port 或\nhttp://user:pass@host:port\n(注意：如果有填寫上述 Base URL 則通常不需再填此 Proxy)"), btn_text="💡 說明")

        make_entry_row(col_left, "Cloudflare Proxy URL (現成代理 URL - 選填)", self.cloudflare_proxy_url_var,
                       btn_cmd=lambda: messagebox.showinfo("Cloudflare Proxy URL 說明", "選填。如果您已經有自己架設好的 Cloudflare Worker 轉發網址，可直接在此填寫。\n(例如: https://xxx.xxx.workers.dev)"), btn_text="💡 說明")
                       
        make_entry_row(col_left, "Discord Bot Token", self.discord_token_var,
                       btn_cmd=lambda: self._show_discord_guide(), btn_text="📋 註冊教學")

        make_entry_row(col_left, "Discord Webhook URL (上線通知用 - 選填)", self.discord_webhook_url_var,
                       btn_cmd=lambda: messagebox.showinfo("Discord Webhook 說明",
                           "Discord Webhook URL 用於部署完成後發送上線通知。\n\n"
                           "取得方式：\n"
                           "1. 在 Discord 伺服器中選擇一個頻道\n"
                           "2. 點擊頻道設定→整合→Webhook\n"
                           "3. 點擊「建立 Webhook」\n"
                           "4. 複製 Webhook URL 貼到此處"), btn_text="💡 說明")

        make_entry_row(col_left, "Discord 允許使用者 ID (選填，逗號分隔)", self.discord_allowed_users_var,
                       btn_cmd=lambda: messagebox.showinfo("Discord User ID 取得方法",
                           "如何取得 Discord User ID：\n\n"
                           "1. Discord 設定 → 進階→開封開發者模式\n"
                           "2. 右鍵點擊你的名字→「複製使用者 ID」\n\n"
                           "格式：123456789012345678\n"
                           "多個以逗號分隔"), btn_text="💡 如何取得 ID")
                       
        make_entry_row(col_left, "Line Channel Access Token", self.line_token_var,
                       btn_cmd=lambda: webbrowser.open("https://developers.line.biz/console/"))
                       
        row_secret = tk.Frame(col_left, bg=Colors.BG_CARD)
        row_secret.pack(fill="x", pady=2)
        tk.Label(row_secret, text="Line Channel Secret", bg=Colors.BG_CARD, fg=Colors.TEXT_PRIMARY,
                 font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL, "bold")).pack(side="left")
        TokenEntry(row_secret, textvariable=self.line_secret_var).pack(fill="x", pady=(2, 4))

        # 右欄：知識庫整合 (Knowledge bases)
        notebooklm_help = lambda: messagebox.showinfo(
            "Google NotebookLM Cookie 取得方法",
            "1. 用 Chrome 瀏覽器登入 Google NotebookLM 網站。\n"
            "2. 按 F12 鍵打開開發者工具。\n"
            "3. 點選上方頁籤『Application』(應用程式) -> 左側『Cookies』-> 選擇 NotebookLM 網址。\n"
            "4. 在清單中找到『__Secure-1PSID』，複製其 Value (值) 貼到此處。\n\n"
            "※ 本一鍵部署工具會自動使用開源的 `notebooklm-py` 套件串接以完成您的知識記憶。"
        )
        make_entry_row(col_right, "Google NotebookLM Cookie (__Secure-1PSID)", self.notebooklm_cookie_var,
                       btn_cmd=notebooklm_help, btn_text="💡 怎麼拿？")

        obsidian_help = lambda: messagebox.showinfo(
            "Obsidian 雲端同步與整合說明",
            "💡 本工具會在雲端 Hugging Face Space 的容器中安裝 Obsidian Headless 同步服務，並在內部以 Local REST API 的方式讓 Agent 直接存取您的筆記庫。\n\n"
            "請填寫您的 Obsidian Sync (官方同步服務) 登入資訊：\n"
            "1. Obsidian Sync 帳號：您的註冊 Email。\n"
            "2. Obsidian Sync 密碼：您的帳號密碼。\n"
            "3. 筆記庫名稱 (Vault)：雲端要同步的筆記庫名稱。\n"
            "4. 解密密碼 (選填)：若您的筆記庫啟用了自訂端對端加密，請在此填入解密金鑰。\n"
            "5. API Key：您可以自訂或複製一組長字串作為 API 金鑰以保護連線安全性，Agent 將使用此金鑰存取內建 API。\n\n"
            "※ 提示：如果不需要同步本機 Obsidian，將下方各欄留空即可。"
        )

        obs_header_row = tk.Frame(col_right, bg=Colors.BG_CARD)
        obs_header_row.pack(fill="x", pady=(6, 2))
        tk.Label(obs_header_row, text="Obsidian Sync 雲端同步設定", bg=Colors.BG_CARD, fg=Colors.TEXT_PRIMARY,
                 font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL, "bold")).pack(side="left")
        tk.Button(obs_header_row, text="💡 說明", command=obsidian_help,
                  bg=Colors.BTN_SECONDARY, fg=Colors.ACCENT_CYAN, relief="flat",
                  font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL), cursor="hand2", bd=0, pady=0).pack(side="right")

        # 1. Email
        row_email = tk.Frame(col_right, bg=Colors.BG_CARD)
        row_email.pack(fill="x", pady=1)
        tk.Label(row_email, text="Obsidian 帳號 (Email)", bg=Colors.BG_CARD, fg=Colors.TEXT_MUTED,
                 font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL)).pack(anchor="w")
        TokenEntry(row_email, textvariable=self.obsidian_email_var).pack(fill="x", pady=(1, 2))

        # 2. Password
        row_pass = tk.Frame(col_right, bg=Colors.BG_CARD)
        row_pass.pack(fill="x", pady=1)
        tk.Label(row_pass, text="Obsidian 密碼", bg=Colors.BG_CARD, fg=Colors.TEXT_MUTED,
                 font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL)).pack(anchor="w")
        TokenEntry(row_pass, textvariable=self.obsidian_password_var).pack(fill="x", pady=(1, 2))

        # 3. Vault Name
        row_vault = tk.Frame(col_right, bg=Colors.BG_CARD)
        row_vault.pack(fill="x", pady=1)
        tk.Label(row_vault, text="筆記庫名稱 (Vault Name)", bg=Colors.BG_CARD, fg=Colors.TEXT_MUTED,
                 font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL)).pack(anchor="w")
        tk.Entry(row_vault, textvariable=self.obsidian_vault_var, bg=Colors.BG_INPUT, fg=Colors.TEXT_PRIMARY,
                 insertbackground=Colors.TEXT_PRIMARY, font=(Fonts.FAMILY[0], Fonts.SIZE_BODY),
                 relief="flat", borderwidth=4).pack(fill="x", pady=(1, 2))

        # 4. Decryption Passphrase (选填)
        row_phrase = tk.Frame(col_right, bg=Colors.BG_CARD)
        row_phrase.pack(fill="x", pady=1)
        tk.Label(row_phrase, text="自訂解密金鑰 (選填，無啟用 E2EE 則留空)", bg=Colors.BG_CARD, fg=Colors.TEXT_MUTED,
                 font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL)).pack(anchor="w")
        TokenEntry(row_phrase, textvariable=self.obsidian_passphrase_var).pack(fill="x", pady=(1, 2))

        # 5. API Key (用以保護連線)
        row_key = tk.Frame(col_right, bg=Colors.BG_CARD)
        row_key.pack(fill="x", pady=1)
        tk.Label(row_key, text="自訂 Local REST API Key (保護連線用，可自訂)", bg=Colors.BG_CARD, fg=Colors.TEXT_MUTED,
                 font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL)).pack(anchor="w")
        TokenEntry(row_key, textvariable=self.obsidian_token_var).pack(fill="x", pady=(1, 2))

        # ── Step 3: Codex auth ──
        card3 = self._card(parent, "第 4 步：OpenAI-Codex 授權")

        codex_instruct = tk.Label(
            card3, text=(
                "💡 說明：\n"
                "1. 如果本機已登入 Codex，直接點『🔎 偵測/匯入 Codex 授權』即可。\n"
                "2. 系統會讀取 ~/.codex/auth.json，並同步成部署需要的 ~/.hermes/auth.json。\n"
                "3. 若尚未登入，點『🔑 安裝/登入 Codex』開啟 Codex CLI 登入流程。\n"
                "4. 完成登入後再點一次『🔎 偵測/匯入 Codex 授權』，部署時會自動上傳授權檔。"
            ),
            bg=Colors.BG_CARD, fg=Colors.TEXT_SECONDARY, justify="left", anchor="w",
            font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL), pady=4
        )
        codex_instruct.pack(fill="x", padx=12, pady=(0, 6))

        row3_btns = tk.Frame(card3, bg=Colors.BG_CARD)
        row3_btns.pack(fill="x", padx=12, pady=(0, 8))

        self.import_codex_auth_btn = tk.Button(
            row3_btns,
            text="🔎 偵測/匯入 Codex 授權",
            command=lambda: self._run_async(
                self._cmd_import_codex_auth,
                button=self.import_codex_auth_btn,
                busy_text="⏳ 匯入中...",
            ),
            bg=Colors.BTN_SECONDARY,
            fg=Colors.TEXT_PRIMARY,
            relief="flat",
            font=(Fonts.FAMILY[0], Fonts.SIZE_BODY, "bold"),
            cursor="hand2",
            pady=6,
        )
        self.import_codex_auth_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        tk.Button(row3_btns, text="🔑 安裝/登入 Codex", command=lambda: self._run_async(self._cmd_codex_login),
                  bg=Colors.BTN_SECONDARY, fg=Colors.ACCENT_CYAN, relief="flat",
                  font=(Fonts.FAMILY[0], Fonts.SIZE_BODY, "bold"), cursor="hand2", pady=6).pack(side="left", fill="x", expand=True)

        self._build_advanced(parent)

        # ── Step 4: Uptime Robot ──
        card4 = self._card(parent, "第 4 步：設定永久在線 (Uptime Robot 監控 - 選填)")
        ur_instruct = tk.Label(
            card4, text=(
                "💡 說明：\n"
                "因為 Hugging Face Space 會在一段時間沒有人使用時自動休眠（暫停運作）。\n"
                "您可以設定免費的 Uptime Robot 監控以保持不休眠：\n"
                "1. 註冊並登入 Uptime Robot 網站。\n"
                "2. 新增一個監視器 (Monitor Type: HTTP)。\n"
                "3. 網址填入部署後的 Space 網址加上 /ping\n"
                "   (例如: https://帳號-專案名.hf.space/ping)\n"
                "4. 監控時間設為每 5 分鐘一次即可保持不休眠！"
            ),
            bg=Colors.BG_CARD, fg=Colors.TEXT_SECONDARY, justify="left", anchor="w",
            font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL), pady=4
        )
        ur_instruct.pack(fill="x", padx=12, pady=(0, 6))

        tk.Button(card4, text="🔗 前往 Uptime Robot 官網", command=lambda: webbrowser.open("https://uptimerobot.com/"),
                  bg=Colors.BTN_SECONDARY, fg=Colors.ACCENT_BLUE, relief="flat",
                  font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL, "bold"), cursor="hand2", bd=0).pack(anchor="e", padx=12, pady=(0, 8))

    def _build_advanced(self, parent) -> None:
        adv_toggle = tk.Frame(parent, bg=Colors.BG_DARK)
        adv_toggle.pack(fill="x", pady=(4, 0))

        self._adv_visible = False
        self._adv_btn = tk.Button(
            adv_toggle, text="▶ 進階設定（通常不用改）",
            command=self._toggle_advanced,
            bg=Colors.BG_DARK, fg=Colors.TEXT_MUTED,
            activebackground=Colors.BG_DARK,
            font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL),
            relief="flat", borderwidth=0, cursor="hand2",
        )
        self._adv_btn.pack(anchor="w")

        self._adv_frame = tk.Frame(parent, bg=Colors.BG_CARD)
        # Initially hidden

        rows = [
            ("Provider", self.provider_var, "通常固定 openai-codex"),
        ]
        for i, (label, var, hint) in enumerate(rows):
            row = tk.Frame(self._adv_frame, bg=Colors.BG_CARD)
            row.pack(fill="x", padx=12, pady=3)
            tk.Label(row, text=label, bg=Colors.BG_CARD, fg=Colors.TEXT_PRIMARY, width=12, anchor="w",
                     font=(Fonts.FAMILY[0], Fonts.SIZE_BODY)).pack(side="left")
            tk.Entry(row, textvariable=var, bg=Colors.BG_INPUT, fg=Colors.TEXT_PRIMARY,
                     insertbackground=Colors.TEXT_PRIMARY, font=(Fonts.FAMILY[0], Fonts.SIZE_BODY),
                     relief="flat", borderwidth=4, width=30).pack(side="left", padx=4)
            tk.Label(row, text=hint, bg=Colors.BG_CARD, fg=Colors.TEXT_MUTED,
                     font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL)).pack(side="left", padx=4)

        # Model dropdown with common options
        model_row = tk.Frame(self._adv_frame, bg=Colors.BG_CARD)
        model_row.pack(fill="x", padx=12, pady=3)
        tk.Label(model_row, text="Model", bg=Colors.BG_CARD, fg=Colors.TEXT_PRIMARY, width=12, anchor="w",
                 font=(Fonts.FAMILY[0], Fonts.SIZE_BODY)).pack(side="left")
        model_choices = ["gpt-5.5", "gpt-5.4-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "o3", "o4-mini"]
        model_combo = ttk.Combobox(model_row, textvariable=self.model_var, values=model_choices,
                                   font=(Fonts.FAMILY[0], Fonts.SIZE_BODY), width=28)
        model_combo.pack(side="left", padx=4)
        tk.Label(model_row, text="可自行輸入或選擇模型", bg=Colors.BG_CARD, fg=Colors.TEXT_MUTED,
                 font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL)).pack(side="left", padx=4)

        # Path rows
        self._path_row_adv(self._adv_frame, "專案資料夾", self.project_dir_var, True)
        self._path_row_adv(self._adv_frame, "Hermes auth", self.hermes_auth_path_var, False)
        self._path_row_adv(self._adv_frame, "Codex auth", self.codex_auth_path_var, False)

        chk_frame = tk.Frame(self._adv_frame, bg=Colors.BG_CARD)
        chk_frame.pack(fill="x", padx=12, pady=4)
        ttk.Checkbutton(chk_frame, text="Space 設為 private", variable=self.private_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(chk_frame, text="上傳 Codex auth.json", variable=self.include_codex_auth_var).pack(side="left")

        # Individual step buttons
        btn_frame = tk.Frame(self._adv_frame, bg=Colors.BG_CARD)
        btn_frame.pack(fill="x", padx=12, pady=(4, 8))

        buttons = [
            ("檢查環境", self._cmd_check_env),
            ("安裝 HF Hub", self._cmd_install_hf),
            ("匯入 Codex Auth", self._cmd_import_codex_auth),
            ("HF 登入", self._cmd_hf_login),
            ("建立 Space", self._cmd_create_space),
            ("Codex 登入", self._cmd_codex_login),
            ("檢查 auth", self._cmd_check_auth),
            ("產生檔案", self._cmd_gen_files),
            ("上傳 Secrets", self._cmd_upload_secrets),
            ("上傳 Space", self._cmd_upload_space),
            ("重啟 Space", self._cmd_restart_space),
        ]
        for idx, (text, cmd) in enumerate(buttons):
            btn = tk.Button(
                btn_frame, text=text,
                bg=Colors.BTN_SECONDARY, fg=Colors.TEXT_PRIMARY,
                activebackground=Colors.BTN_SECONDARY_HOVER,
                font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL), relief="flat",
                borderwidth=0, cursor="hand2", padx=6, pady=3,
            )
            if text == "匯入 Codex Auth":
                btn.configure(command=lambda c=cmd, b=btn: self._run_async(c, button=b, busy_text="匯入中..."))
            else:
                btn.configure(command=lambda c=cmd: self._run_async(c))
            btn.grid(row=idx // 4, column=idx % 4, sticky="ew", padx=3, pady=2)
        for c in range(4):
            btn_frame.columnconfigure(c, weight=1)

    def _toggle_advanced(self):
        self._adv_visible = not self._adv_visible
        if self._adv_visible:
            self._adv_frame.pack(fill="x", pady=(2, 4))
            self._adv_btn.configure(text="▼ 進階設定（通常不用改）")
        else:
            self._adv_frame.pack_forget()
            self._adv_btn.configure(text="▶ 進階設定（通常不用改）")

    def _path_row_adv(self, parent, label, var, is_dir):
        row = tk.Frame(parent, bg=Colors.BG_CARD)
        row.pack(fill="x", padx=12, pady=3)
        tk.Label(row, text=label, bg=Colors.BG_CARD, fg=Colors.TEXT_PRIMARY, width=12, anchor="w",
                 font=(Fonts.FAMILY[0], Fonts.SIZE_BODY)).pack(side="left")
        tk.Entry(row, textvariable=var, bg=Colors.BG_INPUT, fg=Colors.TEXT_PRIMARY,
                 insertbackground=Colors.TEXT_PRIMARY, font=(Fonts.FAMILY[0], Fonts.SIZE_BODY),
                 relief="flat", borderwidth=4).pack(side="left", fill="x", expand=True, padx=4)
        tk.Button(row, text="📁", command=lambda: self._pick_path(var, is_dir),
                  bg=Colors.BTN_SECONDARY, fg=Colors.TEXT_PRIMARY, relief="flat",
                  font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL), cursor="hand2").pack(side="right")

    def _build_sidebar(self, parent) -> None:
        # 將「一鍵開始部署」卡片排在最上方
        deploy_card = tk.Frame(parent, bg=Colors.BG_CARD, padx=8, pady=8)
        deploy_card.pack(fill="x", side="top", pady=(10, 0))

        self.deploy_btn = tk.Button(
            deploy_card, text="🚀 一鍵開始部署",
            command=self._start_deploy,
            bg=Colors.BTN_PRIMARY, fg="#ffffff",
            activebackground=Colors.BTN_PRIMARY_HOVER,
            font=(Fonts.FAMILY[0], Fonts.SIZE_BUTTON_BIG, "bold"),
            relief="flat", borderwidth=0, cursor="hand2", pady=12,
        )
        self.deploy_btn.pack(fill="x", pady=(0, 6))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            deploy_card, variable=self.progress_var, maximum=100,
            style="Horizontal.TProgressbar",
        )
        self.progress_bar.pack(fill="x", pady=(0, 6))

        self.status_label = tk.Label(
            deploy_card, text="準備就緒", bg=Colors.BG_CARD, fg=Colors.TEXT_MUTED,
            font=(Fonts.FAMILY[0], Fonts.SIZE_SMALL),
        )
        self.status_label.pack(anchor="w")

        # 分隔線
        sep = tk.Frame(parent, bg=Colors.BORDER, height=1)
        sep.pack(fill="x", padx=10, pady=10)

        # 部署進度標題
        tk.Label(parent, text="📋 部署進度", bg=Colors.BG_CARD, fg=Colors.ACCENT_BLUE,
                 font=(Fonts.FAMILY[0], Fonts.SIZE_SUBTITLE, "bold")).pack(padx=10, pady=(0, 6), anchor="w")

        self.step_tracker = StepTracker(parent)
        self.step_tracker.pack(fill="x", padx=6, pady=4)

        # 系統上線可用狀態標籤
        self.online_status_label = tk.Label(
            parent, text="", bg=Colors.BG_CARD, fg=Colors.STATUS_SUCCESS,
            font=(Fonts.FAMILY[0], Fonts.SIZE_SUBTITLE, "bold"), anchor="w"
        )
        self.online_status_label.pack(fill="x", padx=14, pady=(6, 0))

    def _show_cloudflare_guide(self) -> None:
        """顯示 Cloudflare Workers API Token 註冊與申請教學。"""
        guide = (
            "📋 Cloudflare Workers API Token 申請教學\n\n"
            "Cloudflare Workers Token 用於自動在您的 Cloudflare 帳戶建立\n"
            "Telegram API 代理 Worker，解決 HF Spaces 無法直連 Telegram 的問題。\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "步驟 1：註冊 Cloudflare 帳號\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "前往 https://dash.cloudflare.com/sign-up 註冊免費帳號。\n"
            "（已有帳號請跳過此步驟）\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "步驟 2：建立 API Token\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1. 登入後，前往：\n"
            "   https://dash.cloudflare.com/profile/api-tokens\n"
            "2. 點擊「Create Token」(建立 Token)\n"
            "3. 選擇「Create Custom Token」(自訂 Token)\n"
            "4. Token 名稱可填：HuggingMes-Proxy\n"
            "5. 權限設定：\n"
            "   • Account / Workers Scripts → Edit\n"
            "   • Account / Workers Routes → Edit\n"
            "   • Zone / Workers Routes → Edit (選填)\n"
            "6. 帳戶資源：選擇 Include → All accounts\n"
            "7. 點擊「Continue to summary」→「Create Token」\n"
            "8. 複製產生的 Token 貼到上方欄位\n\n"
            "⚠️ 注意：Token 只會顯示一次，請妥善保存！\n"
            "（Cloudflare Workers 免費方案每天 100,000 請求，完全足夠使用）"
        )
        result = messagebox.showinfo("Cloudflare Workers API Token 申請教學", guide)
        # 提供快速開啟瀏覽器的選項
        if messagebox.askyesno("開啟 Cloudflare", "是否立即開啟 Cloudflare API Token 設定頁面？"):
            webbrowser.open("https://dash.cloudflare.com/profile/api-tokens")

    def _show_telegram_guide(self) -> None:
        """顯示 Telegram Bot 註冊教學。"""
        guide = (
            "📋 Telegram Bot 註冊教學\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "步驟 1：建立 Bot\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1. 在 Telegram 中搜尋 @BotFather\n"
            "2. 發送 /newbot 命令\n"
            "3. 依照提示設定 Bot 名稱\n"
            "4. BotFather 會回覆一組 Token，複製貼到上方欄位\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "步驟 2：取得您的 User ID\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1. 在 Telegram 中搜尋 @userinfobot\n"
            "2. 對該 Bot 發送任意訊息\n"
            "3. Bot 會回覆您的數字 User ID\n"
            "4. 將此 ID 填入「允許使用者 ID」欄位\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "步驟 3：對 Bot 發送訊息\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "部署前，請在 Telegram 中對您的新 Bot 發送 /start\n"
            "這樣部署工具才能偵測到您的 Chat ID。"
        )
        messagebox.showinfo("Telegram Bot 註冊教學", guide)

    def _show_discord_guide(self) -> None:
        """顯示 Discord Bot 註冊教學。"""
        guide = (
            "📋 Discord Bot 註冊教學\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "步驟 1：建立 Discord 應用程式\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1. 前往 Discord Developer Portal\n"
            "2. 點擊「New Application」建立新應用\n"
            "3. 設定應用名稱（例如：Hermes Agent）\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "步驟 2：設定 Bot\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1. 左側選單 → Bot\n"
            "2. 點擊「Reset Token」取得 Bot Token\n"
            "3. 開啟以下 Privileged Gateway Intents：\n"
            "   • Server Members Intent ✅\n"
            "   • Message Content Intent ✅\n"
            "   • Presence Intent ✅（選填）\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "步驟 3：邀請 Bot 加入伺服器\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1. 左側選單 → OAuth2 → URL Generator\n"
            "2. Scopes 勾選 bot\n"
            "3. Bot Permissions 勾選：\n"
            "   • Send Messages\n"
            "   • Read Message History\n"
            "   • View Channels\n"
            "4. 複製產生的邀請 URL 並在瀏覽器開啟\n"
            "5. 選擇你的伺服器並授權\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "步驟 4：設定 Webhook（選填，用於通知）\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1. 在伺服器中選擇一個頻道\n"
            "2. 頻道設定 → 整合 → Webhook\n"
            "3. 建立 Webhook 並複製 URL"
        )
        messagebox.showinfo("Discord Bot 註冊教學", guide)
        if messagebox.askyesno("開啟 Discord", "是否立即開啟 Discord Developer Portal？"):
            webbrowser.open("https://discord.com/developers/applications")

    def _toggle_log(self) -> None:
        self._log_visible = not self._log_visible
        if self._log_visible:
            self.pane.add(self.log_container, minsize=0, stretch="never")
            self.log_toggle_btn.configure(text="👁️ 隱藏日誌")
        else:
            self.pane.forget(self.log_container)
            self.log_toggle_btn.configure(text="👁️ 顯示日誌")

    def _build_log_panel(self, parent) -> None:
        self.log_panel = DarkLogPanel(parent, height=12)
        self.log_panel.pack(fill="both", expand=True)
        self.log("程式已啟動。填寫以上資料，然後點擊右側『🚀 一鍵開始部署』按鈕。")

    def _cmd_verify_hf_token(self) -> None:
        token = self.hf_token_var.get().strip()
        if not token:
            messagebox.showwarning("提示", "請先輸入 Hugging Face Token！")
            return
        self.log("正在驗證 Hugging Face Token...")
        
        def run():
            try:
                from huggingface_hub import whoami
                info = whoami(token=token)
                username = info.get("name", "未知")
                auth = info.get("auth", {})
                role = "unknown"
                if isinstance(auth, dict) and "accessToken" in auth:
                    role = auth["accessToken"].get("role", "unknown")
                
                self.log(f"✅ 驗證成功！使用者名稱：{username}，權限角色：{role}")
                
                # 自動偵測並填入 Space 名稱
                detected_repo = f"{username}/hermes-agent-space"
                self.repo_id_var.set(detected_repo)
                self.log(f"  已根據驗證的使用者名稱自動填入專案名稱：{detected_repo}")

                if role != "write":
                    self.log("⚠️ 警告：偵測到此 Token 可能不是『Write』權限。若無法寫入 Space，請至 HF 重新建立 Token。")
                    messagebox.showwarning("權限警告", f"驗證成功！使用者為 {username}。\n但偵測到 Token 權限不是 Write (目前為 {role})，請確保您的 Token 具有 Write 權限，否則部署將會失敗。")
                else:
                    messagebox.showinfo("驗證成功", f"驗證成功！\n\n登入使用者：{username}\nToken 權限：{role} (Write)\n\n已為您填入專案名稱：{detected_repo}")
            except Exception as e:
                self.log(f"❌ 驗證失敗：{e}")
                messagebox.showerror("驗證失敗", f"無法驗證 Token，錯誤訊息：\n{e}")
                
        self._run_async(run)
    # ── Helpers ──────────────────────────────────────────────

    def _card(self, parent, title: str) -> tk.Frame:
        card = tk.Frame(parent, bg=Colors.BG_CARD, padx=2, pady=2)
        card.pack(fill="x", pady=(0, 6))

        tk.Label(card, text=title, bg=Colors.BG_CARD, fg=Colors.ACCENT_BLUE,
                 font=(Fonts.FAMILY[0], Fonts.SIZE_SUBTITLE, "bold")).pack(anchor="w", padx=12, pady=(8, 4))
        return card

    def _pick_path(self, var: tk.StringVar, is_dir: bool) -> None:
        if is_dir:
            p = filedialog.askdirectory()
        else:
            p = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if p:
            var.set(p)

    def log(self, message: str) -> None:
        self.log_queue.put(message)

    def _drain_log_queue(self) -> None:
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_panel.append(msg)
        except queue.Empty:
            pass
        self.after(100, self._drain_log_queue)

    def _clear_log(self) -> None:
        self.log_panel.clear()

    def _get_config(self) -> DeployConfig:
        return DeployConfig(
            repo_id=self.repo_id_var.get().strip(),
            project_dir=pathlib.Path(self.project_dir_var.get()).expanduser().resolve(),
            model=self.model_var.get().strip() or DEFAULT_MODEL,
            provider=self.provider_var.get().strip() or DEFAULT_PROVIDER,
            private=self.private_var.get(),
            hf_token=self.hf_token_var.get().strip(),
            hermes_auth_path=pathlib.Path(self.hermes_auth_path_var.get()).expanduser().resolve(),
            codex_auth_path=pathlib.Path(self.codex_auth_path_var.get()).expanduser().resolve(),
            include_codex_auth=self.include_codex_auth_var.get(),
            tg_token=self.tg_token_var.get().strip(),
            telegram_proxy=self.telegram_proxy_var.get().strip(),
            telegram_base_url=self.telegram_base_url_var.get().strip(),
            telegram_allowed_users=self.telegram_allowed_users_var.get().strip(),
            cloudflare_workers_token=self.cloudflare_workers_token_var.get().strip(),
            cloudflare_proxy_url=self.cloudflare_proxy_url_var.get().strip(),
            gateway_token=self.gateway_token_var.get().strip() or "admin123",
            discord_token=self.discord_token_var.get().strip(),
            discord_webhook_url=self.discord_webhook_url_var.get().strip(),
            discord_allowed_users=self.discord_allowed_users_var.get().strip(),
            line_token=self.line_token_var.get().strip(),
            line_secret=self.line_secret_var.get().strip(),
            notebooklm_cookie=self.notebooklm_cookie_var.get().strip(),
            obsidian_url=self.obsidian_url_var.get().strip() or "http://127.0.0.1:27124",
            obsidian_token=self.obsidian_token_var.get().strip(),
            obsidian_email=self.obsidian_email_var.get().strip(),
            obsidian_password=self.obsidian_password_var.get().strip(),
            obsidian_vault=self.obsidian_vault_var.get().strip(),
            obsidian_passphrase=self.obsidian_passphrase_var.get().strip(),
        )

    def _run_async(self, func, button=None, busy_text: str | None = None) -> None:
        original_text = None
        if button is not None:
            try:
                original_text = button.cget("text")
                button.configure(
                    text=busy_text or "執行中...",
                    state="disabled",
                    bg=Colors.BTN_SECONDARY_HOVER,
                    cursor="watch",
                )
                button.update_idletasks()
            except Exception:
                original_text = None
        threading.Thread(target=self._safe_run, args=(func, button, original_text), daemon=True).start()

    def _safe_run(self, func, button=None, original_text=None) -> None:
        try:
            func()
        except Exception as exc:
            self.log(f"ERROR: {type(exc).__name__}: {exc}")
            try:
                messagebox.showerror("錯誤", f"{type(exc).__name__}: {exc}")
            except Exception:
                pass
        finally:
            if button is not None and original_text is not None:
                try:
                    self.after(0, lambda: button.configure(
                        text=original_text,
                        state="normal",
                        bg=Colors.BTN_SECONDARY,
                        cursor="hand2",
                    ))
                except Exception:
                    pass

    def _load_tokens(self) -> None:
        try:
            import json
            token_path = pathlib.Path("token.json")
            if token_path.exists():
                with open(token_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.hf_token_var.set(data.get("hf_token", "").strip())
                    self.tg_token_var.set(data.get("tg_token", "").strip())
                    self.telegram_proxy_var.set(data.get("telegram_proxy", "").strip())
                    self.telegram_base_url_var.set(data.get("telegram_base_url", "").strip())
                    self.telegram_allowed_users_var.set(data.get("telegram_allowed_users", "").strip())
                    self.cloudflare_workers_token_var.set(data.get("cloudflare_workers_token", "").strip())
                    self.cloudflare_proxy_url_var.set(data.get("cloudflare_proxy_url", "").strip())
                    self.discord_token_var.set(data.get("discord_token", "").strip())
                    self.discord_webhook_url_var.set(data.get("discord_webhook_url", "").strip())
                    self.discord_allowed_users_var.set(data.get("discord_allowed_users", "").strip())
                    self.line_token_var.set(data.get("line_token", "").strip())
                    self.line_secret_var.set(data.get("line_secret", "").strip())
                    self.notebooklm_cookie_var.set(data.get("notebooklm_cookie", "").strip())
                    self.obsidian_url_var.set(data.get("obsidian_url", "http://127.0.0.1:27124").strip())
                    self.obsidian_token_var.set(data.get("obsidian_token", "").strip())
                    self.obsidian_email_var.set(data.get("obsidian_email", "").strip())
                    self.obsidian_password_var.set(data.get("obsidian_password", "").strip())
                    self.obsidian_vault_var.set(data.get("obsidian_vault", "").strip())
                    self.obsidian_passphrase_var.set(data.get("obsidian_passphrase", "").strip())
                    self.gateway_token_var.set(data.get("gateway_token", "admin123").strip() or "admin123")
        except Exception as e:
            print(f"Failed to load token.json at startup: {e}")

    def _save_tokens(self) -> None:
        try:
            import json
            token_data = {
                "hf_token": self.hf_token_var.get().strip(),
                "tg_token": self.tg_token_var.get().strip(),
                "telegram_proxy": self.telegram_proxy_var.get().strip(),
                "telegram_base_url": self.telegram_base_url_var.get().strip(),
                "telegram_allowed_users": self.telegram_allowed_users_var.get().strip(),
                "cloudflare_workers_token": self.cloudflare_workers_token_var.get().strip(),
                "cloudflare_proxy_url": self.cloudflare_proxy_url_var.get().strip(),
                "discord_token": self.discord_token_var.get().strip(),
                "discord_webhook_url": self.discord_webhook_url_var.get().strip(),
                "discord_allowed_users": self.discord_allowed_users_var.get().strip(),
                "line_token": self.line_token_var.get().strip(),
                "line_secret": self.line_secret_var.get().strip(),
                "notebooklm_cookie": self.notebooklm_cookie_var.get().strip(),
                "obsidian_url": self.obsidian_url_var.get().strip() or "http://127.0.0.1:27124",
                "obsidian_token": self.obsidian_token_var.get().strip(),
                "obsidian_email": self.obsidian_email_var.get().strip(),
                "obsidian_password": self.obsidian_password_var.get().strip(),
                "obsidian_vault": self.obsidian_vault_var.get().strip(),
                "obsidian_passphrase": self.obsidian_passphrase_var.get().strip(),
                "gateway_token": self.gateway_token_var.get().strip() or "admin123",
            }
            with open("token.json", "w", encoding="utf-8") as f:
                json.dump(token_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.log(f"⚠️ 無法儲存 token.json: {e}")

    # ── Deploy Flow ──────────────────────────────────────────

    def _start_deploy(self) -> None:
        if self._deploying:
            self.log("部署正在進行中，請等待完成。")
            return

        token = self.hf_token_var.get().strip()
        repo_id = self.repo_id_var.get().strip()

        # 如果使用者貼了 HF Token，但還沒驗證 token（此時 repo_id 是預設的驗證提示字串或是空的）
        if token and (not repo_id or "請點擊驗證" in repo_id):
            self.log("偵測到尚未驗證 Token，正在自動驗證並取得 Space 專案名稱...")
            self._deploying = True
            self.deploy_btn.configure(state="disabled", bg=Colors.TEXT_MUTED)
            self.step_tracker.reset_all()
            self.progress_var.set(0)
            self.status_label.configure(text="驗證 Token 中...", fg=Colors.STATUS_RUNNING)
            self.online_status_label.configure(text="")

            def auto_verify_and_deploy():
                try:
                    from huggingface_hub import whoami
                    info = whoami(token=token)
                    username = info.get("name", "未知")
                    auth = info.get("auth", {})
                    role = "unknown"
                    if isinstance(auth, dict) and "accessToken" in auth:
                        role = auth["accessToken"].get("role", "unknown")

                    self.log(f"✅ 自動驗證成功！使用者名稱：{username}，權限角色：{role}")

                    detected_repo = f"{username}/hermes-agent-space"
                    self.repo_id_var.set(detected_repo)
                    self.log(f"  已自動設定專案名稱：{detected_repo}")

                    if role != "write":
                        self.log("⚠️ 警告：偵測到此 Token 可能不是『Write』權限。若無法寫入 Space，請至 HF 重新建立 Token。")

                    # 儲存 Token
                    self._save_tokens()

                    # 執行部署
                    cfg = self._get_config()
                    self._run_deploy(cfg)
                except Exception as e:
                    self.log(f"❌ 自動驗證失敗：{e}")
                    self.after(0, lambda: messagebox.showerror("驗證失敗", f"自動驗證 Token 失敗，無法繼續部署：\n{e}"))
                    self._deploying = False
                    self.after(0, lambda: self.deploy_btn.configure(state="normal", bg=Colors.BTN_PRIMARY))
                    self.after(0, lambda: self.status_label.configure(text="部署終止", fg=Colors.STATUS_ERROR))

            self._run_async(auto_verify_and_deploy)
            return

        cfg = self._get_config()
        errors = cfg.validate()
        if errors:
            messagebox.showwarning("請修正", "\n".join(errors))
            return

        # 儲存 Token 到 token.json
        self._save_tokens()

        self._deploying = True
        self.deploy_btn.configure(state="disabled", bg=Colors.TEXT_MUTED)
        self.step_tracker.reset_all()
        self.progress_var.set(0)
        self.status_label.configure(text="部署中...", fg=Colors.STATUS_RUNNING)
        self.online_status_label.configure(text="")

        self._run_async(lambda: self._run_deploy(cfg))

    def _run_deploy(self, cfg: DeployConfig) -> None:
        try:
            deployer = Deployer(
                cfg=cfg,
                log=self.log,
                on_step_change=self._on_step_change_safe,
                on_progress=self._on_progress_safe,
                ask_user_to_complete_oauth=self._ask_oauth,
            )

            success = deployer.run_full_deploy()

            if success:
                self.log(f"\n🎉 本地打包與上傳完成！")
                self.log(f"🔗 Hugging Face Space 網址：{cfg.space_url}")
                self.log("\n💡 正在等待 Hugging Face 雲端建置與啟動 (通常需要 1~3 分鐘)...")
                self._update_status("⏳ 等待雲端建置與啟動...", Colors.STATUS_RUNNING)
                self.after(0, lambda: self.online_status_label.configure(text="⏳ 雲端建置啟動中...", fg=Colors.STATUS_RUNNING))

                from huggingface_hub import HfApi
                import time
                api = HfApi(token=cfg.hf_token or None)
                
                last_stage = None
                start_time = time.time()
                timeout = 600  # 10分鐘超時
                
                while (time.time() - start_time) < timeout:
                    try:
                        runtime = api.get_space_runtime(repo_id=cfg.repo_id)
                        stage = runtime.stage
                        
                        if stage != last_stage:
                            last_stage = stage
                            self.log(f"☁️ 雲端狀態更新：{stage}")
                            self._update_status(f"雲端部署狀態：{stage}", Colors.STATUS_RUNNING)
                            
                        if stage in ["RUNNING", "RUNNING_WITH_WARNINGS"]:
                            self.log(f"\n🎉 Hugging Face Space 已成功啟動並運行！")
                            self.log(f"🔗 網址：{cfg.space_url}")
                            self._update_status("部署完成 - 系統上線可用", Colors.STATUS_SUCCESS)
                            self.after(0, lambda: self.online_status_label.configure(text="🎉 系統上線可用", fg=Colors.STATUS_SUCCESS))
                            
                            # 發送部署完成通知
                            notify_logs = send_deploy_notification(cfg, True, "Space 已成功啟動並運行！系統上線可用。")
                            for line in notify_logs:
                                self.log(line)
                                
                            self.after(0, lambda: messagebox.showinfo("部署完成", f"🎉 Space 部署完成且已成功運行！\n\n網址：{cfg.space_url}"))
                            self.after(500, lambda: webbrowser.open(cfg.space_url))
                            break
                        elif stage in ["BUILD_ERROR", "RUNTIME_ERROR", "CRASHED", "STOPPED", "PAUSED"]:
                            self.log(f"\n❌ 雲端部署失敗！最終狀態：{stage}")
                            self.log("\n💡 雲端建置與執行日誌查看命令：")
                            self.log(f"  [建置日誌 (Build)]:\n  curl -N -H \"Authorization: Bearer {cfg.hf_token}\" \"https://huggingface.co/api/spaces/{cfg.repo_id}/logs/build\"")
                            self.log(f"  [運行日誌 (Run)]:\n  curl -N -H \"Authorization: Bearer {cfg.hf_token}\" \"https://huggingface.co/api/spaces/{cfg.repo_id}/logs/run\"\n")
                            
                            self._update_status(f"部署失敗 ({stage})", Colors.STATUS_ERROR)
                            self.after(0, lambda: self.online_status_label.configure(text=f"❌ 部署失敗 ({stage})", fg=Colors.STATUS_ERROR))
                            
                            # 發送部署失敗通知
                            notify_logs = send_deploy_notification(cfg, False, f"Space 部署失敗，目前狀態為：{stage}")
                            for line in notify_logs:
                                self.log(line)
                            break
                    except Exception as e:
                        self.log(f"[查詢雲端狀態出錯: {e}，3 秒後重試...]")
                    
                    time.sleep(3)
                else:
                    self.log("\n⏳ 等待雲端啟動逾時。請手動至瀏覽器檢查狀態。")
                    self._update_status("逾時，請手動確認", Colors.STATUS_WARNING)
                    self.after(0, lambda: self.online_status_label.configure(text="⚠️ 等待雲端啟動逾時", fg=Colors.STATUS_WARNING))
            else:
                self._update_status("部署失敗，請查看 Log", Colors.STATUS_ERROR)
                self.after(0, lambda: self.online_status_label.configure(text="❌ 部署失敗", fg=Colors.STATUS_ERROR))
        finally:
            self._deploying = False
            self.after(0, lambda: self.deploy_btn.configure(state="normal", bg=Colors.BTN_PRIMARY))

    def _on_step_change_safe(self, step_name: str, status: StepStatus) -> None:
        self.after(0, lambda: self.step_tracker.update_step(step_name, status))

    def _on_progress_safe(self, current: int, total: int) -> None:
        pct = (current / total) * 100 if total > 0 else 0
        self.after(0, lambda: self.progress_var.set(pct))

    def _update_status(self, text: str, color: str) -> None:
        self.after(0, lambda: self.status_label.configure(text=text, fg=color))

    def _ask_oauth(self) -> None:
        self.log("⏸️ 等待你完成 OpenAI/Codex 授權...")
        self._update_status("等待 OAuth 授權...", Colors.STATUS_WARNING)
        try:
            messagebox.showinfo(
                "請完成 OpenAI / Codex 授權",
                "請看剛剛跳出的視窗：\n\n"
                "1. 它會給你登入網址或代碼\n"
                "2. 用瀏覽器登入 OpenAI / ChatGPT\n"
                "3. 授權完成後，回來按 OK\n\n"
                "⚠️ 還沒完成不要按 OK",
            )
        except Exception:
            pass

    # ── Individual Commands ──────────────────────────────────

    def _cmd_check_env(self):
        cfg = self._get_config()
        self.log("\n=== 檢查環境 ===")
        environment.check_environment(cfg.hermes_auth_path, cfg.codex_auth_path, self.log)

    def _cmd_install_hf(self):
        self.log("\n=== 安裝 huggingface_hub ===")
        hermes_ops.install_hf_hub(self.log)

    def _cmd_import_codex_auth(self):
        cfg = self._get_config()
        self.log("\n=== 偵測/匯入 Codex 授權 ===")
        ok = hermes_ops.import_codex_auth(
            cfg.hermes_auth_path,
            cfg.codex_auth_path,
            self.log,
        )
        if not ok:
            raise FileNotFoundError(
                f"找不到 Codex auth.json：{cfg.codex_auth_path}\n"
                "請先點『安裝/登入 Codex』完成登入，或確認 Codex auth 路徑是否正確。"
            )

    def _cmd_hf_login(self):
        cfg = self._get_config()
        self.log("\n=== HF 登入 ===")
        hf_ops.hf_login(cfg.hf_token, self.log)

    def _cmd_create_space(self):
        cfg = self._get_config()
        self.log("\n=== 建立 Space ===")
        hf_ops.create_space(cfg, self.log)

    def _cmd_codex_login(self):
        self.log("\n=== Codex CLI 登入 ===")
        hermes_ops.open_codex_login(self.log)

    def _cmd_check_auth(self):
        cfg = self._get_config()
        self.log("\n=== 檢查授權檔 ===")
        hermes_ops.check_auth_files(cfg.hermes_auth_path, cfg.codex_auth_path, self.log)

    def _cmd_gen_files(self):
        cfg = self._get_config()
        self.log("\n=== 產生 Space 檔案 ===")
        space_builder.generate_space_files(cfg, self.log)

    def _cmd_upload_secrets(self):
        cfg = self._get_config()
        self.log("\n=== 上傳 Secrets ===")
        hf_ops.upload_secrets_and_variables(cfg, self.log)

    def _cmd_upload_space(self):
        cfg = self._get_config()
        self.log("\n=== 上傳 Space ===")
        hf_ops.upload_space_files(cfg, self.log)

    def _cmd_restart_space(self):
        cfg = self._get_config()
        self.log("\n=== 重啟 Space ===")
        hf_ops.restart_space(cfg, self.log)

    def show_hf_log_monitor(self, cfg: DeployConfig) -> None:
        # Create a beautiful Toplevel window
        monitor = tk.Toplevel(self)
        monitor.title("🛸 Hugging Face Space 雲端部署日誌監控")
        monitor.geometry("750x555")
        monitor.configure(bg=Colors.BG_DARK)
        
        # Make it transient to main window
        monitor.transient(self)
        monitor.grab_set()

        # Custom header
        header = tk.Frame(monitor, bg=Colors.BG_CARD)
        header.pack(fill="x", padx=15, pady=(15, 10))
        
        tk.Label(header, text="🛸 Space 雲端建置與部署監控", bg=Colors.BG_CARD, fg=Colors.ACCENT_CYAN,
                 font=(Fonts.FAMILY[0], Fonts.SIZE_SUBTITLE, "bold")).pack(anchor="w", pady=(5, 2))
        
        status_frame = tk.Frame(header, bg=Colors.BG_CARD)
        status_frame.pack(fill="x", pady=2)
        
        tk.Label(status_frame, text="目前階段：", bg=Colors.BG_CARD, fg=Colors.TEXT_MUTED,
                 font=(Fonts.FAMILY[0], Fonts.SIZE_BODY)).pack(side="left")
        
        stage_label = tk.Label(status_frame, text="等待中...", bg=Colors.BG_CARD, fg=Colors.ACCENT_YELLOW,
                               font=(Fonts.FAMILY[0], Fonts.SIZE_BODY, "bold"))
        stage_label.pack(side="left")
        
        # Log Console
        console_frame = tk.Frame(monitor, bg=Colors.BG_DARK)
        console_frame.pack(fill="both", expand=True, padx=15, pady=5)
        
        from tkinter.scrolledtext import ScrolledText
        text_area = ScrolledText(console_frame, bg=Colors.BG_INPUT, fg=Colors.TEXT_PRIMARY,
                                 insertbackground=Colors.TEXT_PRIMARY, font=("Consolas", 10),
                                 state="disabled", relief="flat")
        text_area.pack(fill="both", expand=True)

        # Bottom Frame
        bottom = tk.Frame(monitor, bg=Colors.BG_DARK)
        bottom.pack(fill="x", padx=15, pady=15)
        
        close_btn = tk.Button(bottom, text="關閉監控並開啟網頁", state="disabled", bg=Colors.BTN_SECONDARY, fg=Colors.TEXT_MUTED,
                              relief="flat", font=(Fonts.FAMILY[0], Fonts.SIZE_BODY), cursor="arrow", bd=0, padx=15, pady=6)
        close_btn.pack(side="right")
        
        is_closed = False
        
        def on_window_close():
            nonlocal is_closed
            is_closed = True
            monitor.destroy()
            
        monitor.protocol("WM_DELETE_WINDOW", on_window_close)
        
        def is_closed_fn():
            return is_closed
        
        def write_log(line: str):
            if not is_closed:
                self.after(0, lambda: _safe_write(line))
            
        def _safe_write(line: str):
            if is_closed:
                return
            text_area.configure(state="normal")
            text_area.insert("end", line)
            text_area.see("end")
            text_area.configure(state="disabled")
            
        def update_stage(stage: str):
            if not is_closed:
                self.after(0, lambda: _safe_update(stage))
            
        def _safe_update(stage: str):
            if is_closed:
                return
            stage_colors = {
                "BUILDING": Colors.ACCENT_YELLOW,
                "DEPLOYING": Colors.ACCENT_CYAN,
                "RUNNING": Colors.STATUS_SUCCESS,
                "RUNNING_WITH_WARNINGS": Colors.STATUS_SUCCESS,
                "BUILD_ERROR": Colors.STATUS_ERROR,
                "RUNTIME_ERROR": Colors.STATUS_ERROR,
                "CRASHED": Colors.STATUS_ERROR,
            }
            color = stage_colors.get(stage, Colors.TEXT_PRIMARY)
            stage_label.configure(text=stage, fg=color)
            self.log(f"☁️ Remote Space Status: {stage}")
            
        def on_complete(success: bool, msg: str):
            if not is_closed:
                self.after(0, lambda: _safe_complete(success, msg))
            
        def _safe_complete(success: bool, msg: str):
            if is_closed:
                return
            close_btn.configure(state="normal", bg=Colors.BTN_PRIMARY, fg=Colors.TEXT_PRIMARY, cursor="hand2")
            
            def finish_action():
                if success:
                    webbrowser.open(cfg.space_url)
                monitor.destroy()
                
            close_btn.configure(command=finish_action)
            
            if success:
                messagebox.showinfo("部署完成", f"🎉 {msg}\n\nSpace 網址：{cfg.space_url}")
                webbrowser.open(cfg.space_url)
            else:
                messagebox.showerror("部署失敗", f"❌ {msg}\n\n請檢查日誌。")
                
        # Start background streaming task
        from huggingface_hub import HfApi
        api = HfApi(token=cfg.hf_token or None)
        
        import threading
        t = threading.Thread(
            target=stream_logs_task,
            args=(api, cfg, write_log, update_stage, on_complete, is_closed_fn),
            daemon=True
        )
        t.start()


def send_deploy_notification(cfg: DeployConfig, success: bool, status_msg: str) -> list[str]:
    """
    發送部署結果通知到配置的聊天軟體。
    回傳成功與失敗的訊息列表以供 logging。
    """
    import requests
    logs = []
    
    if cfg.tg_token:
        try:
            # 1. 取得更新以獲取使用者的 chat_id
            updates_url = f"https://api.telegram.org/bot{cfg.tg_token}/getUpdates"
            r = requests.get(updates_url, timeout=10).json()
            if not r.get("ok"):
                logs.append(f"❌ Telegram getUpdates 失敗: {r.get('description', '未知錯誤')}")
            else:
                chat_ids = set()
                for update in r.get("result", []):
                    if "message" in update and "chat" in update["message"]:
                        chat_ids.add(update["message"]["chat"]["id"])
                
                if not chat_ids:
                    logs.append("⚠️ 偵測到 Telegram Token，但近 24 小時無互動記錄 (getUpdates 為空)。請先在手機 Telegram 與 Bot 對話 (發送隨意訊息如 /start) 後重新部署，才能收到通知！")
                else:
                    status_emoji = "🟢" if success else "🔴"
                    msg_text = (
                        f"{status_emoji} *Hermes Space 部署通知* {status_emoji}\n\n"
                        f"• *專案 Repo*: `{cfg.repo_id}`\n"
                        f"• *部署結果*: {'成功運行' if success else '部署失敗'}\n"
                        f"• *詳細狀態*: {status_msg}\n"
                        f"• *Space 網址*: {cfg.space_url}"
                    )
                    
                    sent_count = 0
                    for cid in chat_ids:
                        send_url = f"https://api.telegram.org/bot{cfg.tg_token}/sendMessage"
                        send_resp = requests.post(send_url, json={
                            "chat_id": cid,
                            "text": msg_text,
                            "parse_mode": "Markdown"
                        }, timeout=10).json()
                        if send_resp.get("ok"):
                            sent_count += 1
                        else:
                            logs.append(f"❌ 傳送訊息至 chat_id {cid} 失敗: {send_resp.get('description')}")
                    
                    if sent_count > 0:
                        logs.append(f"✅ 已成功透過 Telegram Bot 發送部署通知給 {sent_count} 位使用者！")
        except Exception as e:
            logs.append(f"❌ Telegram 通知出錯: {e}")
            
    return logs


def stream_logs_task(api, cfg, write_log_cb, update_stage_cb, on_complete_cb, is_closed_fn):
    import time
    repo_id = cfg.repo_id
    last_stage = None
    build_streamed = False
    run_streamed = False
    
    # Wait a bit for HF to register the restart/deploy action
    time.sleep(5)
    
    while not is_closed_fn():
        try:
            runtime = api.get_space_runtime(repo_id=repo_id)
            stage = runtime.stage
            if stage != last_stage:
                last_stage = stage
                update_stage_cb(stage)
                
            if stage in ["RUNNING", "RUNNING_WITH_WARNINGS"]:
                # 發送部署成功通知
                notify_logs = send_deploy_notification(cfg, True, "Space 已成功啟動並運行！")
                for line in notify_logs:
                    write_log_cb(f"\n{line}\n")
                on_complete_cb(True, "Space 已成功啟動並運行！")
                break
            elif stage in ["BUILD_ERROR", "RUNTIME_ERROR", "CRASHED", "STOPPED", "PAUSED"]:
                # 發送部署失敗通知
                notify_logs = send_deploy_notification(cfg, False, f"Space 部署失敗，目前狀態為：{stage}")
                for line in notify_logs:
                    write_log_cb(f"\n{line}\n")
                on_complete_cb(False, f"Space 部署失敗，目前狀態為：{stage}")
                break
                
            # Stream logs
            if stage == "BUILDING" and not build_streamed:
                write_log_cb("\n--- 開始串流 Build 容器建置日誌 ---\n")
                try:
                    for line in api.fetch_space_logs(repo_id=repo_id, build=True, follow=True):
                        if is_closed_fn():
                            break
                        write_log_cb(line)
                except Exception as e:
                    write_log_cb(f"\n[Build Log Stream finished/interrupted: {e}]\n")
                build_streamed = True
                
            elif stage in ["DEPLOYING", "RUNNING"] and not run_streamed:
                write_log_cb("\n--- 開始串流 Runtime 執行日誌 ---\n")
                try:
                    for line in api.fetch_space_logs(repo_id=repo_id, build=False, follow=True):
                        if is_closed_fn():
                            break
                        write_log_cb(line)
                except Exception as e:
                    write_log_cb(f"\n[Runtime Log Stream finished/interrupted: {e}]\n")
                run_streamed = True
                
        except Exception as e:
            if not is_closed_fn():
                write_log_cb(f"\n[連線日誌錯誤: {e}，2 秒後重試...]\n")
            
        time.sleep(2)
