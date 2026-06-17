
"""
VM Management Panel - 远程 Hypervisor 集成插件

统一接入:
  • Proxmox VE API  (via proxmoxer)
  • oVirt Engine API (via ovirt-engine-sdk4)
  • VMware vSphere   (via pyvmomi)

每个连接目标称为一个 "remote"，存储在 hypervisors.json 中。
"""
import os
import json
import threading
from datetime import datetime
from flask import request

from plugins import PluginBase

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
HYPERVISORS_FILE = os.path.join(CONFIG_DIR, "hypervisors.json")
LOCK = threading.Lock()


# ── 远程连接器基类 ────────────────────────────────────────

class BaseConnector:
    """每个远程平台的连接器基类"""
    type = "unknown"

    def __init__(self, config):
        self.config = config  # {name, host, port, user, password, ...}

    def connect(self):
        """建立连接，返回 True/False"""
        raise NotImplementedError

    def disconnect(self):
        raise NotImplementedError

    def get_host_info(self):
        """返回 {hostname, cpus, memory_total_mb, ...}"""
        raise NotImplementedError

    def list_vms(self):
        """返回 [{name, state, vcpu, memory_mb, ...}, ...]"""
        raise NotImplementedError

    def get_vm(self, name):
        raise NotImplementedError

    def start_vm(self, name):
        raise NotImplementedError

    def stop_vm(self, name):
        raise NotImplementedError

    def get_status(self):
        return {"connected": False, "error": "not implemented"}


# ── Proxmox VE 连接器 ──────────────────────────────────────

class ProxmoxConnector(BaseConnector):
    type = "proxmox"

    def connect(self):
        try:
            from proxmoxer import ProxmoxAPI
            cfg = self.config
            verify_ssl = cfg.get("verify_ssl", False)
            self._api = ProxmoxAPI(
                cfg["host"], user=cfg["user"],
                password=cfg["password"],
                verify_ssl=verify_ssl,
                port=cfg.get("port", 8006),
            )
            # 验证连接 — 获取节点列表
            self._nodes = self._api.nodes.get()
            self._connected = True
            return True
        except ImportError:
            self._connected = False
            self._error = "proxmoxer 未安装 (pip install proxmoxer)"
            return False
        except Exception as e:
            self._connected = False
            self._error = str(e)
            return False

    def disconnect(self):
        self._api = None
        self._connected = False

    def get_host_info(self):
        if not self._connected:
            return {"error": self._error}
        try:
            node = self._nodes[0]["node"]
            status = self._api.nodes(node).status.get()
            return {
                "hostname": status.get("hostname", node),
                "cpus": status.get("cpuinfo", {}).get("cpus", 0),
                "memory_total_mb": round(status.get("memory", {}).get("total", 0) / 1024 / 1024, 0),
                "memory_used_mb": round(status.get("memory", {}).get("used", 0) / 1024 / 1024, 0),
                "platform": "Proxmox VE",
                "node": node,
            }
        except Exception as e:
            return {"error": str(e)}

    def list_vms(self):
        if not self._connected:
            return []
        try:
            vms = []
            for node_info in self._nodes:
                node = node_info["node"]
                for vm in self._api.nodes(node).qemu.get():
                    vms.append({
                        "name": vm.get("name", f"vm-{vm['vmid']}"),
                        "vmid": vm["vmid"],
                        "state": "running" if vm["status"] == "running" else "shutoff",
                        "vcpu": vm.get("cpus", 0),
                        "memory_mb": round(vm.get("mem", 0) / 1024 / 1024, 0),
                        "disk_gb": round(vm.get("disk", 0) / 1024 / 1024 / 1024, 1),
                        "node": node,
                        "type": "qemu",
                        "platform": "proxmox",
                    })
                for vm in self._api.nodes(node).lxc.get():
                    vms.append({
                        "name": vm.get("name", f"ct-{vm['vmid']}"),
                        "vmid": vm["vmid"],
                        "state": "running" if vm["status"] == "running" else "shutoff",
                        "vcpu": vm.get("cpus", 0),
                        "memory_mb": round(vm.get("mem", 0) / 1024 / 1024, 0),
                        "disk_gb": round(vm.get("disk", 0) / 1024 / 1024 / 1024, 1),
                        "node": node,
                        "type": "lxc",
                        "platform": "proxmox",
                    })
            return vms
        except Exception as e:
            return [{"error": str(e)}]

    def get_vm(self, name):
        for vm in self.list_vms():
            if vm["name"] == name:
                return vm
        return None

    def start_vm(self, name):
        try:
            vm = self.get_vm(name)
            if not vm:
                return {"success": False, "error": f"VM '{name}' not found"}
            node = vm["node"]
            vmid = vm["vmid"]
            vtype = vm["type"]
            if vtype == "qemu":
                self._api.nodes(node).qemu(vmid).status.start.post()
            else:
                self._api.nodes(node).lxc(vmid).status.start.post()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def stop_vm(self, name):
        try:
            vm = self.get_vm(name)
            if not vm:
                return {"success": False, "error": f"VM '{name}' not found"}
            node = vm["node"]
            vmid = vm["vmid"]
            if vm["type"] == "qemu":
                self._api.nodes(node).qemu(vmid).status.shutdown.post()
            else:
                self._api.nodes(node).lxc(vmid).status.shutdown.post()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_status(self):
        if not self._connected:
            return {"connected": False, "error": getattr(self, "_error", "unknown")}
        try:
            vms = self.list_vms()
            running = sum(1 for v in vms if v.get("state") == "running")
            return {
                "connected": True,
                "type": "Proxmox VE",
                "host": self.config["host"],
                "nodes": len(self._nodes),
                "vms": len(vms),
                "running": running,
            }
        except Exception as e:
            return {"connected": True, "error": str(e)}


