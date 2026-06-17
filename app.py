"""
VM Management Panel - Flask Application

类 PVE / VMware 的虚拟机管理面板 Web 应用。
支持 Linux (KVM/libvirt) / Windows (模拟) 双平台。
"""
import os
import json
import sys
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, send_from_directory, session,
)

# 配置加载: 优先从 deploy/run.py 注入的 config 模块
try:
    from config import Config
except ImportError:
    # 备用: 使用 deploy/linux/config_linux.py
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "deploy", "linux"))
    from config_linux import Config
from libvirt_manager import LibvirtManager
from network_manager import NetworkManager
from storage_manager import StorageManager
from i18n import _, get_i18n
from event_log import log_event, get_event_log
from plugins import PluginManager, PluginBase
from task_queue import get_queue

# ── App Setup ──────────────────────────────────────────────

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# 核心管理器单例
libvirt_mgr = LibvirtManager()
network_mgr = NetworkManager()
storage_mgr = StorageManager()

# ── 插件系统 ──────────────────────────────────────────────

plugin_mgr = PluginManager()
loaded_plugins = plugin_mgr.load_all()
if loaded_plugins:
    print(f"  * 已加载 {len(loaded_plugins)} 个插件: {', '.join(p.name for p in loaded_plugins)}")


# ── 模板全局变量 ─────────────────────────────────────────

@app.context_processor
def inject_globals():
    """向所有模板注入 _() 翻译函数和当前语言"""
    i18n = get_i18n()
    lang = i18n._detect_lang()
    return {
        "_": _,
        "current_lang": lang,
        "simulate_mode": Config.SIMULATE_LIBVIRT,
    }


# ── 辅助函数 ───────────────────────────────────────────────

def api_response(data, status=200):
    """统一 API 响应格式"""
    return jsonify({"ok": status < 400, "data": data}), status


