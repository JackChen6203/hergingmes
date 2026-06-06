"""
Hermes Agent Hugging Face Space Desktop Deployer

此檔案位於 _internal/，由 .bat → .ps1 啟動。
"""

import sys
import pathlib

# 確保 _internal/ 在 sys.path 中，讓 app 套件可以 import
_internal_dir = pathlib.Path(__file__).parent.resolve()
if str(_internal_dir) not in sys.path:
    sys.path.insert(0, str(_internal_dir))

from app.main import main

if __name__ == "__main__":
    main()