# ── oVirt 连接器 ──────────────────────────────────────────

class OvirtConnector(BaseConnector):
    type = "ovirt"

    def connect(self):
        try:
            import ovirtsdk4 as sdk
            cfg = self.config
            self._conn = sdk.Connection(
                url=f"https://{cfg['host']}:{cfg.get('port', 443)}/ovirt-engine/api",
                username=cfg["user"],
                password=cfg["password"],
                ca_file=cfg.get("ca_file", ""),
                insecure=cfg.get("insecure", True),
            )
            self._connected = True
            return True
        except ImportError:
            self._connected = False
            self._error = "ovirt-engine-sdk4 未安装"
            return False
        except Exception as e:
            self._connected = False
            self._error = str(e)
            return False

    def disconnect(self):
        if self._connected:
            self._conn.close()
        self._connected = False

    def get_host_info(self):
        try:
            hosts_svc = self._conn.system_service().hosts_service()
            hosts = hosts_svc.list()
            total_mem = max((h.memory for h in hosts), default=0)
            return {
                "hostname": self.config["host"],
                "hosts": len(hosts),
                "memory_total_mb": round(total_mem / 1024 / 1024, 0),
                "platform": "oVirt",
            }
        except Exception as e:
            return {"error": str(e)}

    def list_vms(self):
        try:
            vms_svc = self._conn.system_service().vms_service()
            vms = vms_svc.list()
            return [{
                "name": vm.name,
                "vmid": vm.id,
                "state": "running" if vm.status.name == "up" else "shutoff",
                "vcpu": vm.cpu.topology.cores if vm.cpu and vm.cpu.topology else 0,
                "memory_mb": round(vm.memory / 1024 / 1024, 0) if vm.memory else 0,
                "platform": "ovirt",
            } for vm in vms]
        except Exception as e:
            return [{"error": str(e)}]

    def get_vm(self, name):
        for vm in self.list_vms():
            if vm["name"] == name:
                return vm
        return None

    def start_vm(self, name):
        try:
            import ovirtsdk4.types as types
            vms_svc = self._conn.system_service().vms_service()
            vm = vms_svc.list(search=f"name={name}")
            if not vm:
                return {"success": False, "error": f"VM '{name}' not found"}
            vm_svc = vms_svc.vm_service(vm[0].id)
            vm_svc.start()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def stop_vm(self, name):
        try:
            import ovirtsdk4.types as types
            vms_svc = self._conn.system_service().vms_service()
            vm = vms_svc.list(search=f"name={name}")
            if not vm:
                return {"success": False, "error": f"VM '{name}' not found"}
            vm_svc = vms_svc.vm_service(vm[0].id)
            vm_svc.shutdown()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_status(self):
        if not self._connected:
            return {"connected": False, "error": getattr(self, "_error", "unknown")}
        try:
            vms = self.list_vms()
            return {
                "connected": True,
                "type": "oVirt",
                "host": self.config["host"],
                "vms": len(vms),
                "running": sum(1 for v in vms if v.get("state") == "running"),
            }
        except Exception as e:
            return {"connected": True, "error": str(e)}


# ── VMware vSphere 连接器 ──────────────────────────────────

