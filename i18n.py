"""
VM Management Panel - 国际化模块 (i18n)

轻量翻译引擎，基于 JSON 语言文件。
无需 Flask-Babel 编译步骤。
"""
import os
import json
from flask import session, request


class I18n:
    """翻译引擎 — 加载 JSON 语言包并提供 _() 快捷函数"""

    def __init__(self, locale_dir=None):
        self.locale_dir = locale_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "translations"
        )
        self._cache = {}

    def _load(self, lang):
        """加载一个语言包到缓存"""
        if lang in self._cache:
            return self._cache[lang]
        path = os.path.join(self.locale_dir, f"{lang}.json")
        if not os.path.exists(path):
            path = os.path.join(self.locale_dir, "zh.json")  # fallback
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._cache[lang] = json.load(f)
        except Exception:
            self._cache[lang] = {}
        return self._cache[lang]

    def gettext(self, key, lang=None, **kwargs):
        """翻译一个 key，支持 %(name)s 格式变量替换"""
        if lang is None:
            lang = self._detect_lang()
        translations = self._load(lang)
        text = translations.get(key, key)
        if kwargs:
            try:
                text = text % kwargs
            except (KeyError, TypeError):
                pass
        return text

    def _detect_lang(self):
        """检测当前语言：session > cookie > 浏览器 Accept-Language > zh"""
        try:
            # 1. session
            lang = session.get("lang", "")
            if lang in ("zh", "en"):
                return lang
            # 2. cookie
            lang = request.cookies.get("lang", "")
            if lang in ("zh", "en"):
                return lang
            # 3. Accept-Language
            accept = request.headers.get("Accept-Language", "")
            if accept.startswith("en"):
                return "en"
        except RuntimeError:
            # 不在请求上下文中
            pass
        return "zh"


# 全局单例
_i18n = I18n()


def _(key, **kwargs):
    """模板可使用的翻译函数 — 自动检测语言"""
    return _i18n.gettext(key, **kwargs)


def get_i18n():
    return _i18n
