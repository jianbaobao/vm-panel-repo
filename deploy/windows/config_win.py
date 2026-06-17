"""
VM Management Panel — Windows 开发版配置

默认使用模拟模式 (无 KVM/libvirt)。支持 Hyper-V 可选后端。
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Config:
    # Flask
    SECRET_KEY = os.environ.get("VM_PANEL_SECRET", "win-dev-secret")
    DEBUG = os.environ.get("VM_PANEL_DEBUG", "true").lower() == "true"
    HOST = os.environ.get("VM_PANEL_HOST", "127.0.0.1")
    PORT = int(os.environ.get("VM_PANEL_PORT", 5000))

    # libvirt — Windows 版默认模拟
    LIBVIRT_URI = ""
    SIMULATE_LIBVIRT = os.environ.get("SIMULATE_LIBVIRT", "true").lower() == "true"

    # 存储路径 (Windows 本地)
    STORAGE_DIR = os.path.join(BASE_DIR, "storage")
    ISO_DIR = os.path.join(STORAGE_DIR, "isos")
    VM_IMAGE_DIR = os.path.join(STORAGE_DIR, "images")
    CONFIG_DIR = os.path.join(BASE_DIR, "config")

    # QEMU (Windows 下可选)
    QEMU_BIN = "qemu-system-x86_64.exe"
    DEFAULT_OS_TYPE = "linux"
    DEFAULT_OS_VARIANT = "ubuntu24.04"

    # VM 模板
    VM_TEMPLATES = {
        "tiny": {"name": "Micro (1C/512M/8G)", "vcpu": 1, "memory_mb": 512, "disk_gb": 8},
        "small": {"name": "Small (2C/2G/20G)", "vcpu": 2, "memory_mb": 2048, "disk_gb": 20},
        "medium": {"name": "Medium (4C/4G/50G)", "vcpu": 4, "memory_mb": 4096, "disk_gb": 50},
        "large": {"name": "Large (8C/8G/100G)", "vcpu": 8, "memory_mb": 8192, "disk_gb": 100},
    }

    @classmethod
    def ensure_dirs(cls):
        for d in [cls.STORAGE_DIR, cls.ISO_DIR, cls.VM_IMAGE_DIR, cls.CONFIG_DIR]:
            os.makedirs(d, exist_ok=True)

Config.ensure_dirs()
