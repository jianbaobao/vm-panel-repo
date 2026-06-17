"""
VM Management Panel — Linux 生产版配置

启用 KVM/QEMU + libvirt 后端。需要 root 权限或 libvirt 组。
"""
import os, sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Config:
    # Flask
    SECRET_KEY = os.environ.get("VM_PANEL_SECRET", "linux-prod-secret-change-me")
    DEBUG = os.environ.get("VM_PANEL_DEBUG", "false").lower() == "true"
    HOST = os.environ.get("VM_PANEL_HOST", "0.0.0.0")
    PORT = int(os.environ.get("VM_PANEL_PORT", 80))

    # libvirt — 生产模式连接真实 libvirt
    LIBVIRT_URI = os.environ.get("LIBVIRT_URI", "qemu:///system")
    SIMULATE_LIBVIRT = os.environ.get("SIMULATE_LIBVIRT", "false").lower() == "true"

    STORAGE_DIR = os.environ.get("VM_STORAGE_DIR", "/var/lib/vm-panel")
    ISO_DIR = os.path.join(STORAGE_DIR, "isos")
    VM_IMAGE_DIR = os.path.join(STORAGE_DIR, "images")
    CONFIG_DIR = os.path.join(STORAGE_DIR, "config")

    QEMU_BIN = "/usr/bin/qemu-system-x86_64"
    DEFAULT_OS_TYPE = "linux"
    DEFAULT_OS_VARIANT = "ubuntu24.04"

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



