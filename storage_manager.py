"""
VM Management Panel - 存储管理模块

管理存储池、卷、ISO 镜像上传等。
"""
import os
import json
import shutil
from datetime import datetime
from xml.etree import ElementTree as ET
from config import Config


class StorageManager:
    """存储管理器 - 存储池/卷/ISO"""

    def __init__(self):
        self._simulated = Config.SIMULATE_LIBVIRT
        self._pools_file = os.path.join(Config.CONFIG_DIR, "storage_pools.json")

    # ── 存储池管理 ─────────────────────────────────────────

    def list_pools(self):
        """列出所有存储池"""
        if self._simulated:
            return self._get_simulated_pools()

        try:
            import libvirt
            conn = libvirt.open(Config.LIBVIRT_URI)
            pools = []
            for pool_name in conn.listStoragePools() + conn.listDefinedStoragePools():
                pool = conn.storagePoolLookupByName(pool_name)
                info = pool.info()
                xml_desc = pool.XMLDesc()
                tree = ET.fromstring(xml_desc)
                target = tree.find("target")

                pools.append({
                    "name": pool_name,
                    "uuid": pool.UUIDString(),
                    "type": tree.get("type", "dir"),
                    "active": pool.isActive(),
                    "autostart": pool.autostart(),
                    "capacity_bytes": info[1],
                    "allocation_bytes": info[2],
                    "available_bytes": info[3],
                    "path": target.findtext("path", "") if target is not None else "",
                })
            conn.close()
            return pools
        except (ImportError, Exception) as e:
            return self._get_simulated_pools()

    def create_pool(self, name, pool_type="dir", path=None):
        """创建存储池"""
        if not path:
            path = os.path.join(Config.STORAGE_DIR, name)

        if self._simulated:
            return self._simulated_create_pool(name, pool_type, path)

        try:
            import libvirt
            conn = libvirt.open(Config.LIBVIRT_URI)
            os.makedirs(path, exist_ok=True)

            xml = f"""<pool type='{pool_type}'>
                <name>{name}</name>
                <target>
                    <path>{path}</path>
                    <permissions>
                        <mode>0755</mode>
                        <owner>0</owner>
                        <group>0</group>
                    </permissions>
                </target>
            </pool>"""

            pool = conn.storagePoolDefineXML(xml)
            pool.setAutostart(True)
            pool.create()
            conn.close()
            return {"success": True}
        except (ImportError, Exception) as e:
            return {"success": False, "error": str(e)}

    def delete_pool(self, name):
        """删除存储池"""
        if self._simulated:
            return self._simulated_delete_pool(name)

        try:
            import libvirt
            conn = libvirt.open(Config.LIBVIRT_URI)
            pool = conn.storagePoolLookupByName(name)
            if pool.isActive():
                pool.destroy()
            pool.undefine()
            conn.close()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 卷管理 ────────────────────────────────────────────

    def list_volumes(self, pool_name):
        """列出存储卷 (模拟模式: 从 JSON + 真实文件读取)"""
        if self._simulated:
            return self._get_simulated_volumes(pool_name)

        try:
            import libvirt
            conn = libvirt.open(Config.LIBVIRT_URI)
            pool = conn.storagePoolLookupByName(pool_name)
            volumes = []
            for vol_name in pool.listVolumes():
                vol = pool.storageVolLookupByName(vol_name)
                info = vol.info()
                xml_desc = vol.XMLDesc()
                tree = ET.fromstring(xml_desc)
                target = tree.find("target")
                fmt = target.findtext("format/@type", "raw") if target is not None else "raw"

                volumes.append({
                    "name": vol_name,
                    "pool": pool_name,
                    "capacity_bytes": info[1],
                    "allocation_bytes": info[2],
                    "format": fmt,
                    "path": vol.path(),
                })
            conn.close()
            return volumes
        except (ImportError, Exception) as e:
            return []

    def create_volume(self, pool_name, name, size_gb, fmt="qcow2"):
        """创建存储卷"""
        if self._simulated:
            fpath = os.path.join(Config.VM_IMAGE_DIR, name)
            # 模拟创建: 写入元数据 JSON 而非真实分配磁盘
            meta = {
                "name": name,
                "pool": pool_name,
                "size_gb": size_gb,
                "format": fmt,
                "path": fpath,
                "simulated": True,
            }
            # 写入一个很小的标记文件
            with open(fpath + ".meta", "w") as f:
                json.dump(meta, f)
            # 同时保存到模拟卷列表
            saved = self._load_simulated_volumes()
            saved.append({
                "name": name,
                "pool": pool_name,
                "capacity_bytes": size_gb * 1024**3,
                "allocation_bytes": 0,
                "format": fmt,
                "path": fpath,
            })
            self._save_simulated_volumes(saved)
            return {"success": True, "path": fpath}

        try:
            import libvirt
            conn = libvirt.open(Config.LIBVIRT_URI)
            pool = conn.storagePoolLookupByName(pool_name)

            xml = f"""<volume>
                <name>{name}</name>
                <capacity unit='G'>{size_gb}</capacity>
                <target>
                    <format type='{fmt}'/>
                    <permissions>
                        <mode>0644</mode>
                    </permissions>
                </target>
            </volume>"""

            vol = pool.storageVolCreateXML(xml)
            conn.close()
            return {"success": True, "path": vol.path()}
        except (ImportError, Exception) as e:
            return {"success": False, "error": str(e)}

    def delete_volume(self, pool_name, vol_name):
        """删除存储卷"""
        if self._simulated:
            # 检查卷是否存在
            saved = self._load_simulated_volumes()
            existed = any(v["name"] == vol_name for v in saved)
            if not existed:
                # 也检查默认卷
                defaults = [
                    {"name": "ubuntu-24.04-server.qcow2", "pool": "default"},
                ]
                existed = any(v["name"] == vol_name for v in defaults)
            if not existed:
                return {"success": False, "error": f"卷 '{vol_name}' 不存在"}

            fpath = os.path.join(Config.VM_IMAGE_DIR, vol_name)
            # 删除元数据文件和真实文件
            for p in [fpath, fpath + ".meta"]:
                if os.path.exists(p):
                    os.remove(p)
            # 从模拟卷列表移除
            saved = [v for v in saved if v["name"] != vol_name]
            self._save_simulated_volumes(saved)
            return {"success": True}

        try:
            import libvirt
            conn = libvirt.open(Config.LIBVIRT_URI)
            pool = conn.storagePoolLookupByName(pool_name)
            vol = pool.storageVolLookupByName(vol_name)
            vol.delete()
            conn.close()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def resize_volume(self, pool_name, vol_name, new_size_gb):
        """扩容卷"""
        if self._simulated:
            saved = self._load_simulated_volumes()
            for v in saved:
                if v["name"] == vol_name:
                    v["capacity_bytes"] = new_size_gb * 1024**3
                    self._save_simulated_volumes(saved)
                    break
            return {"success": True}

        try:
            import libvirt
            conn = libvirt.open(Config.LIBVIRT_URI)
            pool = conn.storagePoolLookupByName(pool_name)
            vol = pool.storageVolLookupByName(vol_name)
            vol.resize(new_size_gb * 1024 * 1024 * 1024)
            conn.close()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── ISO 镜像管理 ──────────────────────────────────────

    def list_isos(self):
        """列出可用的 ISO 镜像"""
        isos = []
        iso_dir = Config.ISO_DIR
        if not os.path.exists(iso_dir):
            return isos

        for fname in os.listdir(iso_dir):
            fpath = os.path.join(iso_dir, fname)
            if os.path.isfile(fpath) and fname.endswith((".iso", ".ISO")):
                size_bytes = os.path.getsize(fpath)
                isos.append({
                    "name": fname,
                    "path": fpath,
                    "size_mb": round(size_bytes / (1024 * 1024), 1),
                    "modified": datetime.fromtimestamp(os.path.getmtime(fpath)).isoformat(),
                })
        return isos

    def upload_iso(self, name, source_path_or_file):
        """
        上传/导入 ISO 镜像
        source_path_or_file 可以是本地路径或文件对象
        """
        dest = os.path.join(Config.ISO_DIR, name)
        os.makedirs(Config.ISO_DIR, exist_ok=True)

        if os.path.exists(source_path_or_file):
            shutil.copy2(source_path_or_file, dest)
        else:
            # 写入文件内容
            with open(dest, "wb") as f:
                if hasattr(source_path_or_file, "read"):
                    f.write(source_path_or_file.read())
                else:
                    f.write(source_path_or_file)

        return {"success": True, "path": dest, "name": name}

    def delete_iso(self, name):
        """删除 ISO"""
        path = os.path.join(Config.ISO_DIR, name)
        if os.path.exists(path):
            os.remove(path)
            return {"success": True}
        return {"success": False, "error": "ISO not found"}

    # ── 磁盘操作 (直接 qemu-img) ───────────────────────────

    def create_disk_image(self, path, size_gb, fmt="qcow2"):
        """通过 qemu-img 创建磁盘镜像"""
        import subprocess
        cmd = ["qemu-img", "create", "-f", fmt, path, f"{size_gb}G"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return {"success": False, "error": result.stderr}
        return {"success": True, "path": path}

    def convert_disk_image(self, source, target, fmt="qcow2"):
        """转换磁盘镜像格式"""
        import subprocess
        cmd = ["qemu-img", "convert", "-O", fmt, source, target]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return {"success": False, "error": result.stderr}
        return {"success": True, "path": target}

    def get_disk_info(self, path):
        """获取磁盘信息"""
        import subprocess
        cmd = ["qemu-img", "info", "--output", "json", path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return json.loads(result.stdout)
        return {"error": result.stderr}

    # ── 模拟模式 ───────────────────────────────────────────

    _volumes_file = None

    @property
    def _volumes_data_file(self):
        if self._volumes_file is None:
            self._volumes_file = os.path.join(Config.CONFIG_DIR, "simulated_volumes.json")
        return self._volumes_file

    def _load_simulated_volumes(self):
        if os.path.exists(self._volumes_data_file):
            with open(self._volumes_data_file) as f:
                return json.load(f)
        return []

    def _save_simulated_volumes(self, volumes):
        os.makedirs(os.path.dirname(self._volumes_data_file), exist_ok=True)
        with open(self._volumes_data_file, "w") as f:
            json.dump(volumes, f, indent=2)

    def _get_simulated_pools(self):
        defaults = [
            {
                "name": "default",
                "uuid": "pool-default-0001",
                "type": "dir",
                "active": True,
                "autostart": True,
                "capacity_bytes": 500 * 1024**3,
                "allocation_bytes": 120 * 1024**3,
                "available_bytes": 380 * 1024**3,
                "path": "/var/lib/libvirt/images",
            },
            {
                "name": "vm-images",
                "uuid": "pool-vm-0002",
                "type": "dir",
                "active": True,
                "autostart": True,
                "capacity_bytes": 200 * 1024**3,
                "allocation_bytes": 50 * 1024**3,
                "available_bytes": 150 * 1024**3,
                "path": Config.VM_IMAGE_DIR,
            },
        ]

        saved = []
        if os.path.exists(self._pools_file):
            with open(self._pools_file) as f:
                saved = json.load(f)
        return defaults + saved

    def _get_simulated_volumes(self, pool_name=None):
        """获取模拟卷列表，可按 pool 名过滤"""
        all_vols = self._load_simulated_volumes()
        defaults = [
            {"name": "ubuntu-24.04-server.qcow2", "pool": "default",
             "capacity_bytes": 20 * 1024**3, "allocation_bytes": 5 * 1024**3,
             "format": "qcow2", "path": f"{Config.VM_IMAGE_DIR}/ubuntu-24.04-server.qcow2"},
        ]
        all_vols = defaults + all_vols
        if pool_name:
            return [v for v in all_vols if v.get("pool") == pool_name]
        return all_vols

    def _simulated_create_pool(self, name, pool_type, path):
        saved = []
        if os.path.exists(self._pools_file):
            with open(self._pools_file) as f:
                saved = json.load(f)
        saved.append({
            "name": name, "type": pool_type, "active": True,
            "autostart": True, "path": path,
            "capacity_bytes": 100 * 1024**3,
            "allocation_bytes": 0,
            "available_bytes": 100 * 1024**3,
        })
        os.makedirs(os.path.dirname(self._pools_file), exist_ok=True)
        with open(self._pools_file, "w") as f:
            json.dump(saved, f, indent=2)
        return {"success": True}

    def _simulated_delete_pool(self, name):
        saved = []
        if os.path.exists(self._pools_file):
            with open(self._pools_file) as f:
                saved = json.load(f)
        saved = [p for p in saved if p["name"] != name]
        with open(self._pools_file, "w") as f:
            json.dump(saved, f, indent=2)
        return {"success": True}
