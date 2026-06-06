"""
Space project file builder.

從模板產生 Dockerfile、entrypoint.sh、app.py 等 Space 檔案。
"""

from __future__ import annotations

import pathlib
from typing import Callable

from app.config import DeployConfig


def generate_space_files(cfg: DeployConfig, log: Callable[[str], None]) -> None:
    """產生所有 Space 專案檔案."""
    project = cfg.project_dir
    project.mkdir(parents=True, exist_ok=True)

    if (project / "health-server.js").exists():
        log("  ✨ 偵測到 HuggingMes 專案結構，跳過檔案生成，保持重構後的最新代碼。")
        return

    log(f"  產生檔案到: {project}")

    templates_dir = pathlib.Path(__file__).parent.parent / "templates"

    files = {
        "README.md": _render_readme(cfg),
        "requirements.txt": _render_requirements(),
        "Dockerfile": _render_dockerfile(),
        "entrypoint.sh": _render_entrypoint(),
        "app.py": _render_app_py(),
        ".gitignore": _render_gitignore(),
        "README_LOCAL.md": _render_readme_local(cfg),
        "patch_hermes.py": _render_patch_hermes(),
    }

    for filename, content in files.items():
        filepath = project / filename
        filepath.write_text(content.lstrip(), encoding="utf-8", newline="\n")
        log(f"    ✅ {filename}")

    log("  ✅ 所有 Space 檔案產生完成")


def _render_readme(cfg: DeployConfig) -> str:
    return f"""
---
title: Hermes Agent Codex Auth
emoji: 🤖
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

Hermes Agent running on Hugging Face Docker Space using `{cfg.provider}` auth.
"""


def _render_requirements() -> str:
    return """
gradio
fastapi
uvicorn
httpx
websockets
python-multipart
notebooklm-py
hermes-agent @ https://github.com/NousResearch/hermes-agent/archive/refs/heads/main.zip
"""


def _render_dockerfile() -> str:
    return """FROM node:20-slim AS frontend-builder
WORKDIR /build
RUN apt-get update && apt-get install -y git
RUN git clone https://github.com/NousResearch/hermes-agent.git .
WORKDIR /build/web
RUN npm install
RUN npm run build

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/tmp/huggingface
ENV HOME=/tmp
ENV HERMES_HOME=/tmp/.hermes
ENV HERMES_WEB_DIST=/app/web_dist

WORKDIR /app

# Install System Dependencies including Node.js (for obsidian-headless), DBus, gnome-keyring, and libsecret
RUN apt-get update && apt-get install -y \\
    git \\
    curl \\
    build-essential \\
    ripgrep \\
    ffmpeg \\
    bash \\
    dbus-x11 \\
    gnome-keyring \\
    libsecret-1-0 \\
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \\
    && apt-get install -y nodejs \\
    && npm install -g obsidian-headless \\
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade pip \\
    && pip install --no-cache-dir -r requirements.txt

COPY --from=frontend-builder /build/hermes_cli/web_dist /app/web_dist
COPY --from=frontend-builder /build/ui-tui /usr/local/lib/python3.11/site-packages/ui-tui

# Pre-install TUI node dependencies and grant full permissions to bypass runtime permission blocks
RUN cd /usr/local/lib/python3.11/site-packages/ui-tui && npm install && chmod -R 777 /usr/local/lib/python3.11/site-packages/ui-tui

COPY . /app/

RUN chmod +x /app/entrypoint.sh

EXPOSE 7860

CMD ["/app/entrypoint.sh"]
"""


