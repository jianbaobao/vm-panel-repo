"""
VM Management Panel - libvirt/KVM 管理抽象层

提供虚拟机生命周期管理：创建、启动、停止、删除、快照等。
支持真实 libvirt 连接和模拟模式（开发/演示用）。
"""
import os
import time
import json
import uuid
import shutil
from datetime import datetime
from xml.etree import ElementTree as ET

from config import Config


class LibvirtManager:
    """虚拟机管理器 - 封装 libvirt API，回退到模拟模式"""

    def __init__(self):
        self._conn = None
        self._simulated = Config.SIMULATE_LIBVIRT
        self._vms_file = os.path.join(Config.CONFIG_DIR, "simulated_vms.json")
        self._simulated_vms = self._load_simulated()

    # ── 连接管理 ───────────────────────────────────────────

    def connect(self):
        """连接到 libvirtd 守护进程"""
        if self._simulated:
            return True
        try:
            import libvirt
            self._conn = libvirt.open(Config.LIBVIRT_URI)
            return self._conn is not None
        except (ImportError, libvirt.libvirtError) as e:
            print(f"[libvirt] 连接失败: {e}，切换模拟模式")
            self._simulated = True
            return False

    def is_connected(self):
        return self._simulated or (self._conn is not None)

    def disconnect(self):
        if self._conn and not self._simulated:
            self._conn.close()

    # ── 宿主机信息 ─────────────────────────────────────────

    def get_host_info(self):
        """获取宿主机系统信息"""
        if self._simulated:
            return {
                "hostname": "vm-host-simulated",
                "arch": "x86_64",
                "cpus": 8,
                "cpu_model": "Intel(R) Xeon(R) Platinum 8375C (Simulated)",
                "memory_total_mb": 32768,
                "memory_free_mb": 24576,
                "memory_used_mb": 8192,
            }
        try:
            info = self._conn.getInfo()
            mem_stats = self._conn.getMemoryStats(-1)
            return {
                "hostname": self._conn.getHostname(),
                "arch": info[0],
                "cpus": info[2],
                "cpu_model": info[1],
                "memory_total_mb": mem_stats.get("total", 0) // 1024,
                "memory_free_mb": mem_stats.get("free", 0) // 1024,
                "memory_used_mb": (mem_stats.get("total", 0) - mem_stats.get("free", 0)) // 1024,
            }
        except Exception as e:
            return {"error": str(e)}

    def get_host_stats(self):
        """获取实时性能统计"""
        if self._simulated:
            return {
                "cpu_percent": 32.5,
                "memory_percent": 25.0,
                "disk_usage": {
                    "total_gb": 500,
                    "used_gb": 120,
                    "free_gb": 380,
                    "percent": 24.0,
                },
            }
        try:
            import psutil
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage(Config.STORAGE_DIR)
            cpu_percent = psutil.cpu_percent(interval=0.5)
            return {
                "cpu_percent": cpu_percent,
                "memory_percent": mem.percent,
                "disk_usage": {
                    "total_gb": round(disk.total / (1024**3), 1),
                    "used_gb": round(disk.used / (1024**3), 1),
                    "free_gb": round(disk.free / (1024**3), 1),
                    "percent": disk.percent,
                },
            }
        except ImportError:
            return {"cpu_percent": 0, "memory_percent": 0, "disk_usage": {}}

    # ── VM 列表/查询 ───────────────────────────────────────

    def list_vms(self):
        """获取所有虚拟机列表"""
        if self._simulated:
            return self._simulated_vms

        vms = []
        for domain_id in self._conn.listDomainsID():
            dom = self._conn.lookupByID(domain_id)
            vms.append(self._domain_to_dict(dom))
        for domain_name in self._conn.listDefinedDomains():
            dom = self._conn.lookupByName(domain_name)
            vms.append(self._domain_to_dict(dom))
        return vms

    def get_vm(self, name):
        """获取单个虚拟机详情"""
        if self._simulated:
            for vm in self._simulated_vms:
                if vm["name"] == name:
                    return vm
            return None

        try:
            dom = self._conn.lookupByName(name)
            return self._domain_to_dict(dom)
        except Exception:
            return None

    def _domain_to_dict(self, dom):
        """将 libvirt Domain 对象转为字典"""
        try:
            state, max_mem, mem, vcpus, cpu_time = dom.info()
            state_map = {
                0: "nostate", 1: "running", 2: "blocked",
                3: "paused", 4: "shutdown", 5: "shutoff",
                6: "crashed", 7: "pmsuspended",
            }
            xml_desc = dom.XMLDesc()
            tree = ET.fromstring(xml_desc)

            # 解析磁盘
            disks = []
            for disk in tree.findall(".//devices/disk"):
                dev = disk.find("target")
                src = disk.find("source")
                if dev is not None and src is not None:
                    disks.append({
                        "device": dev.get("dev"),
                        "bus": dev.get("bus"),
                        "file": src.get("file") or src.get("dev"),
                        "type": disk.get("type"),
                    })

            # 解析网络
            networks = []
            for iface in tree.findall(".//devices/interface"):
                mac = iface.find("mac")
                source = iface.find("source")
                model = iface.find("model")
                networks.append({
                    "mac": mac.get("address") if mac is not None else "",
                    "network": source.get("network") if source is not None else "",
                    "bridge": source.get("bridge") if source is not None else "",
                    "model": model.get("type") if model is not None else "",
                })

            return {
                "name": dom.name(),
                "uuid": dom.UUIDString(),
                "state": state_map.get(state, "unknown"),
                "vcpu": vcpus,
                "memory_mb": max_mem // 1024,
                "memory_used_mb": mem // 1024,
                "cpu_time_ns": cpu_time,
                "autostart": dom.autostart(),
                "os_type": tree.findtext("./os/type", ""),
                "disks": disks,
                "networks": networks,
                "created": datetime.fromtimestamp(dom.getMetadata(0, None, 0))
                           if hasattr(dom, "getMetadata") else None,
            }
        except Exception as e:
            return {"name": dom.name(), "error": str(e)}

    # ── VM 操作 ────────────────────────────────────────────

    def create_vm(self, spec):
        """
        创建虚拟机

        spec 格式:
        {
            "name": "vm-name",
            "vcpu": 2,
            "memory_mb": 2048,
            "disk_gb": 20,
            "disk_path": "/path/to/disk.qcow2",
            "network": "default",
            "network_model": "virtio",
            "iso_path": "/path/to/installer.iso",
            "os_type": "linux",
            "os_variant": "ubuntu24.04",
        }
        """
        name = spec["name"]
        vcpu = spec.get("vcpu", 2)
        memory_mb = spec.get("memory_mb", 2048)
        disk_gb = spec.get("disk_gb", 20)
        network = spec.get("network", "default")
        iso_path = spec.get("iso_path", "")

        # 磁盘镜像路径
        disk_path = spec.get("disk_path") or os.path.join(
            Config.VM_IMAGE_DIR, f"{name}.qcow2"
        )
        disk_path = os.path.abspath(disk_path)

        if self._simulated:
            return self._simulated_create(name, vcpu, memory_mb, disk_gb, network, iso_path, disk_path)

        try:
            # 1. 创建磁盘镜像
            self._create_disk_image(disk_path, disk_gb)

            # 2. 生成 XML 描述
            xml_desc = self._build_domain_xml(name, vcpu, memory_mb, disk_path, network, iso_path)

            # 3. 定义 domain
            dom = self._conn.defineXML(xml_desc)
            return {"success": True, "name": name, "uuid": dom.UUIDString()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_disk_image(self, path, size_gb):
        """创建 qcow2 磁盘镜像"""
        import subprocess
        cmd = ["qemu-img", "create", "-f", "qcow2", path, f"{size_gb}G"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"创建磁盘镜像失败: {result.stderr}")
        return path

    def _build_domain_xml(self, name, vcpu, memory_mb, disk_path, network, iso_path):
        """构建 libvirt domain XML"""
        mem_kib = memory_mb * 1024
        uuid_str = str(uuid.uuid4())

        disk_xml = f"""
            <disk type='file' device='disk'>
                <driver name='qemu' type='qcow2' cache='writeback'/>
                <source file='{disk_path}'/>
                <target dev='vda' bus='virtio'/>
            </disk>"""

        cdrom_xml = ""
        if iso_path and os.path.exists(iso_path):
            cdrom_xml = f"""
            <disk type='file' device='cdrom'>
                <driver name='qemu' type='raw'/>
                <source file='{iso_path}'/>
                <target dev='sda' bus='sata'/>
                <readonly/>
            </disk>"""

        if network.startswith("br-") or network.startswith("bridge:"):
            bridge_name = network.replace("bridge:", "")
            net_xml = f"""
            <interface type='bridge'>
                <source bridge='{bridge_name}'/>
                <model type='virtio'/>
            </interface>"""
        else:
            net_xml = f"""
            <interface type='network'>
                <source network='{network}'/>
                <model type='virtio'/>
            </interface>"""

        xml = f"""<?xml version='1.0' encoding='UTF-8'?>
<domain type='kvm'>
    <name>{name}</name>
    <uuid>{uuid_str}</uuid>
    <memory unit='KiB'>{mem_kib}</memory>
    <currentMemory unit='KiB'>{mem_kib}</currentMemory>
    <vcpu placement='static'>{vcpu}</vcpu>
    <os>
        <type arch='x86_64' machine='pc-q35-9.0'>hvm</type>
        <boot dev='hd'/>
        <boot dev='cdrom'/>
    </os>
    <features>
        <acpi/><apic/><pae/>
    </features>
    <cpu mode='host-passthrough' check='none'/>
    <clock offset='utc'>
        <timer name='rtc' tickpolicy='catchup'/>
        <timer name='pit' tickpolicy='delay'/>
        <timer name='hpet' present='no'/>
    </clock>
    <on_poweroff>destroy</on_poweroff>
    <on_reboot>restart</on_reboot>
    <on_crash>destroy</on_crash>
    <devices>
        <emulator>{Config.QEMU_BIN}</emulator>
        {disk_xml}
        {cdrom_xml}
        {net_xml}
        <serial type='pty'>
            <target port='0'/>
        </serial>
        <console type='pty'>
            <target type='serial' port='0'/>
        </console>
        <graphics type='vnc' port='-1' autoport='yes' listen='0.0.0.0'>
            <listen type='address' address='0.0.0.0'/>
        </graphics>
        <video>
            <model type='virtio' heads='1' primary='yes'/>
        </video>
        <memballoon model='virtio'/>
    </devices>
</domain>"""
        return xml

    def start_vm(self, name):
        """启动虚拟机"""
        if self._simulated:
            return self._simulated_operate(name, "start")

        try:
            dom = self._conn.lookupByName(name)
            dom.create()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def shutdown_vm(self, name):
        """正常关机 (ACPI)"""
        if self._simulated:
            return self._simulated_operate(name, "shutdown")

        try:
            dom = self._conn.lookupByName(name)
            dom.shutdown()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def force_stop_vm(self, name):
        """强制断电"""
        if self._simulated:
            return self._simulated_operate(name, "force_stop")

        try:
            dom = self._conn.lookupByName(name)
            dom.destroy()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def restart_vm(self, name):
        """重启虚拟机 (先关后开)"""
        if self._simulated:
            return self._simulated_operate(name, "restart")

        try:
            dom = self._conn.lookupByName(name)
            # 使用 reboot (ACPI 重启) 代替 reset (硬复位)
            try:
                dom.reboot(0)  # 0 = libvirt.VIR_DOMAIN_REBOOT_DEFAULT
            except Exception:
                # 如果 reboot 不支持，回退到 shutdown+start
                dom.shutdown()
                import time
                time.sleep(2)
                dom.create()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_vm(self, name, delete_disk=False):
        """删除虚拟机"""
        if self._simulated:
            return self._simulated_operate(name, "delete")

        try:
            dom = self._conn.lookupByName(name)
            # 先强制停止
            try:
                dom.destroy()
            except Exception:
                pass
            # 取消自动启动
            dom.setAutostart(False)
            # 获取磁盘路径以删除
            disk_paths = []
            if delete_disk:
                xml_desc = dom.XMLDesc()
                tree = ET.fromstring(xml_desc)
                for disk in tree.findall(".//devices/disk"):
                    src = disk.find("source")
                    if src is not None:
                        f = src.get("file")
                        if f:
                            disk_paths.append(f)
            # 取消定义
            dom.undefine()
            # 删除磁盘
            if delete_disk:
                for path in disk_paths:
                    if os.path.exists(path):
                        os.remove(path)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 快照管理 ───────────────────────────────────────────

    def list_snapshots(self, vm_name):
        """列出虚拟机快照"""
        if self._simulated:
            return []

        try:
            dom = self._conn.lookupByName(vm_name)
            snapshots = dom.listAllSnapshots()
            result = []
            for snap in snapshots:
                xml_desc = snap.getXMLDesc()
                tree = ET.fromstring(xml_desc)
                result.append({
                    "name": snap.getName(),
                    "created": tree.findtext("creationTime", ""),
                    "state": tree.findtext("state", ""),
                    "description": tree.findtext("description", ""),
                })
            return result
        except Exception as e:
            return {"error": str(e)}

    def create_snapshot(self, vm_name, snap_name, description=""):
        """创建快照"""
        if self._simulated:
            return {"success": True}

        try:
            dom = self._conn.lookupByName(vm_name)
            xml_desc = f"<domainsnapshot><name>{snap_name}</name><description>{description}</description></domainsnapshot>"
            dom.snapshotCreateXML(xml_desc)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def revert_snapshot(self, vm_name, snap_name):
        """回滚快照"""
        if self._simulated:
            return {"success": True}

        try:
            dom = self._conn.lookupByName(vm_name)
            snap = dom.snapshotLookupByName(snap_name)
            dom.revertToSnapshot(snap)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_snapshot(self, vm_name, snap_name):
        """删除快照"""
        if self._simulated:
            return {"success": True}

        try:
            dom = self._conn.lookupByName(vm_name)
            snap = dom.snapshotLookupByName(snap_name)
            snap.delete()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── VNC 端口 ───────────────────────────────────────────

    def get_vnc_port(self, vm_name):
        """获取 VM 的 VNC 端口"""
        if self._simulated:
            return 5900

        try:
            dom = self._conn.lookupByName(vm_name)
            xml_desc = dom.XMLDesc()
            tree = ET.fromstring(xml_desc)
            graphics = tree.find(".//devices/graphics")
            if graphics is not None:
                return int(graphics.get("port", -1))
            return -1
        except Exception:
            return -1

    # ── 模拟模式 ───────────────────────────────────────────

    def _load_simulated(self):
        if os.path.exists(self._vms_file):
            with open(self._vms_file) as f:
                return json.load(f)
        # 默认示例 VM
        return [
            {
                "name": "ubuntu-server",
                "uuid": str(uuid.uuid4()),
                "state": "running",
                "vcpu": 4,
                "memory_mb": 4096,
                "memory_used_mb": 2048,
                "cpu_time_ns": 123456789000,
                "autostart": True,
                "os_type": "hvm",
                "disks": [
                    {"device": "vda", "bus": "virtio", "file": "/var/lib/libvirt/images/ubuntu-server.qcow2", "type": "file"}
                ],
                "networks": [
                    {"mac": "52:54:00:a1:b2:c3", "network": "default", "bridge": "", "model": "virtio"}
                ],
                "created": "2025-01-15T10:30:00",
                "uptime_seconds": 86400,
            },
            {
                "name": "centos-dev",
                "uuid": str(uuid.uuid4()),
                "state": "shutoff",
                "vcpu": 2,
                "memory_mb": 2048,
                "memory_used_mb": 0,
                "cpu_time_ns": 0,
                "autostart": False,
                "os_type": "hvm",
                "disks": [
                    {"device": "vda", "bus": "virtio", "file": "/var/lib/libvirt/images/centos-dev.qcow2", "type": "file"}
                ],
                "networks": [
                    {"mac": "52:54:00:d4:e5:f6", "network": "default", "bridge": "", "model": "virtio"}
                ],
                "created": "2025-02-20T14:00:00",
                "uptime_seconds": 0,
            },
        ]

    def _save_simulated(self):
        os.makedirs(os.path.dirname(self._vms_file), exist_ok=True)
        with open(self._vms_file, "w") as f:
            json.dump(self._simulated_vms, f, indent=2, default=str)

    def _simulated_create(self, name, vcpu, memory_mb, disk_gb, network, iso_path, disk_path):
        vm = {
            "name": name,
            "uuid": str(uuid.uuid4()),
            "state": "shutoff",
            "vcpu": vcpu,
            "memory_mb": memory_mb,
            "memory_used_mb": 0,
            "cpu_time_ns": 0,
            "autostart": False,
            "os_type": "hvm",
            "disks": [
                {"device": "vda", "bus": "virtio", "file": disk_path, "type": "file"}
            ],
            "networks": [
                {"mac": "52:54:00:" + ":".join(f"{uuid.uuid4().hex[i:i+2]}" for i in range(0, 3)),
                 "network": network, "bridge": "", "model": "virtio"}
            ],
            "created": datetime.now().isoformat(),
            "uptime_seconds": 0,
            "iso_path": iso_path if iso_path else "",
        }
        self._simulated_vms.append(vm)
        self._save_simulated()
        return {"success": True, "name": name, "uuid": vm["uuid"]}

    def _simulated_operate(self, name, action):
        for vm in self._simulated_vms:
            if vm["name"] == name:
                if action == "start":
                    vm["state"] = "running"
                    vm["uptime_seconds"] = 0
                elif action == "shutdown":
                    vm["state"] = "shutoff"
                    vm["uptime_seconds"] = 0
                elif action == "force_stop":
                    vm["state"] = "shutoff"
                    vm["uptime_seconds"] = 0
                elif action == "restart":
                    vm["state"] = "running"
                    vm["uptime_seconds"] = 0
                elif action == "delete":
                    self._simulated_vms.remove(vm)
                self._save_simulated()
                return {"success": True}
        return {"success": False, "error": f"VM '{name}' not found"}
