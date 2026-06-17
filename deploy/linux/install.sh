#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
# VM Panel — Linux 生产版一键部署脚本
# 适用: Ubuntu 22.04+ / Debian 12+
# ═══════════════════════════════════════════════════════════
set -e

APP_DIR="/opt/vm-panel"
SERVICE_NAME="vm-panel"
CONFIG_DIR="/var/lib/vm-panel"

echo "========================================"
echo " VM Panel — Linux 生产版安装"
echo "========================================"

# 1. 检查 root
if [ "$EUID" -ne 0 ]; then
    echo "[!] 请以 root 身份运行: sudo bash install.sh"
    exit 1
fi

# 2. 安装系统依赖
echo "[1/5] 安装系统依赖..."
apt-get update -qq
apt-get install -y -qq \
    qemu-kvm qemu-system-x86 libvirt-daemon-system libvirt-clients \
    bridge-utils virtinst python3 python3-pip python3-venv \
    nginx 2>/dev/null

# 3. 启动 libvirtd
systemctl enable --now libvirtd

# 4. 部署应用
echo "[2/5] 部署应用..."
mkdir -p "$APP_DIR"
cp -r "$(dirname "$0")/../.." "$APP_DIR/"
cd "$APP_DIR"

# 创建 Python 虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -q

# 5. 创建数据目录
echo "[3/5] 创建数据目录..."
mkdir -p "$CONFIG_DIR"/{isos,images,config}
chmod 755 "$CONFIG_DIR"

# 6. 安装 systemd 服务
echo "[4/5] 安装 systemd 服务..."
cat > "/etc/systemd/system/$SERVICE_NAME.service" << 'SERVICEEOF'
[Unit]
Description=VM Management Panel
After=libvirtd.service network-online.target
Requires=libvirtd.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/vm-panel
ExecStart=/opt/vm-panel/venv/bin/python /opt/vm-panel/deploy/run.py
Restart=always
RestartSec=5
Environment=VM_PANEL_HOST=0.0.0.0
Environment=VM_PANEL_PORT=80
Environment=VM_PANEL_DEBUG=false
Environment=VM_STORAGE_DIR=/var/lib/vm-panel

[Install]
WantedBy=multi-user.target
SERVICEEOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

# 7. 加入 libvirt 组
echo "[5/5] 配置权限..."
usermod -aG libvirt,kvm root 2>/dev/null

# 启动服务
systemctl start "$SERVICE_NAME"

echo ""
echo "========================================"
echo " ✅ VM Panel Linux 版部署完成!"
echo "========================================"
echo "  访问地址: http://$(hostname -I | awk '{print $1}')"
echo "  管理命令:"
echo "    systemctl status $SERVICE_NAME"
echo "    systemctl restart $SERVICE_NAME"
echo "    journalctl -u $SERVICE_NAME -f"
echo "  存储目录: $CONFIG_DIR"
echo "========================================"
