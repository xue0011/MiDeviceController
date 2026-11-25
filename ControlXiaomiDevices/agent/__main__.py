"""python -m agent —— 启动设备控制 Agent 的 HTTP 服务。"""

from __future__ import annotations

import uvicorn

from .api import app


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8020)


if __name__ == "__main__":
    main()
