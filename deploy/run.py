"""
VM Management Panel — 平台检测入口

自动检测操作系统并加载对应配置。
  - Linux: deploy/linux/config_linux.py  (KVM/libvirt 生产)
  - Windows: deploy/windows/config_win.py (模拟模式开发)
"""
import os, sys
import platform

# 检测平台
SYSTEM = platform.system().lower()

# 确定配置路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if SYSTEM == "linux":
    config_path = os.path.join(BASE_DIR, "deploy", "linux", "config_linux.py")
    deploy_dir = os.path.join(BASE_DIR, "deploy", "linux")
    config_name = "config_linux"
elif SYSTEM == "windows":
    config_path = os.path.join(BASE_DIR, "deploy", "windows", "config_win.py")
    deploy_dir = os.path.join(BASE_DIR, "deploy", "windows")
    config_name = "config_win"
else:
    # 未知系统 — 使用默认 config
    config_path = os.path.join(BASE_DIR, "config.py")
    deploy_dir = os.path.join(BASE_DIR, "deploy")
    config_name = "config"

# 加载配置模块
if os.path.exists(config_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(config_name, config_path)
    config_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_mod)
    # 将配置注入 sys.modules 供 app.py 使用
    sys.modules["config"] = config_mod
else:
    # 回退到默认 config.py
    sys.path.insert(0, BASE_DIR)
    import config as config_mod

# 导入并启动应用
sys.path.insert(0, BASE_DIR)
from app import app as application

if __name__ == "__main__":
    print(f"╔═══════════════════════════════════════════════╗")
    print(f"║     VM Management Panel - {SYSTEM.upper():10s} Edition    ║")
    print(f"║     {'Simulated' if config_mod.Config.SIMULATE_LIBVIRT else 'Production'} mode{' ' * 20}║")
    print(f"╚═══════════════════════════════════════════════╝")
    print(f"  * Platform: {SYSTEM}")
    print(f"  * Config: {config_path}")
    print(f"  * Simulated: {config_mod.Config.SIMULATE_LIBVIRT}")
    print(f"  * Address: http://{config_mod.Config.HOST}:{config_mod.Config.PORT}")
    print(f"  * Storage: {config_mod.Config.STORAGE_DIR}")
    print()

    application.run(
        host=config_mod.Config.HOST,
        port=config_mod.Config.PORT,
        debug=config_mod.Config.DEBUG,
    )
