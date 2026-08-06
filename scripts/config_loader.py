#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置加载模块 - 从 config.json 读取统一配置
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def get_config_path() -> Path:
    """获取配置文件路径（与脚本同目录）"""
    return Path(__file__).parent.parent / "config.json"


def load_config() -> Dict[str, Any]:
    """加载配置文件"""
    config_path = get_config_path()
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在：{config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


# 平台配置
def get_platform_config() -> Dict[str, Any]:
    config = load_config()
    return config.get("platform", {})


def get_base_url() -> str:
    cfg = get_platform_config()
    return f"{cfg.get('base_url', 'https://iot-test.ninebot.com')}{cfg.get('ota_api_prefix', '/service/iot-ota-console-api')}"


def get_console_base_url() -> str:
    cfg = get_platform_config()
    return f"{cfg.get('base_url', 'https://iot-test.ninebot.com')}{cfg.get('console_api_prefix', '/service/iot-console-api')}"


def get_file_upload_url() -> str:
    cfg = get_platform_config()
    return f"{cfg.get('base_url', 'https://iot-test.ninebot.com')}{cfg.get('file_upload_prefix', '/service/file-upload')}"


def get_upload_host() -> str:
    cfg = get_platform_config()
    return cfg.get("upload_host", "https://file-upload-test.ninebot.com")


def get_s3_config() -> Dict[str, Any]:
    cfg = get_platform_config()
    return {
        "region": cfg.get("s3_region", "cn-northwest-1"),
        "bucket": cfg.get("s3_bucket", "file-upload-test"),
        "chunk_size": cfg.get("chunk_size", 5242880),
    }


# 代理配置
def get_proxy_config() -> Dict[str, str]:
    config = load_config()
    proxy = config.get("proxy", {}).get("socks5", "socks5h://127.0.0.1:1080")
    return {"http": proxy, "https": proxy}


# 认证配置
def get_auth_config() -> Dict[str, Any]:
    config = load_config()
    return config.get("auth", {})


def get_account() -> str:
    return get_auth_config().get("account", "dehao.zhang@ninebot.com")


def get_password() -> str:
    return get_auth_config().get("password", "")


def get_operate_user() -> str:
    return get_auth_config().get("operate_user", "dehao.zhang")


def get_cookie_file() -> Path:
    auth_cfg = get_auth_config()
    cookie_filename = auth_cfg.get("cookie_file", "ninebot_cookies.json")
    return Path(__file__).parent / cookie_filename


def get_auth_valid_seconds() -> int:
    return get_auth_config().get("auth_valid_seconds", 1800)


# 设备配置
def get_device_config() -> Dict[str, Any]:
    config = load_config()
    return config.get("device", {})


def get_default_serial() -> str:
    return get_device_config().get("default_serial", "A2TBVB2C27014459")


def get_ninebot_package() -> str:
    return get_device_config().get("ninebot_package", "com.ninebot.segway")


# 页面树配置
def get_page_tree() -> Dict[str, Any]:
    config = load_config()
    return config.get("page_tree", {})


# 模块映射
def get_module_mapping() -> Dict[str, Dict[str, str]]:
    config = load_config()
    return config.get("module_mapping", {})


def get_app_to_platform() -> Dict[str, str]:
    return get_module_mapping().get("app_to_platform", {})


def get_platform_to_app() -> Dict[str, str]:
    return get_module_mapping().get("platform_to_app", {})


# 测试
if __name__ == "__main__":
    print("配置文件路径:", get_config_path())
    print("BASE URL:", get_base_url())
    print("CONSOLE BASE URL:", get_console_base_url())
    print("S3 配置:", get_s3_config())
    print("代理配置:", get_proxy_config())
    print("账号:", get_account())
    print("默认设备序列号:", get_default_serial())
    print("页面树节点:", list(get_page_tree().keys()))