def error_response(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def require_json(f):
    """装饰器：要求请求体为 JSON"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.content_type and "application/json" in request.content_type:
            return f(*args, **kwargs)
        return error_response("需要 application/json 请求体")
    return wrapper


# ── 页面路由 ───────────────────────────────────────────────

@app.route("/")
def dashboard():
    """仪表盘主页"""
    return render_template("dashboard.html")


@app.route("/vms")
def vms_page():
    """虚拟机列表页"""
    return render_template("vms.html")


@app.route("/vms/create")
def vm_create_page():
    """创建虚拟机页"""
    networks = network_mgr.list_networks()
    isos = storage_mgr.list_isos()
    return render_template("vm_create.html",
                         templates=Config.VM_TEMPLATES,
                         networks=networks,
                         isos=isos)


@app.route("/vms/<name>")
def vm_detail_page(name):
    """虚拟机详情页"""
    vm = libvirt_mgr.get_vm(name)
    if vm is None:
        return render_template("vms.html", error=f"VM '{name}' 不存在"), 404
    return render_template("vm_detail.html", vm=vm)


@app.route("/networks")
def networks_page():
    """网络管理页"""
    return render_template("networks.html")


@app.route("/networks/create")
def network_create_page():
    """创建网络页"""
    return render_template("network_create.html")


@app.route("/storage")
def storage_page():
    """存储管理页"""
    return render_template("storage.html")


@app.route("/isos")
def isos_page():
    """ISO 镜像管理页"""
    return render_template("isos.html")


@app.route("/settings")
def settings_page():
    """系统设置页"""
    return render_template("settings.html")


# ══════════════════════════════════════════════════════════
#  RESTful API
# ══════════════════════════════════════════════════════════

# ── 系统信息 ──────────────────────────────────────────────

@app.route("/api/host/info")
def api_host_info():
    """宿主机信息"""
    return api_response(libvirt_mgr.get_host_info())


@app.route("/api/host/stats")
def api_host_stats():
    """宿主机实时性能"""
    return api_response(libvirt_mgr.get_host_stats())


# ── 虚拟机 CRUD ────────────────────────────────────────────

@app.route("/api/vms")
def api_list_vms():
    """获取所有 VM 列表"""
    vms = libvirt_mgr.list_vms()
    return api_response(vms)


@app.route("/api/vms/<name>")
def api_get_vm(name):
    """获取单个 VM 详情"""
    vm = libvirt_mgr.get_vm(name)
    if vm is None:
        return error_response(f"VM '{name}' 不存在", 404)
    return api_response(vm)


@app.route("/api/vms", methods=["POST"])
@require_json
def api_create_vm():
    """创建虚拟机"""
    data = request.get_json()

    required = ["name", "vcpu", "memory_mb", "disk_gb"]
    for field in required:
        if field not in data:
            return error_response(f"缺少必填字段: {field}")

    # 检查重名
    existing = libvirt_mgr.get_vm(data["name"])
    if existing:
        log_event("create", data["name"], "名称已存在", "fail")
        return error_response(f"虚拟机 '{data['name']}' 已存在")

    result = libvirt_mgr.create_vm(data)
    if result.get("success"):
        log_event("create", data["name"], f"vCPU={data.get('vcpu')} RAM={data.get('memory_mb')}MB Disk={data.get('disk_gb')}GB")
        return api_response(result, 201)
    log_event("create", data["name"], result.get("error", ""), "fail")
    return error_response(result.get("error", "创建失败"))


@app.route("/api/vms/<name>/start", methods=["POST"])
def api_start_vm(name):
    """启动 VM"""
    result = libvirt_mgr.start_vm(name)
    if result.get("success"):
        log_event("start", name)
        return api_response({"status": "started"})
    log_event("start", name, result.get("error", ""), "fail")
    return error_response(result.get("error", "启动失败"))


@app.route("/api/vms/<name>/shutdown", methods=["POST"])
def api_shutdown_vm(name):
    """正常关机"""
    result = libvirt_mgr.shutdown_vm(name)
    if result.get("success"):
        log_event("shutdown", name)
        return api_response({"status": "shutdown"})
    log_event("shutdown", name, result.get("error", ""), "fail")
    return error_response(result.get("error", "关机失败"))


@app.route("/api/vms/<name>/force-stop", methods=["POST"])
def api_force_stop_vm(name):
    """强制断电"""
    result = libvirt_mgr.force_stop_vm(name)
    if result.get("success"):
        log_event("force-stop", name)
        return api_response({"status": "stopped"})
    log_event("force-stop", name, result.get("error", ""), "fail")
    return error_response(result.get("error", "强制停止失败"))


@app.route("/api/vms/<name>/restart", methods=["POST"])
def api_restart_vm(name):
    """重启 VM"""
    result = libvirt_mgr.restart_vm(name)
    if result.get("success"):
        log_event("restart", name)
        return api_response({"status": "restarted"})
    log_event("restart", name, result.get("error", ""), "fail")
    return error_response(result.get("error", "重启失败"))


@app.route("/api/vms/<name>", methods=["DELETE"])
def api_delete_vm(name):
    """删除 VM"""
    delete_disk = request.args.get("delete_disk", "false").lower() == "true"
    result = libvirt_mgr.delete_vm(name, delete_disk=delete_disk)
    if result.get("success"):
        log_event("delete", name, f"delete_disk={delete_disk}")
        return api_response({"status": "deleted"})
    log_event("delete", name, result.get("error", ""), "fail")
    return error_response(result.get("error", "删除失败"))


@app.route("/api/vms/<name>/vnc-port")
def api_vnc_port(name):
    """获取 VM VNC 端口"""
    port = libvirt_mgr.get_vnc_port(name)
    return api_response({"port": port, "host": request.host.split(":")[0]})


# ── 快照管理 ──────────────────────────────────────────────

@app.route("/api/vms/<name>/snapshots")
def api_list_snapshots(name):
    """列出 VM 快照"""
    snapshots = libvirt_mgr.list_snapshots(name)
    return api_response(snapshots)


@app.route("/api/vms/<name>/snapshots", methods=["POST"])
@require_json
def api_create_snapshot(name):
    """创建快照"""
    data = request.get_json()
    snap_name = data.get("name", f"snap-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    description = data.get("description", "")
    result = libvirt_mgr.create_snapshot(name, snap_name, description)
    if result.get("success"):
        return api_response(result, 201)
    return error_response(result.get("error", "创建快照失败"))


@app.route("/api/vms/<name>/snapshots/<snap_name>/revert", methods=["POST"])
def api_revert_snapshot(name, snap_name):
    """回滚快照"""
    result = libvirt_mgr.revert_snapshot(name, snap_name)
    if result.get("success"):
        return api_response({"status": "reverted"})
    return error_response(result.get("error", "回滚快照失败"))


@app.route("/api/vms/<name>/snapshots/<snap_name>", methods=["DELETE"])
def api_delete_snapshot(name, snap_name):
    """删除快照"""
    result = libvirt_mgr.delete_snapshot(name, snap_name)
    if result.get("success"):
        return api_response({"status": "deleted"})
    return error_response(result.get("error", "删除快照失败"))


# ── 网络管理 ──────────────────────────────────────────────

@app.route("/api/networks")
def api_list_networks():
    """列出所有虚拟网络"""
    return api_response(network_mgr.list_networks())


@app.route("/api/networks", methods=["POST"])
@require_json
def api_create_network():
    """创建虚拟网络"""
    data = request.get_json()
    if "name" not in data:
        return error_response("缺少 name 字段")
    result = network_mgr.create_network(data)
    if result.get("success"):
        log_event("net-create", data["name"], f"type={data.get('type')} subnet={data.get('subnet')}")
        return api_response(result, 201)
    log_event("net-create", data.get("name","?"), result.get("error",""), "fail")
    return error_response(result.get("error", "创建网络失败"))


@app.route("/api/networks/<name>", methods=["DELETE"])
def api_delete_network(name):
    """删除虚拟网络"""
    result = network_mgr.delete_network(name)
    if result.get("success"):
        log_event("net-delete", name)
        return api_response({"status": "deleted"})
    log_event("net-delete", name, result.get("error", ""), "fail")
    return error_response(result.get("error", "删除网络失败"))


@app.route("/api/networks/<name>/activate", methods=["POST"])
def api_activate_network(name):
    """激活网络"""
    result = network_mgr.activate_network(name)
    if result.get("success"):
        return api_response({"status": "activated"})
    return error_response(result.get("error", "激活网络失败"))


@app.route("/api/networks/<name>/deactivate", methods=["POST"])
def api_deactivate_network(name):
    """停用网络"""
    result = network_mgr.deactivate_network(name)
    if result.get("success"):
        return api_response({"status": "deactivated"})
    return error_response(result.get("error", "停用网络失败"))


@app.route("/api/bridges")
def api_list_bridges():
    """列出系统级网桥"""
    return api_response(network_mgr.list_bridges())


@app.route("/api/bridges", methods=["POST"])
@require_json
def api_create_bridge():
    """创建系统级网桥"""
    data = request.get_json()
    bridge_name = data.get("name", "br0")
    interface = data.get("interface", "")
    result = network_mgr.create_bridge(bridge_name, interface or None)
    if result.get("success"):
        return api_response(result, 201)
    return error_response(result.get("error", "创建网桥失败"))


# ── 存储管理 ──────────────────────────────────────────────

@app.route("/api/pools")
def api_list_pools():
    """列出存储池"""
    return api_response(storage_mgr.list_pools())


@app.route("/api/pools", methods=["POST"])
@require_json
def api_create_pool():
    """创建存储池"""
    data = request.get_json()
    name = data.get("name", "")
    if not name:
        return error_response("缺少 name 字段")
    pool_type = data.get("type", "dir")
    path = data.get("path")
    result = storage_mgr.create_pool(name, pool_type, path)
    if result.get("success"):
        return api_response(result, 201)
    return error_response(result.get("error", "创建存储池失败"))


@app.route("/api/pools/<name>", methods=["DELETE"])
def api_delete_pool(name):
    """删除存储池"""
    result = storage_mgr.delete_pool(name)
    if result.get("success"):
        return api_response({"status": "deleted"})
    return error_response(result.get("error", "删除存储池失败"))


@app.route("/api/pools/<pool_name>/volumes")
def api_list_volumes(pool_name):
    """列出存储卷"""
    return api_response(storage_mgr.list_volumes(pool_name))


@app.route("/api/pools/<pool_name>/volumes", methods=["POST"])
@require_json
def api_create_volume(pool_name):
    """创建存储卷"""
    data = request.get_json()
    name = data.get("name", "")
    size_gb = data.get("size_gb", 10)
    fmt = data.get("format", "qcow2")
    if not name:
        return error_response("缺少 name 字段")
    result = storage_mgr.create_volume(pool_name, name, size_gb, fmt)
    if result.get("success"):
        return api_response(result, 201)
    return error_response(result.get("error", "创建卷失败"))


@app.route("/api/pools/<pool_name>/volumes/<vol_name>", methods=["DELETE"])
def api_delete_volume(pool_name, vol_name):
    """删除存储卷"""
    result = storage_mgr.delete_volume(pool_name, vol_name)
    if result.get("success"):
        return api_response({"status": "deleted"})
    return error_response(result.get("error", "删除卷失败"))


@app.route("/api/pools/<pool_name>/volumes/<vol_name>/resize", methods=["POST"])
@require_json
def api_resize_volume(pool_name, vol_name):
    """扩容卷"""
    data = request.get_json()
    new_size = data.get("size_gb", 0)
    if new_size <= 0:
        return error_response("size_gb 必须 > 0")
    result = storage_mgr.resize_volume(pool_name, vol_name, new_size)
    if result.get("success"):
        return api_response({"status": "resized"})
    return error_response(result.get("error", "扩容失败"))


# ── ISO 镜像管理 ──────────────────────────────────────────

@app.route("/api/isos")
def api_list_isos():
    """列出 ISO 镜像"""
    return api_response(storage_mgr.list_isos())


@app.route("/api/isos/upload", methods=["POST"])
def api_upload_iso():
    """上传 ISO 镜像"""
    if "file" not in request.files:
        return error_response("未选择文件")

    file = request.files["file"]
    if file.filename == "":
        return error_response("文件名为空")

    if not file.filename.lower().endswith(".iso"):
        return error_response("仅支持 ISO 文件")

    result = storage_mgr.upload_iso(file.filename, file)
    if result.get("success"):
        return api_response(result, 201)
    return error_response(result.get("error", "上传失败"))


@app.route("/api/isos/<name>", methods=["DELETE"])
def api_delete_iso(name):
    """删除 ISO"""
    result = storage_mgr.delete_iso(name)
    if result.get("success"):
        return api_response({"status": "deleted"})
    return error_response(result.get("error", "删除失败"))


# ── 语言切换 ──────────────────────────────────────────────

@app.route("/api/lang", methods=["POST"])
@require_json
def api_set_lang():
    """切换语言"""
    data = request.get_json()
    lang = data.get("lang", "zh")
    if lang not in ("zh", "en"):
        return error_response("不支持的语言")

    session["lang"] = lang
    resp = api_response({"lang": lang, "msg": _("msg.operate_success")})
    resp[0].set_cookie("lang", lang, max_age=365*24*3600)
    return resp


# ── 健康检查 & 版本 ───────────────────────────────────────

@app.route("/api/health")
def api_health():
    """健康检查端点"""
    host_info = libvirt_mgr.get_host_info()
    is_ok = "error" not in host_info
    return api_response({
        "status": "ok" if is_ok else "degraded",
        "simulated": Config.SIMULATE_LIBVIRT,
        "plugins": len(plugin_mgr._plugins),
        "timestamp": datetime.now().isoformat(),
    }, 200 if is_ok else 503)


@app.route("/api/version")
def api_version():
    """API 版本信息"""
    return api_response({
        "version": "1.0.0",
        "api_version": "v1",
        "backend": "Flask + Python",
        "hypervisor": "KVM/QEMU + libvirt",
        "features": {
            "vms": True,
            "networks": True,
            "storage": True,
            "snapshots": True,
            "cloning": True,
            "plugins": True,
            "i18n": True,
        },
    })


# ── 宿主机磁盘 ────────────────────────────────────────────

@app.route("/api/host/disks")
def api_host_disks():
    """列出宿主机磁盘/存储设备"""
    if Config.SIMULATE_LIBVIRT:
        return api_response([
            {"device": "sda", "type": "disk", "size_gb": 500,
             "model": "SSD (Simulated)", "mount": "/", "used_gb": 120},
            {"device": "sdb", "type": "disk", "size_gb": 2000,
             "model": "HDD (Simulated)", "mount": "/data", "used_gb": 800},
            {"device": "nvme0n1", "type": "nvme", "size_gb": 256,
             "model": "NVMe (Simulated)", "mount": "/var/lib/libvirt", "used_gb": 180},
        ])
    try:
        import psutil
        disks = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "device": part.device,
                    "mount": part.mountpoint,
                    "fstype": part.fstype,
                    "total_gb": round(usage.total / (1024**3), 1),
                    "used_gb": round(usage.used / (1024**3), 1),
                    "free_gb": round(usage.free / (1024**3), 1),
                    "percent": usage.percent,
                })
            except Exception:
                pass
        return api_response(disks)
    except ImportError:
        return api_response([])


# ── VM XML 查看 ──────────────────────────────────────────

@app.route("/api/vms/<name>/xml")
def api_vm_xml(name):
    """获取 VM 的 libvirt XML 描述"""
    if Config.SIMULATE_LIBVIRT:
        vm = libvirt_mgr.get_vm(name)
        if vm is None:
            return error_response(f"VM '{name}' 不存在", 404)
        # 模拟 XML
        xml = f"""<!-- Simulated libvirt domain XML for {name} -->
<domain type='kvm'>
  <name>{name}</name>
  <uuid>{vm.get('uuid', 'unknown')}</uuid>
  <memory unit='KiB'>{vm.get('memory_mb', 1024) * 1024}</memory>
  <vcpu>{vm.get('vcpu', 2)}</vcpu>
  <os>
    <type arch='x86_64' machine='pc-q35-9.0'>hvm</type>
  </os>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='{vm.get('disks', [{}])[0].get('file', '/var/lib/libvirt/images/{name}.qcow2')}'/>
    </disk>
  </devices>
</domain>"""
        return api_response({"name": name, "xml": xml, "simulated": True})

    try:
        import libvirt
        conn = libvirt.open(Config.LIBVIRT_URI)
        dom = conn.lookupByName(name)
        xml = dom.XMLDesc(0)
        conn.close()
        return api_response({"name": name, "xml": xml, "simulated": False})
    except Exception as e:
        return error_response(str(e))


# ── 批量 VM 操作 ─────────────────────────────────────────

@app.route("/api/vms/batch/<action>", methods=["POST"])
@require_json
def api_batch_vm_action(action):
    """批量 VM 操作: start / stop / force-stop / restart"""
    data = request.get_json()
    names = data.get("names", [])
    if not names:
        return error_response("请提供 names 列表")

    if action not in ("start", "shutdown", "force-stop", "restart"):
        return error_response(f"不支持的操作: {action}")

    results = []
    for name in names:
        if action == "start":
            r = libvirt_mgr.start_vm(name)
        elif action == "shutdown":
            r = libvirt_mgr.shutdown_vm(name)
        elif action == "force-stop":
            r = libvirt_mgr.force_stop_vm(name)
        elif action == "restart":
            r = libvirt_mgr.restart_vm(name)
        results.append({
            "name": name,
            "success": r.get("success", False),
            "error": r.get("error"),
        })
        if r.get("success"):
            log_event(f"batch-{action}", name)

    success_count = sum(1 for r in results if r["success"])
    return api_response({
        "action": action,
        "total": len(names),
        "success": success_count,
        "failed": len(names) - success_count,
        "results": results,
    })


# ── 事件日志 ──────────────────────────────────────────────

@app.route("/api/events", methods=["GET"])
def api_list_events():
    """获取操作日志"""
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    action = request.args.get("action", None)
    events, total = get_event_log().list(limit=limit, offset=offset, action_filter=action)
    return api_response({"events": events, "total": total})


@app.route("/api/events/stats")
def api_event_stats():
    """日志统计"""
    return api_response(get_event_log().stats())


@app.route("/api/events", methods=["DELETE"])
def api_clear_events():
    """清空日志"""
    get_event_log().clear()
    log_event("clear", "events", "日志已清空")
    return api_response({"status": "cleared"})


@app.route("/events")
def events_page():
    """操作日志页"""
    return render_template("events.html")


# ── VM 克隆 ──────────────────────────────────────────────

@app.route("/api/vms/<name>/clone", methods=["POST"])
@require_json
def api_clone_vm(name):
    """克隆虚拟机"""
    data = request.get_json()
    new_name = data.get("new_name", f"{name}-clone")
    vm = libvirt_mgr.get_vm(name)
    if vm is None:
        log_event("clone", name, "源 VM 不存在", "fail")
        return error_response(f"VM '{name}' 不存在", 404)

    spec = {
        "name": new_name,
        "vcpu": vm.get("vcpu", 2),
        "memory_mb": vm.get("memory_mb", 2048),
        "disk_gb": 20,  # 默认
        "network": "default",
    }
    result = libvirt_mgr.create_vm(spec)
    if result.get("success"):
        log_event("clone", f"{name} → {new_name}",
                  f"vCPU={spec['vcpu']} RAM={spec['memory_mb']}MB")
        return api_response(result, 201)
    log_event("clone", new_name, result.get("error", ""), "fail")
    return error_response(result.get("error", "克隆失败"))


# ── 插件管理 API ─────────────────────────────────────────

@app.route("/api/plugins")
def api_list_plugins():
    """列出所有插件及状态"""
    return api_response(plugin_mgr.list_plugins())


@app.route("/api/plugins/<name>/toggle", methods=["POST"])
@require_json
def api_toggle_plugin(name):
    """启停插件"""
    plugin = plugin_mgr.get_plugin(name)
    if plugin is None:
        return error_response(f"插件 '{name}' 不存在")
    data = request.get_json()
    enabled = data.get("enabled", True)
    plugin_mgr.set_enabled(name, enabled)
    log_event("plugin-toggle", name, f"enabled={enabled}")
    return api_response({"name": name, "enabled": enabled})


# ── 插件页面路由 ──────────────────────────────────────────

@app.route("/plugins")
def plugins_page():
    """插件管理页"""
    return render_template("plugins.html")


@app.route("/plugins/docker")
def docker_page():
    """Docker 管理页 (示例插件)"""
    return render_template("plugin_docker.html")


# ── 模板配置 ──────────────────────────────────────────────

@app.route("/api/templates")
def api_templates():
    """获取 VM 模板配置"""
    return api_response(Config.VM_TEMPLATES)


# ── 组件工具 ──────────────────────────────────────────────

@app.route("/api/disk-info", methods=["POST"])
@require_json
def api_disk_info():
    """查询 qemu-img 磁盘信息"""
    path = request.get_json().get("path", "")
    if not path or not os.path.exists(path):
        return error_response("文件不存在")
    return api_response(storage_mgr.get_disk_info(path))


# ══════════════════════════════════════════════════════════
#  static file serving
# ══════════════════════════════════════════════════════════

@app.route("/static/<path:filename>")
def static_files(filename):
    # 防止路径穿越
    if ".." in filename or filename.startswith("/"):
        return error_response("Forbidden", 403)
    if not os.path.exists(os.path.join(app.static_folder, filename)):
        return error_response("File not found", 404)
    return send_from_directory("static", filename)


# ══════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════

# ── 异步任务 API ──────────────────────────────────────────

@app.route("/api/tasks")
def api_list_tasks():
    """任务列表"""
    limit = request.args.get("limit", 50, type=int)
    return api_response(get_queue().list_tasks(limit=limit))


@app.route("/api/tasks/<task_id>")
def api_get_task(task_id):
    """单个任务详情"""
    task = get_queue().get_task(task_id)
    if task is None:
        return error_response("任务不存在", 404)
    return api_response(task)


@app.route("/api/tasks/<task_id>/cancel", methods=["POST"])
def api_cancel_task(task_id):
    """取消任务"""
    if get_queue().cancel_task(task_id):
        log_event("task-cancel", task_id)
        return api_response({"status": "cancelled"})
    return error_response("无法取消任务")


@app.route("/api/tasks/clear", methods=["POST"])
def api_clear_tasks():
    """清理已完成的任务"""
    get_queue().clear_finished()
    return api_response({"status": "cleared"})


@app.route("/tasks")
def tasks_page():
    """任务队列页面"""
    return render_template("tasks.html")


# ── VNC 控制台 ────────────────────────────────────────────

@app.route("/vnc/<name>")
def vnc_console_page(name):
    """VNC Web 控制台页面"""
    vm = libvirt_mgr.get_vm(name)
    if vm is None:
        return error_response(f"VM '{name}' 不存在", 404)
    return send_from_directory("static/novnc", "console.html")


# 注册插件路由 (必须在所有路由之后)
plugin_mgr.register_routes(app)


if __name__ == "__main__":
    print("╔═══════════════════════════════════════════════╗")
    print("║       VM Management Panel v1.0               ║")
    print("║    类 PVE / VMware 的虚拟机管理面板            ║")
    print("╚═══════════════════════════════════════════════╝")
    print(f"  * 模拟模式: {'开启 (演示用)' if Config.SIMULATE_LIBVIRT else '关闭 (真实 libvirt)'}")
    print(f"  * 访问地址: http://{Config.HOST}:{Config.PORT}")
    print(f"  * 存储目录: {Config.STORAGE_DIR}")
    if plugin_mgr._plugins:
        print(f"  * 已加载 {len(plugin_mgr._plugins)} 个插件: {', '.join(plugin_mgr._plugins.keys())}")
    print()

    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
    )
