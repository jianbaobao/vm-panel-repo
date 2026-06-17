"""
VM Panel — 构建分发包

生成:
  - dist/VM-Panel-Windows.zip     (便携版)
  - dist/vm-panel-linux.tar.gz    (部署版)
"""
import os, sys, shutil, zipfile, tarfile, subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)  # vm-panel/
DIST = BASE
WIN_DIR = os.path.join(DIST, "VM-Panel-Windows")
LINUX_DIR = os.path.join(DIST, "vm-panel-linux")

# 需要排除的文件/目录
EXCLUDE = {
    "__pycache__", "*.pyc", ".pyc", "test_all.py", "test_wsl.py",
    "wsl_*.b64", "wsl_*.txt", "encode_script.py",
    "wsl_all.b64", "wsl_b64_payload.txt", "wsl_config.b64",
    "wsl_event_log.b64", "wsl_i18n.b64", "wsl_libvirt_manager.b64",
    "wsl_network_manager.b64", "wsl_storage_manager.b64",
    "dist", ".reasonix",
}

def should_include(name):
    for pat in EXCLUDE:
        if name.endswith(pat) or name == pat:
            return False
    return True


def collect_files(src_dir):
    """收集需要打包的文件列表"""
    files = []
    for root, dirs, fnames in os.walk(src_dir):
        # 跳过排除目录
        dirs[:] = [d for d in dirs if should_include(d)]
        for f in fnames:
            if should_include(f):
                full = os.path.join(root, f)
                # 获取相对路径
                rel = os.path.relpath(full, ROOT)
                files.append(rel)
    return sorted(files)


def build_windows_zip():
    """构建 Windows ZIP 包"""
    print("=" * 50)
    print("  构建 Windows 便携版...")
    print("=" * 50)

    zip_path = os.path.join(DIST, "VM-Panel-Windows.zip")
    files = collect_files(ROOT)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 项目文件
        for rel in files:
            full = os.path.join(ROOT, rel)
            zf.write(full, rel)
            print(f"  + {rel}")
        # 添加启动脚本到根目录
        start_bat = os.path.join(BASE, "VM-Panel-Windows", "start.bat")
        if os.path.exists(start_bat):
            zf.write(start_bat, "start.bat")
            print(f"  + start.bat")

    size_mb = os.path.getsize(zip_path) / 1024 / 1024
    print(f"\n  ✅ Windows ZIP: {zip_path} ({size_mb:.1f} MB, {len(files)} files)")
    return zip_path


def build_linux_tar():
    """构建 Linux tar.gz 包"""
    print("\n" + "=" * 50)
    print("  构建 Linux 部署包...")
    print("=" * 50)

    # 收集文件并复制到临时目录
    tmp_dir = os.path.join(DIST, ".linux_tmp")
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)

    files = collect_files(ROOT)
    for rel in files:
        src = os.path.join(ROOT, rel)
        dst = os.path.join(tmp_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

    # 设置 install.sh 和 run.sh 为可执行
    for script in ["deploy/linux/install.sh", "deploy/linux/run.sh"]:
        spath = os.path.join(tmp_dir, script)
        if os.path.exists(spath):
            os.chmod(spath, 0o755)

    # 打包
    tar_path = os.path.join(DIST, "vm-panel-linux.tar.gz")
    with tarfile.open(tar_path, "w:gz") as tar:
        for rel in files:
            full = os.path.join(tmp_dir, rel)
            tar.add(full, arcname=rel)
            print(f"  + {rel}")

    # 清理
    shutil.rmtree(tmp_dir)

    size_mb = os.path.getsize(tar_path) / 1024 / 1024
    print(f"\n  ✅ Linux tar.gz: {tar_path} ({size_mb:.1f} MB, {len(files)} files)")
    return tar_path


def build_version_file():
    """生成版本信息"""
    from datetime import datetime
    ver = {
        "version": "1.0.0",
        "build_date": datetime.now().isoformat(),
        "platforms": ["windows", "linux"],
    }
    import json
    with open(os.path.join(DIST, "version.json"), "w") as f:
        json.dump(ver, f, indent=2)
    print(f"\n  ✅ version.json")


if __name__ == "__main__":
    print()
    print("╔════════════════════════════════════════╗")
    print("║     VM Panel — 构建分发包              ║")
    print("╚════════════════════════════════════════╝")
    print()

    build_windows_zip()
    build_linux_tar()
    build_version_file()

    print()
    print("=" * 50)
    print("  ✅ 全部构建完成!")
    print(f"  📦 Windows: dist/VM-Panel-Windows.zip")
    print(f"  📦 Linux:   dist/vm-panel-linux.tar.gz")
    print("=" * 50)
    print()
