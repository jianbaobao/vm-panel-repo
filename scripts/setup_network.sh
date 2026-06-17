#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
# VM Management Panel — 桥接网络配置
# 将物理网卡桥接到 br0，使 VM 可直接获取局域网 IP
# ═══════════════════════════════════════════════════════════

set -e

INTERFACE="${1:-eth0}"
BRIDGE_NAME="${2:-br0}"

echo "=== 创建桥接网络 ==="
echo "  物理网卡: $INTERFACE"
echo "  网桥名称: $BRIDGE_NAME"

# 检测发行版
if [ -f /etc/debian_version ]; then
    # Debian/Ubuntu — netplan 方式
    echo ""
    echo "=== Netplan 配置 ==="
    NETPLAN_FILE="/etc/netplan/01-${BRIDGE_NAME}.yaml"

    cat > "$NETPLAN_FILE" <<EOF
network:
  version: 2
  ethernets:
    ${INTERFACE}:
      dhcp4: false
  bridges:
    ${BRIDGE_NAME}:
      interfaces: [${INTERFACE}]
      dhcp4: true
      parameters:
        stp: true
        forward-delay: 0
EOF

    echo "写入 $NETPLAN_FILE"
    echo "执行 netplan apply 应用..."
    netplan apply

elif [ -f /etc/redhat-release ]; then
    # RHEL/CentOS/Fedora — nmcli 方式
    echo ""
    echo "=== NetworkManager 配置 ==="

    # 创建桥接连接
    nmcli connection add type bridge con-name "${BRIDGE_NAME}" ifname "${BRIDGE_NAME}"
    nmcli connection modify "${BRIDGE_NAME}" ipv4.method auto

    # 将物理网卡加入桥接
    nmcli connection add type ethernet slave-type bridge con-name "bridge-${INTERFACE}" \
        ifname "${INTERFACE}" master "${BRIDGE_NAME}"

    # 停用原有连接
    ORIG_CONN=$(nmcli -t -f NAME,DEVICE connection show --active | grep "${INTERFACE}" | cut -d: -f1)
    if [ -n "$ORIG_CONN" ]; then
        nmcli connection down "$ORIG_CONN" || true
    fi

    # 启用桥接
    nmcli connection up "${BRIDGE_NAME}"

    echo "[OK] 桥接网络已配置"
else
    # 通用方式 (iproute2)
    echo ""
    echo "=== 使用 iproute2 手动配置 (临时) ==="

    ip link add name "${BRIDGE_NAME}" type bridge
    ip link set "${BRIDGE_NAME}" up
    ip link set "${INTERFACE}" master "${BRIDGE_NAME}"

    echo "[OK] 临时网桥 ${BRIDGE_NAME} 已创建"
    echo "    持久化配置请参考发行版文档"
fi

echo ""
echo "=== 桥接信息 ==="
ip addr show "${BRIDGE_NAME}"
echo ""
echo "虚拟机 XML 中使用:"
echo "  <interface type='bridge'>"
echo "    <source bridge='${BRIDGE_NAME}'/>"
echo "  </interface>"
