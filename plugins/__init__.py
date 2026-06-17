"""
VM Management Panel - 第三方插件引擎

支持动态扫描、加载、启禁用第三方插件。
每个插件是一个 Python 模块，通过 Plugin 类暴露功能。
"""
import os
import sys
import json
import importlib
import inspect


class PluginBase:
    """插件基类 — 所有插件必须继承此类"""
    name = "base-plugin"
    version = "0.0.0"
    description = "Base plugin"
    author = "unknown"
    homepage = ""

    def register_routes(self, app):
        """注册 Flask 路由 — 子类覆盖"""
        pass

    def register_menu(self):
        """返回导航项列表: [(label, url, icon_class), ...]"""
        return []

    def get_status(self):
        """返回插件状态信息 dict"""
        return {
            "enabled": True,
            "metrics": {},
        }


class PluginManager:
    """插件管理器 — 扫描/加载/管理"""

    def __init__(self, plugin_dir=None):
        self.plugin_dir = plugin_dir or os.path.dirname(os.path.abspath(__file__))
        self.registry_file = os.path.join(self.plugin_dir, "registry.json")
        self._plugins = {}
        self._metadata = {}
        self._load_registry()

    # ── 注册表管理 ─────────────────────────────────────────

    def _load_registry(self):
        """加载启禁用状态"""
        if os.path.exists(self.registry_file):
            with open(self.registry_file) as f:
                self._metadata = json.load(f)
        else:
            self._metadata = {}

    def _save_registry(self):
        os.makedirs(os.path.dirname(self.registry_file), exist_ok=True)
        with open(self.registry_file, "w") as f:
            json.dump(self._metadata, f, indent=2)

    def is_enabled(self, name):
        return self._metadata.get(name, {}).get("enabled", True)

    def set_enabled(self, name, enabled=True):
        if name not in self._metadata:
            self._metadata[name] = {}
        self._metadata[name]["enabled"] = enabled
        self._save_registry()

    # ── 插件扫描 & 加载 ────────────────────────────────────

    def discover_plugins(self):
        """扫描 plugins/ 目录，发现所有插件模块"""
        discovered = {}
        plugin_dir = self.plugin_dir
        sys.path.insert(0, os.path.dirname(plugin_dir))

        # 扫描 plugins/builtins/
        builtins_dir = os.path.join(plugin_dir, "builtins")
        if os.path.exists(builtins_dir):
            for fname in sorted(os.listdir(builtins_dir)):
                if fname.endswith(".py") and not fname.startswith("_"):
                    mod_name = fname[:-3]
                    full_path = os.path.join(builtins_dir, fname)
                    discovered[mod_name] = full_path

        return discovered

    def load_plugin(self, mod_name, file_path):
        """加载单个插件"""
        try:
            spec = importlib.util.spec_from_file_location(mod_name, file_path)
            if spec is None:
                return None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            # 查找 Plugin 类
            for name, obj in inspect.getmembers(mod):
                if inspect.isclass(obj) and issubclass(obj, PluginBase) and obj is not PluginBase:
                    instance = obj()
                    if not self.is_enabled(instance.name):
                        instance._disabled = True
                    self._plugins[instance.name] = instance
                    # 确保注册表有记录
                    if instance.name not in self._metadata:
                        self._metadata[instance.name] = {"enabled": True}
                    self._save_registry()
                    return instance
            return None
        except Exception as e:
            print(f"[plugins] 加载 '{mod_name}' 失败: {e}")
            return None

    def load_all(self):
        """扫描并加载所有插件"""
        discovered = self.discover_plugins()
        loaded = []
        for name, path in discovered.items():
            inst = self.load_plugin(name, path)
            if inst:
                loaded.append(inst)
        return loaded

    def get_plugin(self, name):
        return self._plugins.get(name)

    def list_plugins(self):
        """列出所有插件及状态"""
        result = []
        for name, plugin in self._plugins.items():
            meta = self._metadata.get(name, {})
            try:
                status = plugin.get_status() if not getattr(plugin, '_disabled', False) else {}
            except Exception:
                status = {"error": "status check failed"}
            result.append({
                "name": plugin.name,
                "version": plugin.version,
                "description": plugin.description,
                "author": plugin.author,
                "homepage": plugin.homepage,
                "enabled": self.is_enabled(name),
                "status": status,
                "menu": plugin.register_menu() if hasattr(plugin, 'register_menu') else [],
            })
        return result

    def register_routes(self, app):
        """让所有已启用插件注册路由"""
        for name, plugin in self._plugins.items():
            if self.is_enabled(name) and not getattr(plugin, '_disabled', False):
                try:
                    plugin.register_routes(app)
                except Exception as e:
                    print(f"[plugins] '{name}' 注册路由失败: {e}")
