"""
VM Management Panel - 配置模块
"""
import os
import json

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    # Flask
    SECRET_KEY = os.environ.get("VM_PANEL_SECRET", "vm-panel-secret-key-change-me")
    DEBUG = os.environ.get("VM_PANEL_DEBUG", "true").lower() == "true"
    HOST = os.environ.get("VM_PANEL_HOST", "0.0.0.0")
    PORT = int(os.environ.get("VM_PANEL_PORT", 8080))

    # libvirt
    LIBVIRT_URI = os.environ.get("LIBVIRT_URI", "qemu:///system")
    # 当系统没有 libvirt 时使用模拟模式
    SIMULATE_LIBVIRT = os.environ.get("SIMULATE_LIBVIRT", "true").lower() == "true"

    # 存储路径
    STORAGE_DIR = os.path.join(BASE_DIR, "storage")
    ISO_DIR = os.path.join(STORAGE_DIR, "isos")
    VM_IMAGE_DIR = os.path.join(STORAGE_DIR, "images")
    CONFIG_DIR = os.path.join(BASE_DIR, "config")

    # QEMU
    QEMU_BIN = "/usr/bin/qemu-system-x86_64"
    DEFAULT_OS_TYPE = "linux"
    DEFAULT_OS_VARIANT = "ubuntu24.04"

    # 默认模板配置
    VM_TEMPLATES = {
        "tiny": {
            "name": "微型 (1C/512M/8G)",
            "vcpu": 1,
            "memory_mb": 512,
            "disk_gb": 8,
        },
        "small": {
            "name": "小型 (2C/2G/20G)",
            "vcpu": 2,
            "memory_mb": 2048,
            "disk_gb": 20,
        },
        "medium": {
            "name": "中型 (4C/4G/50G)",
            "vcpu": 4,
            "memory_mb": 4096,
            "disk_gb": 50,
        },
        "large": {
            "name": "大型 (8C/8G/100G)",
            "vcpu": 8,
            "memory_mb": 8192,
            "disk_gb": 100,
        },
    }

    # 默认网络
    DEFAULT_NETWORKS = [
        {
            "name": "default",
            "type": "nat",
            "bridge": "virbr0",
            "subnet": "192.168.122.0/24",
            "dhcp_start": "192.168.122.2",
            "dhcp_end": "192.168.122.254",
        }
    ]

    @classmethod
    def ensure_dirs(cls):
        """确保所有存储目录存在"""
        for d in [cls.STORAGE_DIR, cls.ISO_DIR, cls.VM_IMAGE_DIR, cls.CONFIG_DIR]:
            os.makedirs(d, exist_ok=True)

    @classmethod
    def cleanup_simulated_volumes(cls):
        """清理模拟卷产生的元数据文件"""
        meta_dir = cls.VM_IMAGE_DIR
        if os.path.exists(meta_dir):
            for f in os.listdir(meta_dir):
                if f.endswith(".meta"):
                    os.remove(os.path.join(meta_dir, f))


# 加载配置文件
config_path = os.path.join(os.path.dirname(__file__), "config.json")
if os.path.exists(config_path):
    with open(config_path) as f:
        overrides = json.load(f)
    for k, v in overrides.items():
        setattr(Config, k.upper(), v)

Config.ensure_dirs()