def _render_entrypoint() -> str:
    return r'''#!/usr/bin/env bash
set -euo pipefail

export HOME="${HOME:-/tmp}"
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
mkdir -p "$HERMES_HOME"
mkdir -p "$HOME/.codex"

# Ensure OBSIDIAN_API_KEY has a value so that the Obsidian feature is always enabled
if [ -z "${OBSIDIAN_API_KEY:-}" ]; then
    export OBSIDIAN_API_KEY="hermes-default-key"
fi

# Patch hermes_cli to support environment variable credentials and troubleshooting logs
python /app/patch_hermes.py

python - <<'PYDECODE'
import base64
import json
import os
from pathlib import Path

home = Path(os.environ.get("HOME", "/tmp"))
hermes_home = Path(os.environ.get("HERMES_HOME", str(home / ".hermes")))
hermes_home.mkdir(parents=True, exist_ok=True)
codex_dir = home / ".codex"
codex_dir.mkdir(parents=True, exist_ok=True)

# ── Validate auth environment variables ──
hermes_b64 = os.environ.get("HERMES_AUTH_JSON_B64", "")
codex_b64 = os.environ.get("CODEX_AUTH_JSON_B64", "")

if hermes_b64 or codex_b64:
    print("Troubleshooting Auth: Detected credentials in environment variables. Hermes will read them directly from memory (no files in /tmp).")
else:
    print("Troubleshooting Auth: WARNING: Neither HERMES_AUTH_JSON_B64 nor CODEX_AUTH_JSON_B64 is set. Hermes openai-codex auth will fail.")

# 設定初始記憶與系統提示 (指向 NotebookLM / Obsidian)
instructions = []
if os.environ.get("NOTEBOOKLM_COOKIE"):
    instructions.append("- 💡 Google NotebookLM 已整合：你的一開始記憶/背景知識庫已指向 Google NotebookLM，請優先利用 NotebookLM-py API 讀取並檢索相關參考文件以增進回答準確度。")
if os.environ.get("OBSIDIAN_API_KEY"):
    obsidian_url = os.environ.get("OBSIDIAN_API_URL", "http://127.0.0.1:27124")
    instructions.append(f"- 💡 Obsidian 筆記庫已整合：你的一開始記憶/背景知識庫已指向 Obsidian 個人筆記本（網址：{obsidian_url}），你可以使用 Local REST API 讀取、搜尋或新增筆記。")

if instructions:
    content = "# 初始記憶與外部知識庫設定\\n\\n偵測到已配置外部知識庫：\\n\\n" + "\\n".join(instructions) + "\\n\\n請在處理任務時善用上述外部記憶與知識庫，保持上下文一致性。"
    for filename in [".hermes.md", "AGENTS.md"]:
        try:
            with open(f"/app/{filename}", "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Generated {filename} initial memory file pointing to external databases")
        except Exception as e:
            print(f"Failed to write {filename}: {e}")
PYDECODE

cat > "$HERMES_HOME/config.yaml" <<EOF
model:
  provider: ${HERMES_PROVIDER:-openai-codex}
  default: ${HERMES_MODEL:-gpt-5.5}
  context_length: ${HERMES_CONTEXT_LENGTH:-1000000}

delegation:
  provider: ${HERMES_PROVIDER:-openai-codex}
  model: ${HERMES_MODEL:-gpt-5.5}
  context_length: ${HERMES_CONTEXT_LENGTH:-1000000}

security:
  redact_secrets: true
EOF

# Initialize DBus session bus if not already running
if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    eval $(dbus-launch --sh-syntax)
    export DBUS_SESSION_BUS_ADDRESS
fi

# Unlock / create default keyring
echo "" | gnome-keyring-daemon --unlock --components=secrets &

# If Obsidian sync credentials are provided, login and start syncing in background
if [ -n "${OBSIDIAN_EMAIL:-}" ] && [ -n "${OBSIDIAN_PASSWORD:-}" ] && [ -n "${OBSIDIAN_VAULT:-}" ]; then
    echo "🔑 Setting up headless Obsidian Sync..."
    mkdir -p /tmp/obsidian_vault
    
    # Run ob login
    ob login --email "$OBSIDIAN_EMAIL" --password "$OBSIDIAN_PASSWORD" || echo "⚠️ ob login failed"
    
    # Run ob sync-setup
    if [ -n "${OBSIDIAN_PASSPHRASE:-}" ]; then
        ob sync-setup --vault "$OBSIDIAN_VAULT" --path /tmp/obsidian_vault --passphrase "$OBSIDIAN_PASSPHRASE" || echo "⚠️ ob sync-setup failed"
    else
        ob sync-setup --vault "$OBSIDIAN_VAULT" --path /tmp/obsidian_vault || echo "⚠️ ob sync-setup failed"
    fi
    
    # Start continuous sync
    echo "🔄 Starting background continuous Obsidian Sync..."
    ob sync --path /tmp/obsidian_vault --continuous &
fi

exec python /app/app.py
'''


