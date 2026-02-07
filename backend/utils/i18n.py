# -*- coding: utf-8 -*-
"""
国际化工具模块

提供多语言支持功能
"""

from typing import Dict, Any


def get_translation_dict() -> Dict[str, Dict[str, str]]:
    """获取翻译字典，直接返回硬编码的翻译内容，避免文件加载问题

    Returns:
        Dict[str, Dict[str, str]]: 翻译字典
    """
    return {
        "zh-CN": {"welcome": "欢迎使用量化交易系统", "current_locale": "当前语言"},
        "en-US": {
            "welcome": "Welcome to Quantitative Trading System",
            "current_locale": "Current Language",
        },
    }


def extract_lang(accept_language: str) -> str:
    """从Accept-Language头中提取语言代码

    Args:
        accept_language: Accept-Language头的值

    Returns:
        str: 提取的语言代码
    """
    if not accept_language:
        return "zh-CN"

    # 提取第一个语言代码
    lang = accept_language.split(",")[0].strip()
    # 标准化语言代码格式
    lang = lang.split(";")[0].replace("_", "-")
    # 确保返回的语言代码在支持列表中
    supported_langs = ["zh-CN", "en-US"]
    return lang if lang in supported_langs else "zh-CN"
