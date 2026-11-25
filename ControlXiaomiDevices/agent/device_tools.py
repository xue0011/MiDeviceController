"""把 DeviceService 包装成 LangChain Tool —— Agent 侧统一用工具名调用，不直接碰 miio。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from device_driver import DeviceError, get_service


def _dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


@tool
def list_devices() -> str:
    """列出可用设备。"""
    return _dumps({"devices": get_service().list_devices()})


@tool
def get_device_status(device_id: str) -> str:
    """查询设备状态。device_id 形如 light-living。"""
    try:
        return _dumps(get_service().status(device_id))
    except DeviceError as exc:
        return _dumps({"ok": False, "error": str(exc)})


@tool
def set_power(device_id: str, on: bool) -> str:
    """开关设备。on=true 打开，false 关闭。"""
    try:
        return _dumps(get_service().set_power(device_id, on))
    except DeviceError as exc:
        return _dumps({"ok": False, "error": str(exc)})


@tool
def set_brightness(device_id: str, brightness: int) -> str:
    """设置亮度 1–100。"""
    try:
        return _dumps(get_service().set_brightness(device_id, brightness))
    except DeviceError as exc:
        return _dumps({"ok": False, "error": str(exc)})


@tool
def set_color_temp(device_id: str, kelvin: int) -> str:
    """设置色温 1700–6500K。"""
    try:
        return _dumps(get_service().set_color_temp(device_id, kelvin))
    except DeviceError as exc:
        return _dumps({"ok": False, "error": str(exc)})


@tool
def set_purifier_mode(device_id: str, mode: str) -> str:
    """净化器模式：auto / silent / favorite / idle。"""
    try:
        return _dumps(get_service().set_mode(device_id, mode))
    except DeviceError as exc:
        return _dumps({"ok": False, "error": str(exc)})


TOOLS = [
    list_devices,
    get_device_status,
    set_power,
    set_brightness,
    set_color_temp,
    set_purifier_mode,
]

TOOLS_BY_NAME = {t.name: t for t in TOOLS}
