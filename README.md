# VM Management Panel

> 类 Proxmox VE / VMware Workstation Pro 的虚拟机管理面板  
> 基于 Linux KVM/QEMU + libvirt，提供 Web 管理界面

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey)

---

## 功能概览

| 模块 | 功能 |
|------|------|
| 📊 **仪表盘** | 宿主机 CPU/内存/存储概览、VM 运行状态 |
| 🖥️ **虚拟机** | 创建/启动/关机/强制断电/重启/删除/快照管理 |
| 🌐 **网络** | NAT 网络、隔离网络、桥接网络、DHCP 配置、系统网桥管理 |
| 💾 **存储** | 存储池 (dir/LVM)、存储卷、磁盘扩容、ISO 上传 |
| 📀 **安装介质** | 上传/管理 ISO 镜像 |
| 🔧 **快照** | VM 快照创建、回滚、删除 |
| 🖱️ **VNC 控制台** | VNC 端口查询 (支持 noVNC 集成) |

## 界面截图 (文字描述)

- **深色主题** Web UI，响应式设计
- 左侧导航：仪表盘 → 虚拟机 → 网络 → 存储 → 设置
- 虚拟机列表：名称、状态(vCPU/内存/磁盘)、一键操作按钮组
- 创建表单：快速模板选择 + 自定义配置
- 存储管理：池/卷进度条展示，创建/删除操作

## 快速开始

### 1. 环境要求

- Linux 系统 (推荐 Ubuntu 22.04+/Debian 12+)
- CPU 支持硬件虚拟化 (Intel VT-x / AMD-V)
- Python 3.8+

### 2. 安装宿主机依赖

```bash
# 使用 root 或 sudo 运行
bash scripts/setup_host.sh
```

该脚本会安装：KVM/QEMU、libvirt守护进程、桥接工具、Python 依赖。

### 3. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 4. 启动面板

```bash
cd vm-panel
python app.py
```

访问 http://localhost:8080

### 无 libvirt 环境（演示/开发模式）

面板在未检测到 libvirt 时自动进入 **模拟模式**，使用本地 JSON 文件模拟 VM 状态。
无需 KVM/libvirt 即可体验全部功能。

```bash
# 强制使用模拟模式
SIMULATE_LIBVIRT=true python app.py
```

## 配置说明

编辑 `config.py` 或创建 `config.json` 覆盖默认配置：

```json
{
    "secret_key": "your-secret-key",
    "libvirt_uri": "qemu:///system",
    "simulate_libvirt": false,
    "port": 8080,
    "host": "0.0.0.0"
}
```

也可以通过环境变量配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VM_PANEL_SECRET` | `vm-panel-secret-key-change-me` | Flask 密钥 |
| `VM_PANEL_HOST` | `0.0.0.0` | 监听地址 |
| `VM_PANEL_PORT` | `8080` | 监听端口 |
| `VM_PANEL_DEBUG` | `true` | 调试模式 |
| `LIBVIRT_URI` | `qemu:///system` | libvirt 连接 URI |
| `SIMULATE_LIBVIRT` | `true` | 模拟模式开关 |

## 网络配置

### NAT 网络 (默认)

虚拟机通过 virbr0 共享宿主机 IP，适合测试环境。

### 桥接网络

虚拟机直接获取局域网 IP，适合生产环境：

```bash
# 创建桥接 br0，桥接 eth0
bash scripts/setup_network.sh eth0 br0
```

然后在 Web 面板的创建 VM 时选择 `br0` 网络。

## API 参考

所有操作均有 RESTful API：

### 系统
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/host/info` | 宿主机信息 |
| GET | `/api/host/stats` | 实时性能 |
| GET | `/api/templates` | VM 模板 |

### 虚拟机
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/vms` | VM 列表 |
| POST | `/api/vms` | 创建 VM |
| GET | `/api/vms/<name>` | VM 详情 |
| POST | `/api/vms/<name>/start` | 启动 |
| POST | `/api/vms/<name>/shutdown` | 关机 |
| POST | `/api/vms/<name>/force-stop` | 强制断电 |
| POST | `/api/vms/<name>/restart` | 重启 |
| DELETE | `/api/vms/<name>` | 删除 VM |
| GET | `/api/vms/<name>/vnc-port` | VNC 端口 |

