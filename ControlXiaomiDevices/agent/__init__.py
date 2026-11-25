"""设备控制 Agent 包。

把仓库根目录塞进 sys.path，便于 `python -m agent` 直接 import device_driver。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
