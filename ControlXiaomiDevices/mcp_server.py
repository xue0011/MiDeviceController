"""设备控制 MCP Server（stdio）—— 让任意 MCP 客户端（客服 Agent / Claude Desktop / Cursor）
用统一协议操作小米设备，而不是各自 import miio 脚本。

启动：
    python mcp_server.py

挂到 Claude Desktop / Cursor（claude_desktop_config.json 或 mcp.json）：
    {
      "mcpServers": {
        "device-control": {
          "command": "python",
          "args": ["E:/project/project3/MiDeviceController/ControlXiaomiDevices/mcp_server.py"]
        }
      }
    }
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from device_driver import DeviceError, get_service

mcp = FastMCP("xiaomi-device-control")


def _dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


@mcp.tool()
def list_devices() -> str:
    """列出已注册的小米设备（id、名称、类型、房间、支持能力）。"""
    return _dumps({"devices": get_service().list_devices()})


@mcp.tool()
def get_device_status(device_id: str) -> str:
    """查询单台设备的当前状态（开关、亮度、色温、净化器模式、AQI）。"""
    try:
        return _dumps(get_service().status(device_id))
    except DeviceError as exc:
        return _dumps({"ok": False, "error": str(exc)})


@mcp.tool()
def set_power(device_id: str, on: bool) -> str:
    """打开或关闭设备。on=true 打开，on=false 关闭。"""
    try:
        return _dumps(get_service().set_power(device_id, on))
    except DeviceError as exc:
        return _dumps({"ok": False, "error": str(exc)})


@mcp.tool()
def set_brightness(device_id: str, brightness: int) -> str:
    """设置灯光亮度，范围 1–100。"""
    try:
        return _dumps(get_service().set_brightness(device_id, brightness))
    except DeviceError as exc:
        return _dumps({"ok": False, "error": str(exc)})


@mcp.tool()
def set_color_temp(device_id: str, kelvin: int) -> str:
    """设置灯光色温，范围 1700–6500K（越小越暖）。"""
    try:
        return _dumps(get_service().set_color_temp(device_id, kelvin))
    except DeviceError as exc:
        return _dumps({"ok": False, "error": str(exc)})


@mcp.tool()
def set_purifier_mode(device_id: str, mode: str) -> str:
    """设置空气净化器模式：auto / silent / favorite / idle。"""
    try:
        return _dumps(get_service().set_mode(device_id, mode))
    except DeviceError as exc:
        return _dumps({"ok": False, "error": str(exc)})


@mcp.tool()
def set_purifier_favorite_level(device_id: str, level: int) -> str:
    """设置空气净化器收藏模式档位，范围 1–14。"""
    try:
        return _dumps(get_service().set_favorite_level(device_id, level))
    except DeviceError as exc:
        return _dumps({"ok": False, "error": str(exc)})


if __name__ == "__main__":
    mcp.run()