### 快照
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/vms/<name>/snapshots` | 快照列表 |
| POST | `/api/vms/<name>/snapshots` | 创建快照 |
| POST | `/api/vms/<name>/snapshots/<snap>/revert` | 回滚 |
| DELETE | `/api/vms/<name>/snapshots/<snap>` | 删除 |

### 网络
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/networks` | 网络列表 |
| POST | `/api/networks` | 创建网络 |
| DELETE | `/api/networks/<name>` | 删除网络 |
| POST | `/api/networks/<name>/activate` | 激活 |
| POST | `/api/networks/<name>/deactivate` | 停用 |
| GET | `/api/bridges` | 系统网桥 |
| POST | `/api/bridges` | 创建网桥 |

### 存储
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/pools` | 存储池列表 |
| POST | `/api/pools` | 创建存储池 |
| DELETE | `/api/pools/<name>` | 删除池 |
| GET | `/api/pools/<pool>/volumes` | 卷列表 |
| POST | `/api/pools/<pool>/volumes` | 创建卷 |
| DELETE | `/api/pools/<pool>/volumes/<vol>` | 删除卷 |
| POST | `/api/pools/<pool>/volumes/<vol>/resize` | 扩容 |

### ISO
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/isos` | ISO 列表 |
| POST | `/api/isos/upload` | 上传 ISO |
| DELETE | `/api/isos/<name>` | 删除 ISO |

## 项目结构

```
vm-panel/
├── app.py                    # Flask 主应用 + 路由
├── config.py                 # 配置
├── libvirt_manager.py        # libvirt 抽象层 (含模拟模式)
├── network_manager.py        # 网络管理
├── storage_manager.py        # 存储管理
├── requirements.txt          # Python 依赖
├── README.md                 # 本文档
├── scripts/
│   ├── setup_host.sh         # 宿主机环境部署
│   └── setup_network.sh      # 桥接网络配置
├── templates/                # Jinja2 模板
│   ├── base.html             # 基础布局 (深色主题)
│   ├── dashboard.html        # 仪表盘
│   ├── vms.html              # VM 列表
│   ├── vm_create.html        # 创建 VM
│   ├── vm_detail.html        # VM 详情 + 控制台
│   ├── networks.html         # 网络管理
│   ├── network_create.html   # 创建网络
│   ├── storage.html          # 存储管理
│   ├── isos.html             # ISO 管理
│   └── settings.html         # 系统设置
├── static/
│   ├── css/style.css         # 样式 (暗色主题)
│   └── js/main.js            # JS 交互层
├── storage/
│   ├── isos/                 # ISO 镜像存储
│   └── images/               # VM 磁盘镜像
└── config/                   # 运行时配置 (JSON)
```

## 与 PVE/VMware 功能对比

| 功能 | 本面板 | Proxmox VE | VMware WS Pro |
|------|--------|-------------|---------------|
| KVM/QEMU 虚拟化 | ✅ | ✅ | ❌ (自家引擎) |
| Web 管理界面 | ✅ | ✅ | ❌ (桌面版) |
| 桥接网络 | ✅ | ✅ | ✅ |
| 快照管理 | ✅ | ✅ | ✅ |
| VNC/SPICE 控制台 | ✅ | ✅ | ✅ |
| 集群管理 | ❌ | ✅ | ❌ |
| 高可用 (HA) | ❌ | ✅ | ❌ |
| 虚拟机模板 | ✅ (基础) | ✅ (高级) | ✅ |
| 存储实时迁移 | ❌ | ✅ | ❌ |
| 嵌套虚拟化 | ✅ (KVM) | ✅ | ✅ |

## 开发

```bash
# 开发模式 (热重载)
python app.py

# 或设置环境
export FLASK_ENV=development
export VM_PANEL_DEBUG=true
python app.py
```

## License

MIT
