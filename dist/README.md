# VM Management Panel — 分发包

| 文件 | 大小 | 说明 |
|------|------|------|
| `VM-Panel-Windows.zip` | ~92 KB | Windows 便携版 |
| `vm-panel-linux.tar.gz` | ~68 KB | Linux 部署版 |
| `build_all.py` | 构建脚本 | 重新生成两个包 |
| `version.json` | 版本信息 | 构建日期等 |

## Windows 便携版

```bash
1. 解压 VM-Panel-Windows.zip
2. 双击 start.bat
3. 浏览器打开 http://localhost:5000
```

**要求**: Python 3.8+ (首次运行自动安装 Flask)

## Linux 部署版

```bash
# 方式一：一键部署
tar xzf vm-panel-linux.tar.gz
cd vm-panel-linux
sudo bash deploy/linux/install.sh

# 方式二：手动启动
tar xzf vm-panel-linux.tar.gz
cd vm-panel-linux
python3 deploy/run.py
```

**要求**: Ubuntu 22.04+ / Debian 12+ (自动安装 KVM/libvirt)
