"""
VM Management Panel - 网络管理模块

管理桥接网络、NAT 网络、DHCP 配置。
底层操作通过 `ip`/`brctl`/`virsh` 命令实现。
"""
import os
import json
import subprocess
import uuid
from xml.etree import ElementTree as ET

from config import Config


class NetworkManager:
    """网络管理器 - 桥接/NAT/DHCP"""

    def __init__(self):
        self._networks_file = os.path.join(Config.CONFIG_DIR, "networks.json")
        self._simulated = Config.SIMULATE_LIBVIRT

    # ── 获取网络列表 ───────────────────────────────────────

    def list_networks(self):
        """获取所有虚拟网络"""
        if self._simulated:
            return self._get_simulated_networks()

        try:
            import libvirt
            conn = libvirt.open(Config.LIBVIRT_URI)
            networks = []
            for net_name in conn.listNetworks() + conn.listDefinedNetworks():
                net = conn.networkLookupByName(net_name)
                xml_desc = net.XMLDesc()
                tree = ET.fromstring(xml_desc)

                # 解析 DHCP
                dhcp = tree.findall(".//dhcp/range")
                dhcp_info = {}
                if dhcp:
                    dhcp_info = {
                        "start": dhcp[0].get("start", ""),
                        "end": dhcp[0].get("end", ""),
                    }

                networks.append({
                    "name": net_name,
                    "uuid": net.UUIDString(),
                    "type": self._detect_net_type(tree),
                    "bridge": tree.findtext("bridge/@name", ""),
                    "forward": tree.findtext("forward/@mode", "nat"),
                    "subnet": self._extract_subnet(tree),
                    "dhcp": dhcp_info,
                    "active": net.isActive(),
                    "autostart": net.autostart(),
                })
            conn.close()
            return networks
        except (ImportError, Exception) as e:
            return self._get_simulated_networks()

    def _detect_net_type(self, tree):
        """检测网络类型"""
        forward = tree.find("forward")
        if forward is None:
            return "isolated"
        mode = forward.get("mode", "")
        if mode == "nat":
            return "nat"
        elif mode == "bridge":
            return "bridge"
        elif mode == "route":
            return "route"
        return "nat"

    def _extract_subnet(self, tree):
        """提取子网 CIDR"""
        ip = tree.find("ip")
        if ip is not None:
            addr = ip.get("address", "")
            prefix = ip.get("prefix", "24")
            return f"{addr}/{prefix}"
        return ""

    # ── 创建网络 ───────────────────────────────────────────

    def create_network(self, spec):
        """
        创建虚拟网络

        spec:
        {
            "name": "net-name",
            "type": "nat" | "bridge" | "isolated",
            "subnet": "192.168.100.0/24",
            "bridge": "virbr1",
            "dhcp_start": "192.168.100.10",
            "dhcp_end": "192.168.100.200",
            "forward_dev": "eth0",    # bridge 类型时需要
        }
        """
        name = spec["name"]
        net_type = spec.get("type", "nat")
        subnet = spec.get("subnet", "192.168.100.0/24")
        dhcp_start = spec.get("dhcp_start", "")
        dhcp_end = spec.get("dhcp_end", "")

        # 解析子网
        if "/" in subnet:
            addr, prefix = subnet.split("/")
        else:
            addr = subnet.rstrip(".0")
            prefix = "24"

        bridge_name = spec.get("bridge", f"virbr{hash(name) % 900 + 100}")

        if self._simulated:
            return self._simulated_create_network(name, net_type, subnet, bridge_name, dhcp_start, dhcp_end)

        try:
            import libvirt
            conn = libvirt.open(Config.LIBVIRT_URI)

            uuid_str = str(uuid.uuid4())
            dhcp_xml = ""
            if dhcp_start and dhcp_end:
                dhcp_xml = f"""
            <dhcp>
                <range start='{dhcp_start}' end='{dhcp_end}'/>
            </dhcp>"""

            forward_xml = ""
            if net_type == "nat":
                forward_xml = "<forward mode='nat'/>"
            elif net_type == "bridge":
                forward_xml = f"<forward mode='bridge'/>"
                dhcp_xml = ""  # 桥接网络通常不需要 DHCP

            xml = f"""<network>
                <name>{name}</name>
                <uuid>{uuid_str}</uuid>
                {forward_xml}
                <bridge name='{bridge_name}' stp='on' delay='0'/>
                <ip address='{addr}' prefix='{prefix}'>
                    {dhcp_xml}
                </ip>
            </network>"""

            conn.networkDefineXML(xml)
            net = conn.networkLookupByName(name)
            net.setAutostart(True)
            net.create()
            conn.close()
            return {"success": True, "name": name}

        except (ImportError, Exception) as e:
            return {"success": False, "error": str(e)}

    # ── 删除网络 ───────────────────────────────────────────

    def delete_network(self, name):
        """删除虚拟网络"""
        if self._simulated:
            return self._simulated_delete_network(name)

        try:
            import libvirt
            conn = libvirt.open(Config.LIBVIRT_URI)
            net = conn.networkLookupByName(name)
            if net.isActive():
                net.destroy()
            net.undefine()
            conn.close()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 激活/停用 ──────────────────────────────────────────

    def activate_network(self, name):
        """激活网络"""
        if self._simulated:
            return {"success": True}

        try:
            import libvirt
            conn = libvirt.open(Config.LIBVIRT_URI)
            net = conn.networkLookupByName(name)
            if not net.isActive():
                net.create()
            conn.close()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def deactivate_network(self, name):
        """停用网络"""
        if self._simulated:
            return {"success": True}

        try:
            import libvirt
            conn = libvirt.open(Config.LIBVIRT_URI)
            net = conn.networkLookupByName(name)
            if net.isActive():
                net.destroy()
            conn.close()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 桥接网络 (系统级) ──────────────────────────────────

    def create_bridge(self, bridge_name, interface=None):
        """
        创建系统级 Linux 桥接网络

        Args:
            bridge_name: 网桥名称 (如 br0)
            interface: 要桥接的物理网卡 (如 eth0)
        """
        if self._simulated:
            return {"success": True}

        try:
            # 1. 创建网桥
            subprocess.run(["ip", "link", "add", "name", bridge_name,
                          "type", "bridge"], check=True)
            subprocess.run(["ip", "link", "set", bridge_name, "up"], check=True)

            # 2. 如果要桥接物理网卡
            if interface:
                subprocess.run(["ip", "link", "set", interface, "master",
                              bridge_name], check=True)

            # 3. 持久化配置 (Debian/Ubuntu)
            netplan_path = f"/etc/netplan/01-{bridge_name}.yaml"
            netplan_config = f"""network:
  version: 2
  ethernets:
    {interface or "eth0"}:
      dhcp4: false
  bridges:
    {bridge_name}:
      interfaces: [{interface or "eth0"}]
      dhcp4: true
"""
            print(f"[bridge] 若要持久化请写入 {netplan_path}")
            print(f"[bridge] 配置内容:\n{netplan_config}")

            return {"success": True, "bridge": bridge_name}
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": f"创建桥接失败: {e.stderr}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_bridge(self, bridge_name):
        """删除网桥"""
        if self._simulated:
            return {"success": True}

        try:
            subprocess.run(["ip", "link", "set", bridge_name, "down"], check=True)
            subprocess.run(["ip", "link", "delete", bridge_name, "type", "bridge"],
                          check=True)
            return {"success": True}
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": str(e)}

    def list_bridges(self):
        """列出系统网桥"""
        try:
            result = subprocess.run(
                ["ip", "-j", "link", "show", "type", "bridge"],
                capture_output=True, text=True, check=True
            )
            bridges = json.loads(result.stdout)
            return [
                {
                    "name": b["ifname"],
                    "mac": b.get("address", ""),
                    "state": "up" if b.get("flags", {}).get("UP", False) else "down",
                }
                for b in bridges
            ]
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
            return []

    # ── 模拟模式 ───────────────────────────────────────────

    def _get_simulated_networks(self):
        """模拟网络列表 (UUID 持久化)"""
        saved = []
        if os.path.exists(self._networks_file):
            with open(self._networks_file) as f:
                saved = json.load(f)

        # 检查是否已有 default 网络，避免 UUID 每次变化
        existing_default = None
        for n in saved:
            if n["name"] == "default":
                existing_default = n
                break

        if not existing_default:
            default = {
                "name": "default",
                "uuid": "default-net-0000-0000-000000000001",
                "type": "nat",
                "bridge": "virbr0",
                "forward": "nat",
                "subnet": "192.168.122.0/24",
                "dhcp": {"start": "192.168.122.2", "end": "192.168.122.254"},
                "active": True,
                "autostart": True,
            }
            saved.insert(0, default)
            os.makedirs(os.path.dirname(self._networks_file), exist_ok=True)
            with open(self._networks_file, "w") as f:
                json.dump(saved, f, indent=2)

        return saved

    def _simulated_create_network(self, name, net_type, subnet, bridge, dhcp_s, dhcp_e):
        saved = []
        if os.path.exists(self._networks_file):
            with open(self._networks_file) as f:
                saved = json.load(f)

        net = {
            "name": name,
            "uuid": str(uuid.uuid4()),
            "type": net_type,
            "bridge": bridge,
            "forward": net_type,
            "subnet": subnet,
            "dhcp": {"start": dhcp_s, "end": dhcp_e},
            "active": True,
            "autostart": False,
        }
        saved.append(net)
        os.makedirs(os.path.dirname(self._networks_file), exist_ok=True)
        with open(self._networks_file, "w") as f:
            json.dump(saved, f, indent=2)
        return {"success": True}

    def _simulated_delete_network(self, name):
        saved = []
        if os.path.exists(self._networks_file):
            with open(self._networks_file) as f:
                saved = json.load(f)
        before = len(saved)
        saved = [n for n in saved if n["name"] != name]
        if len(saved) == before:
            return {"success": False, "error": f"网络 '{name}' 不存在"}
        with open(self._networks_file, "w") as f:
            json.dump(saved, f, indent=2)
        return {"success": True}
