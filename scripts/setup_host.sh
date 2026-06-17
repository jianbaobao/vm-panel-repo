#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
# VM Management Panel — 宿主机制备脚本
# 适用于 Debian/Ubuntu 系统
# ═══════════════════════════════════════════════════════════

set -e

echo "=== 安装 KVM/QEMU/libvirt 依赖 ==="

# 1. 检查虚拟化支持
if grep -q -E '(vmx|svm)' /proc/cpuinfo; then
    echo "[OK] CPU 支持硬件虚拟化 (VT-x/AMD-V)"
else
    echo "[WARN] CPU 未检测到硬件虚拟化，将使用软件模拟 (性能差)"
fi

# 2. 安装软件包
apt-get update
apt-get install -y \
    qemu-kvm \
    qemu-system-x86 \
    libvirt-daemon-system \
    libvirt-clients \
    bridge-utils \
    virt-manager \
    virtinst \
    cpu-checker \
    python3-pip \
    python3-venv \
    nginx \
    novnc

# 3. 启动 libvirtd
systemctl enable --now libvirtd

# 4. 将当前用户加入 libvirt 组
if [ -n "$SUDO_USER" ]; then
    usermod -aG libvirt "$SUDO_USER"
    usermod -aG kvm "$SUDO_USER"
    echo "[OK] 用户 $SUDO_USER 已加入 libvirt/kvm 组"
    echo "    请重新登录使组权限生效"
fi

# 5. 创建默认存储池
virsh pool-define-as default dir --target /var/lib/libvirt/images
virsh pool-start default
virsh pool-autostart default

echo ""
echo "=== 安装完成 ==="
echo "请重新登录后运行: python3 app.py"
echo "访问地址: http://localhost:8080"
