"""
VM Management Panel - 端口转发插件

通过 iptables 管理 NAT 端口转发规则。
支持 TCP/UDP 协议，规则持久化到 JSON 文件。
"""
import os
import json
import subprocess
import threading
from flask import request
from plugins import PluginBase

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
RULES_FILE = os.path.join(CONFIG_DIR, "port_forward_rules.json")


class PortForwardManager:
    """端口转发管理器 — iptables NAT 规则"""

    def __init__(self):
        self._rules = []
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if os.path.exists(RULES_FILE):
            with open(RULES_FILE) as f:
                self._rules = json.load(f)
        else:
            # 默认示例规则
            self._rules = [
                {"id": 1, "proto": "tcp", "host_port": 2222, "vm_ip": "192.168.122.100",
                 "vm_port": 22, "remark": "SSH -> VM1", "enabled": True},
                {"id": 2, "proto": "tcp", "host_port": 8081, "vm_ip": "192.168.122.100",
                 "vm_port": 80, "remark": "HTTP -> VM1", "enabled": True},
            ]
            self._save()

    def _save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(RULES_FILE, "w") as f:
            json.dump(self._rules, f, indent=2)

    def _next_id(self):
        return max((r.get("id", 0) for r in self._rules), default=0) + 1

    def _apply_iptables(self, rule, add=True):
        """应用 iptables NAT 规则"""
        try:
            action = "-A" if add else "-D"
            cmd = [
                "iptables", "-t", "nat", action, "PREROUTING",
                "-p", rule["proto"],
                "--dport", str(rule["host_port"]),
                "-j", "DNAT",
                "--to-destination", f"{rule['vm_ip']}:{rule['vm_port']}",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            # 同时添加 FORWARD 规则
            fwd_cmd = [
                "iptables", action, "FORWARD",
                "-p", rule["proto"],
                "-d", rule["vm_ip"],
                "--dport", str(rule["vm_port"]),
                "-j", "ACCEPT",
            ]
            subprocess.run(fwd_cmd, capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # iptables 不可用 (模拟模式或容器)
            return True

    def list_rules(self):
        return self._rules

    def add_rule(self, proto, host_port, vm_ip, vm_port, remark="", enabled=True):
        with self._lock:
            rule = {
                "id": self._next_id(),
                "proto": proto,
                "host_port": int(host_port),
                "vm_ip": vm_ip,
                "vm_port": int(vm_port),
                "remark": remark,
                "enabled": enabled,
            }
            self._rules.append(rule)
            self._save()
        if enabled:
            self._apply_iptables(rule, add=True)
        return rule

    def delete_rule(self, rule_id):
        with self._lock:
            for r in self._rules:
                if r["id"] == rule_id:
                    self._rules.remove(r)
                    self._save()
                    if r.get("enabled"):
                        self._apply_iptables(r, add=False)
                    return {"success": True}
        return {"success": False, "error": "规则不存在"}

    def toggle_rule(self, rule_id, enabled):
        with self._lock:
            for r in self._rules:
                if r["id"] == rule_id:
                    r["enabled"] = enabled
                    self._save()
                    self._apply_iptables(r, add=enabled)
                    return {"success": True}
        return {"success": False, "error": "规则不存在"}


_pfm = PortForwardManager()


class Plugin(PluginBase):
    name = "port-forwarding"
    version = "1.0.0"
    description = "iptables NAT port forwarding — expose VM ports to external network"
    author = "VM Panel Team"

    def register_routes(self, app):

        @app.route("/api/plugins/port-forward/rules")
        def pf_list():
            return {"ok": True, "data": _pfm.list_rules()}, 200

        @app.route("/api/plugins/port-forward/rules", methods=["POST"])
        def pf_add():
            data = request.get_json() or {}
            required = ["host_port", "vm_ip", "vm_port"]
            for f in required:
                if f not in data:
                    return {"ok": False, "error": f"缺少字段: {f}"}, 400
            rule = _pfm.add_rule(
                proto=data.get("proto", "tcp"),
                host_port=data["host_port"],
                vm_ip=data["vm_ip"],
                vm_port=data["vm_port"],
                remark=data.get("remark", ""),
                enabled=data.get("enabled", True),
            )
            return {"ok": True, "data": rule}, 201

        @app.route("/api/plugins/port-forward/rules/<int:rule_id>", methods=["DELETE"])
        def pf_delete(rule_id):
            result = _pfm.delete_rule(rule_id)
            if result["success"]:
                return {"ok": True, "data": result}, 200
            return {"ok": False, "error": result["error"]}, 404

        @app.route("/api/plugins/port-forward/rules/<int:rule_id>/toggle", methods=["POST"])
        def pf_toggle(rule_id):
            data = request.get_json() or {}
            enabled = data.get("enabled", True)
            result = _pfm.toggle_rule(rule_id, enabled)
            if result["success"]:
                return {"ok": True, "data": {"enabled": enabled}}, 200
            return {"ok": False, "error": result["error"]}, 404

        @app.route("/plugins/port-forward")
        def pf_page():
            from flask import render_template
            return render_template("plugin_port_forward.html")

    def register_menu(self):
        return [("Port Forwarding", "/plugins/port-forward", "bi bi-router")]

    def get_status(self):
        rules = _pfm.list_rules()
        enabled = sum(1 for r in rules if r.get("enabled"))
        return {"enabled": True, "total": len(rules), "active": enabled}