class VSphereConnector(BaseConnector):
    type = "vsphere"

    def connect(self):
        try:
            from pyVim import connect
            from pyVmomi import vim
            cfg = self.config
            self._si = connect.SmartConnect(
                host=cfg["host"],
                user=cfg["user"],
                pwd=cfg["password"],
                port=cfg.get("port", 443),
                disableSslCertValidation=cfg.get("insecure", True),
            )
            self._content = self._si.RetrieveContent()
            self._connected = True
            return True
        except ImportError:
            self._connected = False
            self._error = "pyvmomi 未安装 (pip install pyvmomi)"
            return False
        except Exception as e:
            self._connected = False
            self._error = str(e)
            return False

    def disconnect(self):
        if self._connected:
            from pyVim import connect
            connect.Disconnect(self._si)
        self._connected = False

    def _get_all_vms(self, folder=None):
        from pyVmomi import vim
        if folder is None:
            folder = self._content.rootFolder
        vms = []
        for child in folder.childEntity:
            if isinstance(child, vim.VirtualMachine):
                vms.append(child)
            elif isinstance(child, vim.Folder):
                vms.extend(self._get_all_vms(child))
        return vms

    def get_host_info(self):
        try:
            about = self._content.about
            return {
                "hostname": about.fullyQualifiedHostName or self.config["host"],
                "platform": "VMware vSphere",
                "version": about.version,
                "build": about.build,
            }
        except Exception as e:
            return {"error": str(e)}

    def list_vms(self):
        try:
            vms = self._get_all_vms()
            return [{
                "name": vm.name,
                "vmid": vm.config.uuid if vm.config else vm._moId,
                "state": "running" if vm.runtime.powerState == "poweredOn" else "shutoff",
                "vcpu": vm.config.hardware.numCPU if vm.config and vm.config.hardware else 0,
                "memory_mb": vm.config.hardware.memoryMB if vm.config and vm.config.hardware else 0,
                "platform": "vsphere",
                "power_state": str(vm.runtime.powerState),
            } for vm in vms]
        except Exception as e:
            return [{"error": str(e)}]

    def get_vm(self, name):
        for vm in self.list_vms():
            if vm["name"] == name:
                return vm
        return None

    def start_vm(self, name):
        try:
            from pyVmomi import vim
            for vm_obj in self._get_all_vms():
                if vm_obj.name == name:
                    task = vm_obj.PowerOn()
                    return {"success": True, "task": str(task)}
            return {"success": False, "error": f"VM '{name}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def stop_vm(self, name):
        try:
            from pyVmomi import vim
            for vm_obj in self._get_all_vms():
                if vm_obj.name == name:
                    task = vm_obj.PowerOff()
                    return {"success": True, "task": str(task)}
            return {"success": False, "error": f"VM '{name}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_status(self):
        if not self._connected:
            return {"connected": False, "error": getattr(self, "_error", "unknown")}
        try:
            vms = self.list_vms()
            running = sum(1 for v in vms if v.get("state") == "running")
            about = self._content.about
            return {
                "connected": True,
                "type": "VMware vSphere",
                "host": self.config["host"],
                "version": f"{about.version} (build {about.build})",
                "vms": len(vms),
                "running": running,
            }
        except Exception as e:
            return {"connected": True, "error": str(e)}


# ── 连接器工厂 ─────────────────────────────────────────────

CONNECTORS = {
    "proxmox": ProxmoxConnector,
    "ovirt": OvirtConnector,
    "vsphere": VSphereConnector,
}


# ── 远程 Hypervisor 管理器 ─────────────────────────────────

class HypervisorManager:
    """管理所有远程 hypervisor 连接"""

    def __init__(self):
        self._remotes = {}  # name -> connector
        self._load_config()

    def _load_config(self):
        if os.path.exists(HYPERVISORS_FILE):
            with open(HYPERVISORS_FILE) as f:
                configs = json.load(f)
        else:
            # 默认演示配置
            configs = [
                {
                    "name": "proxmox-demo",
                    "type": "proxmox",
                    "host": "192.168.1.100",
                    "port": 8006,
                    "user": "root@pam",
                    "password": "********",
                    "verify_ssl": False,
                    "enabled": False,
                },
                {
                    "name": "ovirt-demo",
                    "type": "ovirt",
                    "host": "ovirt-engine.example.com",
                    "port": 443,
                    "user": "admin@internal",
                    "password": "********",
                    "insecure": True,
                    "enabled": False,
                },
                {
                    "name": "vsphere-demo",
                    "type": "vsphere",
                    "host": "vcenter.example.com",
                    "port": 443,
                    "user": "administrator@vsphere.local",
                    "password": "********",
                    "insecure": True,
                    "enabled": False,
                },
            ]
            self._save_config(configs)

        for cfg in configs:
            if cfg.get("enabled", True):
                connector_class = CONNECTORS.get(cfg["type"])
                if connector_class:
                    connector = connector_class(cfg)
                    connector.connect()
                    self._remotes[cfg["name"]] = connector

    def _save_config(self, configs):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(HYPERVISORS_FILE, "w") as f:
            json.dump(configs, f, indent=2)

    def list_remotes(self):
        result = []
        for name, conn in self._remotes.items():
            status = conn.get_status()
            result.append({
                "name": name,
                "type": conn.type,
                "host": conn.config["host"],
                "status": status,
            })
        return result

    def get_remote(self, name):
        return self._remotes.get(name)

    def add_remote(self, config):
        configs = []
        if os.path.exists(HYPERVISORS_FILE):
            with open(HYPERVISORS_FILE) as f:
                configs = json.load(f)
        # 检查重名
        for existing in configs:
            if existing["name"] == config["name"]:
                return {"success": False, "error": "名称已存在"}
        configs.append(config)
        self._save_config(configs)
        # 如果启用则立即连接
        if config.get("enabled", True):
            connector_class = CONNECTORS.get(config["type"])
            if connector_class:
                conn = connector_class(config)
                conn.connect()
                self._remotes[config["name"]] = conn
        return {"success": True}

    def remove_remote(self, name):
        conn = self._remotes.pop(name, None)
        if conn:
            conn.disconnect()
        configs = []
        if os.path.exists(HYPERVISORS_FILE):
            with open(HYPERVISORS_FILE) as f:
                configs = json.load(f)
        configs = [c for c in configs if c["name"] != name]
        self._save_config(configs)
        return {"success": True}


# 全局单例
_hypervisors = HypervisorManager()


# ═════════════════════════════════════════════════════════
#  Plugin 类
# ═════════════════════════════════════════════════════════

class Plugin(PluginBase):
    name = "remote-hypervisors"
    version = "1.0.0"
    description = "Connect to Proxmox VE, oVirt, VMware vSphere — unified remote VM management"
    author = "VM Panel Team"
    homepage = ""

    def register_routes(self, app):

        # ── 远程连接列表 ──
        @app.route("/api/plugins/hypervisors")
        def api_hypervisors_list():
            return {"ok": True, "data": _hypervisors.list_remotes()}, 200

        # ── 添加远程连接 ──
        @app.route("/api/plugins/hypervisors", methods=["POST"])
        def api_hypervisors_add():
            data = request.get_json()
            if not data or "name" not in data or "type" not in data or "host" not in data:
                return {"ok": False, "error": "缺少必填字段 (name, type, host)"}, 400
            result = _hypervisors.add_remote(data)
            if result["success"]:
                return {"ok": True, "data": result}, 201
            return {"ok": False, "error": result["error"]}, 400

        # ── 删除远程连接 ──
        @app.route("/api/plugins/hypervisors/<name>", methods=["DELETE"])
        def api_hypervisors_delete(name):
            result = _hypervisors.remove_remote(name)
            return {"ok": True, "data": result}, 200

        # ── 远程 VM 列表 ──
        @app.route("/api/plugins/hypervisors/<name>/vms")
        def api_hypervisors_vms(name):
            remote = _hypervisors.get_remote(name)
            if not remote:
                return {"ok": False, "error": f"远程 '{name}' 不存在"}, 404
            vms = remote.list_vms()
            return {"ok": True, "data": vms}, 200

        # ── 远程 VM 操作 ──
        @app.route("/api/plugins/hypervisors/<name>/vms/<vm_name>/<action>", methods=["POST"])
        def api_hypervisors_vm_action(name, vm_name, action):
            remote = _hypervisors.get_remote(name)
            if not remote:
                return {"ok": False, "error": f"远程 '{name}' 不存在"}, 404
            if action == "start":
                result = remote.start_vm(vm_name)
            elif action == "stop":
                result = remote.stop_vm(vm_name)
            else:
                return {"ok": False, "error": f"不支持的操作: {action}"}, 400
            return {"ok": result.get("success", False), "data": result}, 200

        # ── 远程宿主机信息 ──
        @app.route("/api/plugins/hypervisors/<name>/info")
        def api_hypervisors_info(name):
            remote = _hypervisors.get_remote(name)
            if not remote:
                return {"ok": False, "error": f"远程 '{name}' 不存在"}, 404
            return {"ok": True, "data": remote.get_host_info()}, 200

        # ── 页面路由 ──
        @app.route("/plugins/hypervisors")
        def hypervisors_page():
            from flask import render_template
            return render_template("plugin_hypervisors.html")

    def register_menu(self):
        return [
            ("Remote Hypervisors", "/plugins/hypervisors", "bi bi-cloud-arrow-down"),
        ]

    def get_status(self):
        remotes = _hypervisors.list_remotes()
        connected = sum(1 for r in remotes if r.get("status", {}).get("connected"))
        total_vms = 0
        for r in remotes:
            s = r.get("status", {})
            total_vms += s.get("vms", 0)
        return {
            "enabled": True,
            "remotes": len(remotes),
            "connected": connected,
            "total_vms": total_vms,
        }