def _render_app_py() -> str:
    return r'''
import os
import subprocess
import time
import asyncio
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
import httpx
import uvicorn

app = FastAPI()

SPACE_PASSWORD = os.getenv("SPACE_PASSWORD", "admin123")
TARGET_URL = "http://127.0.0.1:9119"

# Start the hermes dashboard in the background
subprocess.Popen([
    "hermes", "dashboard",
    "--port", "9119",
    "--host", "127.0.0.1",
    "--no-open"
])

# Wait for it to start
time.sleep(3)

# Start the hermes gateway (always enabled to support API server and message bots)
os.environ["API_SERVER_ENABLED"] = "true"
if not os.getenv("API_SERVER_KEY"):
    os.environ["API_SERVER_KEY"] = "hermes-api-key"
os.environ["API_SERVER_HOST"] = "127.0.0.1"
os.environ["API_SERVER_PORT"] = "8642"

# Bypassing the Telegram/Discord pairing approval requirement for convenience
os.environ["GATEWAY_ALLOW_ALL_USERS"] = "true"

subprocess.Popen([
    "hermes", "gateway", "run"
])

# Start mock Obsidian Local REST API server on port 27124 if configured
def run_obsidian_mock_server():
    from fastapi import FastAPI, Header, HTTPException
    import shutil
    import re

    obsidian_app = FastAPI()
    vault_path = "/tmp/obsidian_vault"
    api_key = os.getenv("OBSIDIAN_API_KEY", "")

    def check_auth(authorization: str = Header(None)):
        if api_key:
            expected = f"Bearer {api_key}"
            if not authorization or authorization != expected:
                raise HTTPException(status_code=401, detail="Unauthorized")

    @obsidian_app.get("/")
    def status(authorization: str = Header(None)):
        check_auth(authorization)
        return {"status": "OK", "authenticated": True, "vault": vault_path}

    @obsidian_app.get("/active")
    def get_active(authorization: str = Header(None)):
        check_auth(authorization)
        return {"path": ""}

    @obsidian_app.get("/vault/{path:path}")
    def read_file(path: str, authorization: str = Header(None)):
        check_auth(authorization)
        full_path = os.path.join(vault_path, path)
        if not os.path.exists(full_path) or os.path.isdir(full_path):
            raise HTTPException(status_code=404, detail="File not found")
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            return Response(content=content, media_type="text/markdown")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @obsidian_app.put("/vault/{path:path}")
    async def write_file(path: str, request: Request, authorization: str = Header(None)):
        check_auth(authorization)
        full_path = os.path.join(vault_path, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        content = await request.body()
        try:
            with open(full_path, "wb") as f:
                f.write(content)
            return Response(status_code=204)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @obsidian_app.patch("/vault/{path:path}")
    async def append_file(path: str, request: Request, authorization: str = Header(None)):
        check_auth(authorization)
        full_path = os.path.join(vault_path, path)
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="File not found")
        content = await request.body()
        try:
            with open(full_path, "ab") as f:
                f.write(content)
            return Response(status_code=204)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @obsidian_app.delete("/vault/{path:path}")
    def delete_file(path: str, authorization: str = Header(None)):
        check_auth(authorization)
        full_path = os.path.join(vault_path, path)
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="File not found")
        try:
            if os.path.isdir(full_path):
                shutil.rmtree(full_path)
            else:
                os.remove(full_path)
            return Response(status_code=204)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @obsidian_app.post("/search")
    async def search_vault(request: Request, authorization: str = Header(None)):
        check_auth(authorization)
        body = await request.json()
        query = body.get("query", "")
        results = []
        if query:
            for root, dirs, files in os.walk(vault_path):
                for file in files:
                    if file.endswith(".md"):
                        fpath = os.path.join(root, file)
                        rel_path = os.path.relpath(fpath, vault_path).replace("\\", "/")
                        try:
                            with open(fpath, "r", encoding="utf-8") as f:
                                text = f.read()
                            if re.search(query, text, re.IGNORECASE):
                                matches = []
                                for idx, line in enumerate(text.splitlines()):
                                    if re.search(query, line, re.IGNORECASE):
                                        matches.append({"line": idx + 1, "match": line})
                                results.append({"filename": rel_path, "matches": matches})
                        except Exception:
                            pass
        return results

    uvicorn.run(obsidian_app, host="127.0.0.1", port=27124)

# Always run Obsidian Mock Server to ensure the tool is enabled
import threading
if not os.getenv("OBSIDIAN_API_KEY"):
    os.environ["OBSIDIAN_API_KEY"] = "hermes-default-key"
threading.Thread(target=run_obsidian_mock_server, daemon=True).start()

import hashlib

def get_expected_cookie_value() -> str:
    return hashlib.sha256(SPACE_PASSWORD.encode("utf-8")).hexdigest()

# Styled login page
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Hermes Agent Dashboard - Login</title>
    <style>
        body {
            background-color: #0f172a;
            color: #f1f5f9;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }
        .card {
            background-color: #1e293b;
            padding: 2.5rem;
            border-radius: 12px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.3);
            width: 100%;
            max-width: 400px;
            text-align: center;
            border: 1px solid #334155;
        }
        h2 {
            margin-top: 0;
            color: #38bdf8;
            font-size: 1.75rem;
            margin-bottom: 0.5rem;
        }
        p {
            color: #94a3b8;
            font-size: 0.875rem;
            margin-bottom: 2rem;
        }
        input[type="password"] {
            width: 100%;
            padding: 0.75rem;
            margin-bottom: 1.25rem;
            border: 1px solid #475569;
            background-color: #0f172a;
            color: #f1f5f9;
            border-radius: 6px;
            box-sizing: border-box;
            font-size: 1rem;
        }
        input[type="password"]:focus {
            outline: none;
            border-color: #38bdf8;
            box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.2);
        }
        button {
            width: 100%;
            padding: 0.75rem;
            background-color: #0284c7;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: background-color 0.2s;
        }
        button:hover {
            background-color: #0369a1;
        }
        .error {
            color: #f87171;
            font-size: 0.875rem;
            margin-bottom: 1rem;
        }
    </style>
</head>
<body>
    <div class="card">
        <h2>🚀 Hermes Dashboard</h2>
        <p>此 Space 已啟用安全密碼驗證，請輸入密碼以存取資訊。</p>
        <form method="post" action="/login">
            {error_msg}
            <input type="password" name="password" placeholder="請輸入密碼" required autofocus>
            <button type="submit">登入</button>
        </form>
    </div>
</body>
</html>
"""

@app.get("/login")
def get_login():
    if not SPACE_PASSWORD:
        return RedirectResponse(url="/")
    return HTMLResponse(content=LOGIN_HTML.replace("{error_msg}", ""))

@app.post("/login")
async def post_login(request: Request):
    if not SPACE_PASSWORD:
        return RedirectResponse(url="/")
    form = await request.form()
    password = form.get("password")
    if password == SPACE_PASSWORD:
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie("space_session", get_expected_cookie_value(), max_age=86400 * 7, httponly=True, samesite="none", secure=True)
        return response
    else:
        return HTMLResponse(content=LOGIN_HTML.replace(
            "{error_msg}", "<div class='error'>❌ 密碼錯誤，請重新輸入</div>"
        ))

# Public Ping endpoint for Uptime Robot (defined before proxy routes)
@app.get("/ping")
def ping():
    return {"status": "ok", "message": "pong"}

# Reverse proxy HTTP requests with 60-second read timeout
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy_http(request: Request, path: str):
    if SPACE_PASSWORD:
        token = request.cookies.get("space_session")
        if token != get_expected_cookie_value():
            return RedirectResponse(url="/login")

    url = f"{TARGET_URL}/{path}"
    query = request.url.query
    if query:
        url += f"?{query}"

    headers = dict(request.headers)
    headers.pop("host", None)

    async with httpx.AsyncClient(timeout=60.0) as client:
        req = client.build_request(
            method=request.method,
            url=url,
            headers=headers,
            content=await request.body()
        )
        resp = await client.send(req)
        
        exclude_headers = ["content-encoding", "content-length", "transfer-encoding", "connection"]
        resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in exclude_headers}
        
        return Response(content=resp.content, status_code=resp.status_code, headers=resp_headers)

# Reverse proxy WebSockets
@app.websocket("/{path:path}")
async def proxy_websocket(websocket: WebSocket, path: str):
    if SPACE_PASSWORD:
        token = websocket.cookies.get("space_session")
        if token != get_expected_cookie_value():
            await websocket.close(code=1008)
            return

    await websocket.accept()
    
    ws_target = f"ws://127.0.0.1:9119/{path}"
    query = websocket.url.query
    if query:
        ws_target += f"?{query}"
        
    import websockets as ws_lib
    try:
        async with ws_lib.connect(ws_target) as target_ws:
            async def forward_to_target():
                try:
                    while True:
                        data = await websocket.receive_text()
                        await target_ws.send(data)
                except Exception:
                    pass

            async def forward_to_client():
                try:
                    while True:
                        data = await target_ws.recv()
                        await websocket.send_text(data)
                except Exception:
                    pass

            await asyncio.gather(forward_to_target(), forward_to_client())
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
'''


def _render_gitignore() -> str:
    return """
__pycache__/
*.pyc
.venv/
venv/
*.log
.hf-secrets
.env
*.json
"""


def _render_readme_local(cfg: DeployConfig) -> str:
    return f"""
# Hermes Agent HF Space 專案（自動產生）

Repo: `{cfg.repo_id}`

## 安全注意

- 不要把 `~/.hermes/auth.json` 或 `~/.codex/auth.json` 放進這個資料夾。
- 不要 commit HF token、OpenAI token、ChatGPT/Codex auth 檔。
- OAuth auth 會以 base64 存進 Hugging Face Space Secret：`HERMES_AUTH_JSON_B64`。

## Space Variables

- `HERMES_PROVIDER={cfg.provider}`
- `HERMES_MODEL={cfg.model}`
- `HERMES_CONTEXT_LENGTH=1000000`

## Space Secret

- `HERMES_AUTH_JSON_B64`: 由本機 `~/.hermes/auth.json` 轉換。
- `CODEX_AUTH_JSON_B64`: 可選，只有使用 Codex CLI app-server runtime 時需要。
"""


def _render_patch_hermes() -> str:
    return r'''import os
import base64
import json
import logging
from pathlib import Path
import hermes_cli.auth as auth

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def patch_auth_file():
    path = Path(auth.__file__)
    print(f"[Patch] Locating auth.py at: {path}")
    content = path.read_text(encoding="utf-8")

    # 1. Patch _load_auth_store
    start_load = content.find("def _load_auth_store(")
    start_save = content.find("def _save_auth_store(")
    if start_load == -1 or start_save == -1:
        print("[Patch] ERROR: Could not locate _load_auth_store or _save_auth_store boundaries.")
        return False

    new_load_auth_store = """def _load_auth_store(auth_file: Optional[Path] = None) -> Dict[str, Any]:
    # Try reading from environment variables first (no physical files in /tmp required!)
    for env_name in ("HERMES_AUTH_JSON_B64", "CODEX_AUTH_JSON_B64"):
        val = os.getenv(env_name, "").strip()
        if val:
            try:
                decoded = base64.b64decode(val).decode("utf-8")
                data = json.loads(decoded)
                if isinstance(data, dict):
                    # Check format: bare Codex format has "tokens" but not "providers"
                    if "tokens" in data and "providers" not in data:
                        logger.info(
                            "Troubleshooting Auth: Found bare Codex format in env var %s. "
                            "Nesting under 'openai-codex' provider.",
                            env_name
                        )
                        return {
                            "version": AUTH_STORE_VERSION,
                            "providers": {
                                "openai-codex": {
                                    "tokens": data["tokens"],
                                    "auth_mode": "chatgpt"
                                }
                            },
                            "active_provider": "openai-codex"
                        }
                    else:
                        logger.info(
                            "Troubleshooting Auth: Loaded standard Hermes auth store directly "
                            "from env var %s.",
                            env_name
                        )
                        data.setdefault("version", AUTH_STORE_VERSION)
                        data.setdefault("providers", {})
                        return data
            except Exception as e:
                logger.error(
                    "Troubleshooting Auth: Failed to parse auth from env var %s: %s",
                    env_name, e
                )

    auth_file = auth_file or _auth_file_path()
    if not auth_file.exists():
        logger.debug("Troubleshooting Auth: Auth file %s does not exist.", auth_file)
        return {"version": AUTH_STORE_VERSION, "providers": {}}

    try:
        raw = json.loads(auth_file.read_text())
    except Exception as exc:
        corrupt_path = auth_file.with_suffix(".json.corrupt")
        try:
            import shutil
            shutil.copy2(auth_file, corrupt_path)
        except Exception:
            pass
        logger.warning(
            "auth: failed to parse %s (%s) — starting with empty store. "
            "Corrupt file preserved at %s",
            auth_file, exc, corrupt_path,
        )
        return {"version": AUTH_STORE_VERSION, "providers": {}}

    if isinstance(raw, dict):
        if "tokens" in raw and "providers" not in raw:
            logger.info("Troubleshooting Auth: Found bare Codex format in auth file. Converting.")
            return {
                "version": AUTH_STORE_VERSION,
                "providers": {
                    "openai-codex": {
                        "tokens": raw["tokens"],
                        "auth_mode": "chatgpt"
                    }
                },
                "active_provider": "openai-codex"
            }
        
        if (
            isinstance(raw.get("providers"), dict)
            or isinstance(raw.get("credential_pool"), dict)
        ):
            raw.setdefault("providers", {})
            return raw

    # Migrate from PR's "systems" format if present
    if isinstance(raw, dict) and isinstance(raw.get("systems"), dict):
        systems = raw["systems"]
        providers = {}
        if "nous_portal" in systems:
            providers["nous"] = systems["nous_portal"]
        return {"version": AUTH_STORE_VERSION, "providers": providers,
                "active_provider": "nous" if providers else None}

"""
    content = content[:start_load] + new_load_auth_store + "\n\n" + content[start_save:]

    # 2. Patch resolve_codex_runtime_credentials
    start_resolve = content.find("def resolve_codex_runtime_credentials(")
    start_helpers = content.find("def _pool_codex_access_token()", start_resolve)
    if start_resolve == -1 or start_helpers == -1:
        print("[Patch] ERROR: Could not locate resolve_codex_runtime_credentials boundaries.")
        return False

    new_resolve_codex = """def resolve_codex_runtime_credentials(
    *,
    force_refresh: bool = False,
    refresh_if_expiring: bool = True,
    refresh_skew_seconds: int = CODEX_ACCESS_TOKEN_REFRESH_SKEW_SECONDS,
) -> Dict[str, Any]:
    \"\"\"Resolve runtime credentials from Hermes's own Codex token store.

    Falls back to the credential pool when the singleton (``providers.openai-codex.tokens``)
    has no usable access_token but the pool (``credential_pool.openai-codex``) does. This
    closes the divergence between the chat path (singleton-only via this function) and
    the auxiliary path (pool-first via ``_read_codex_access_token``). Without this
    fallback, a user whose tokens live only in the pool — for example after a manual
    pool seed, a partial re-auth, or pool-only restoration from a backup — gets a bare
    HTTP 401 ``Missing Authentication header`` from the wire instead of a usable
    credential. See issue #32992.
    \"\"\"
    logger.info("Troubleshooting Codex Auth: Resolving runtime credentials...")
    try:
        data = _read_codex_tokens()
        logger.info("Troubleshooting Codex Auth: Read Codex tokens successfully from store.")
    except AuthError as exc:
        logger.info("Troubleshooting Codex Auth: No Codex tokens in main store: %s. Trying pool fallback...", exc)
        pool_token = _pool_codex_access_token()
        if pool_token:
            logger.info("Troubleshooting Codex Auth: Found usable access token in credential pool.")
            base_url = (
                os.getenv("HERMES_CODEX_BASE_URL", "").strip().rstrip("/")
                or DEFAULT_CODEX_BASE_URL
            )
            return {
                "provider": "openai-codex",
                "base_url": base_url,
                "api_key": pool_token,
                "source": "credential_pool",
                "last_refresh": None,
                "auth_mode": "chatgpt",
            }
        logger.error("Troubleshooting Codex Auth: Failed to resolve credentials. No tokens in store or pool.")
        raise

    tokens = dict(data["tokens"])
    access_token = str(tokens.get("access_token", "") or "").strip()
    refresh_timeout_seconds = float(os.getenv("HERMES_CODEX_REFRESH_TIMEOUT_SECONDS", "20"))

    should_refresh = bool(force_refresh)
    if (not should_refresh) and refresh_if_expiring:
        should_refresh = _codex_access_token_is_expiring(access_token, refresh_skew_seconds)
        logger.info("Troubleshooting Codex Auth: Checking token expiry... Needs refresh? %s", should_refresh)
    if should_refresh:
        # Re-read under lock to avoid racing with other Hermes processes
        with _auth_store_lock(timeout_seconds=max(float(AUTH_LOCK_TIMEOUT_SECONDS), refresh_timeout_seconds + 5.0)):
            data = _read_codex_tokens(_lock=False)
            tokens = dict(data["tokens"])
            access_token = str(tokens.get("access_token", "") or "").strip()

            should_refresh = bool(force_refresh)
            if (not should_refresh) and refresh_if_expiring:
                should_refresh = _codex_access_token_is_expiring(access_token, refresh_skew_seconds)

            if should_refresh:
                logger.info("Troubleshooting Codex Auth: Performing token refresh request...")
                try:
                    tokens = _refresh_codex_auth_tokens(tokens, refresh_timeout_seconds)
                    access_token = str(tokens.get("access_token", "") or "").strip()
                    logger.info("Troubleshooting Codex Auth: Token refresh succeeded.")
                except Exception as refresh_exc:
                    logger.error("Troubleshooting Codex Auth: Token refresh failed: %s", refresh_exc)
                    raise

    base_url = (
        os.getenv("HERMES_CODEX_BASE_URL", "").strip().rstrip("/")
        or DEFAULT_CODEX_BASE_URL
    )

    return {
        "provider": "openai-codex",
        "base_url": base_url,
        "api_key": access_token,
        "source": "hermes-auth-store",
        "last_refresh": data.get("last_refresh"),
        "auth_mode": "chatgpt",
    }

"""
    content = content[:start_resolve] + new_resolve_codex + "\n\n" + content[start_helpers:]

    path.write_text(content, encoding="utf-8")
    print("[Patch] Patched auth.py successfully!")
    return True

if __name__ == "__main__":
    patch_auth_file()
'''

