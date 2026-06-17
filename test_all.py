"""
VM Panel 全面测试脚本
测试所有 API 端点 + 边界条件
"""
import sys, os, json, urllib.request, urllib.error

BASE = "http://localhost:8080"
PASS = 0
FAIL = 0

def test(name, method, path, expected_status=200, send_data=None, checks=None):
    global PASS, FAIL
    url = f"{BASE}{path}"
    data = json.dumps(send_data).encode() if send_data else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req)
        raw = resp.read().decode()
        status = resp.status
        # HTML 页面不需要 JSON 解析
        if raw.strip().startswith("<"):
            result = "✅" if status == expected_status else "❌"
            print(f"  {result} {method:6s} {path:40s} → {status} [HTML]")
            PASS += 1 if "✅" in result else 0
            FAIL += 1 if "❌" in result else 0
            return {"ok": status < 400, "data": {}}
        body = json.loads(raw)
        ok = body.get("ok", False)
        result = "✅" if (status == expected_status and ok) else "❌"
        # 额外检查
        extra = ""
        if checks:
            for key, expected in checks.items():
                actual = body.get("data", body).get(key) if "." not in key else _nested_get(body, key)
                if actual != expected:
                    result = "❌"
                    extra += f" [{key}期望={expected}实际={actual}]"
        print(f"  {result} {method:6s} {path:40s} → {status} {extra}")
        PASS += 1 if "✅" in result else 0
        FAIL += 1 if "❌" in result else 0
        return body
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode()) if e.code != 404 else {"error": "not found"}
        result = "✅" if e.code == expected_status else "❌"
        print(f"  {result} {method:6s} {path:40s} → {e.code} [{body.get('error','')}]")
        PASS += 1 if "✅" in result else 0
        FAIL += 1 if "❌" in result else 0
        return body
    except Exception as e:
        print(f"  ❌ {method:6s} {path:40s} → ERROR: {e}")
        FAIL += 1
        return None

def _nested_get(body, key):
    parts = key.split(".")
    v = body
    for p in parts:
        v = v.get(p, {}) if isinstance(v, dict) else v[p] if isinstance(v, (list, tuple)) and p.isdigit() else None
    return v


# ═══════════════════════════════════════════
#  1. 页面路由
# ═══════════════════════════════════════════
print("\n═══ 1. 页面路由 ═══")
test("仪表盘", "GET", "/", 200)
test("VM列表页", "GET", "/vms", 200)
test("创建VM页", "GET", "/vms/create", 200)
test("网络页", "GET", "/networks", 200)
test("创建网络页", "GET", "/networks/create", 200)
test("存储页", "GET", "/storage", 200)
test("ISO页", "GET", "/isos", 200)
test("设置页", "GET", "/settings", 200)

# ═══════════════════════════════════════════
#  2. 系统信息
# ═══════════════════════════════════════════
print("\n═══ 2. 系统 API ═══")
host = test("宿主机信息", "GET", "/api/host/info", 200,
    checks={"hostname": "vm-host-simulated"})
test("宿主机统计", "GET", "/api/host/stats", 200)
test("模板列表", "GET", "/api/templates", 200)

# ═══════════════════════════════════════════
#  3. 虚拟机 CRUD
# ═══════════════════════════════════════════
print("\n═══ 3. 虚拟机 ═══")
test("VM列表", "GET", "/api/vms", 200)

# 创建(缺少字段)
test("创建VM(缺字段)", "POST", "/api/vms", 400,
    send_data={"name": "test-only"},
    checks={"error": "缺少必填字段: vcpu"})

# 创建(正常)
test("创建VM", "POST", "/api/vms", 201,
    send_data={"name": "test-vm-2", "vcpu": 2, "memory_mb": 2048, "disk_gb": 20,
               "network": "default", "iso_path": ""})

# 重名
test("创建VM(重名)", "POST", "/api/vms", 400,
    send_data={"name": "test-vm-2", "vcpu": 2, "memory_mb": 1024, "disk_gb": 10},
    checks={"error": "虚拟机 'test-vm-2' 已存在"})

# VM详情
test("VM详情", "GET", "/api/vms/test-vm-2", 200,
    checks={"name": "test-vm-2", "state": "shutoff"})

# 不存在的VM详情
test("VM详情(不存在)", "GET", "/api/vms/nonexist", 404)

# ═══════════════════════════════════════════
#  4. VM 状态操作
# ═══════════════════════════════════════════
print("\n═══ 4. VM 操作 ═══")
test("启动VM", "POST", "/api/vms/test-vm-2/start", 200)
test("确认运行", "GET", "/api/vms/test-vm-2", 200, checks={"state": "running"})
test("重启VM", "POST", "/api/vms/test-vm-2/restart", 200)
test("关机VM", "POST", "/api/vms/test-vm-2/shutdown", 200)
test("确认关机", "GET", "/api/vms/test-vm-2", 200, checks={"state": "shutoff"})
test("强制停止", "POST", "/api/vms/test-vm-2/force-stop", 200)

# 操作不存在的VM
test("操作不存在VM", "POST", "/api/vms/no-vm/start", 400)

# VNC端口
test("VNC端口", "GET", "/api/vms/test-vm-2/vnc-port", 200,
    checks={"port": 5900})

# ═══════════════════════════════════════════
#  5. 快照管理
# ═══════════════════════════════════════════
print("\n═══ 5. 快照 ═══")
test("快照列表(空)", "GET", "/api/vms/test-vm-2/snapshots", 200)
test("创建快照", "POST", "/api/vms/test-vm-2/snapshots", 201,
    send_data={"name": "snap-before-update", "description": "更新前快照"})
test("快照列表(有)", "GET", "/api/vms/test-vm-2/snapshots", 200)
test("回滚快照", "POST", "/api/vms/test-vm-2/snapshots/snap-before-update/revert", 200)
test("删除快照", "DELETE", "/api/vms/test-vm-2/snapshots/snap-before-update", 200)

# ═══════════════════════════════════════════
#  6. 删除VM
# ═══════════════════════════════════════════
print("\n═══ 6. 删除VM ═══")
test("删除VM", "DELETE", "/api/vms/test-vm-2", 200)
test("确认删除", "GET", "/api/vms/test-vm-2", 404)
test("删除不存在VM", "DELETE", "/api/vms/test-vm-2", 400)
# 创建一个VM然后删除它(含磁盘)
test("创建临时VM", "POST", "/api/vms", 201,
    send_data={"name": "temp-for-delete", "vcpu": 1, "memory_mb": 512, "disk_gb": 5})
test("删除VM(删磁盘)", "DELETE", "/api/vms/temp-for-delete?delete_disk=true", 200)

# ═══════════════════════════════════════════
#  7. 网络管理
# ═══════════════════════════════════════════
print("\n═══ 7. 网络 ═══")
nets = test("网络列表", "GET", "/api/networks", 200)
# 验证UUID一致性
uuid1 = nets.get("data", [{}])[0].get("uuid", "")
test("创建网络", "POST", "/api/networks", 201,
    send_data={"name": "test-net", "type": "nat", "subnet": "10.10.10.0/24",
               "dhcp_start": "10.10.10.10", "dhcp_end": "10.10.10.200"})
test("删除网络", "DELETE", "/api/networks/test-net", 200)
test("删除不存在网络", "DELETE", "/api/networks/no-net", 400)
test("激活网络", "POST", "/api/networks/default/activate", 200)
test("停用网络", "POST", "/api/networks/default/deactivate", 200)

# 系统网桥
test("网桥列表", "GET", "/api/bridges", 200)

# 再查询一次网络确认 UUID 不变
nets2 = test("网络列表(再次)", "GET", "/api/networks", 200)
uuid2 = nets2.get("data", [{}])[0].get("uuid", "") if nets2 else ""
if uuid1 == uuid2 and uuid1:
    print(f"  ✅ UUID一致性检查: {uuid1} == {uuid2}")
    PASS += 1
else:
    print(f"  ❌ UUID一致性检查: {uuid1} != {uuid2}")
    FAIL += 1

# ═══════════════════════════════════════════
#  8. 存储管理
# ═══════════════════════════════════════════
print("\n═══ 8. 存储 ═══")
test("存储池列表", "GET", "/api/pools", 200)
test("创建存储池", "POST", "/api/pools", 201,
    send_data={"name": "test-pool", "type": "dir", "path": ""})

# 卷管理
test("卷列表(空)", "GET", "/api/pools/test-pool/volumes", 200)
test("创建卷", "POST", "/api/pools/test-pool/volumes", 201,
    send_data={"name": "test-vol.qcow2", "size_gb": 10, "format": "qcow2"})
test("确认卷存在", "GET", "/api/pools/test-pool/volumes", 200)

# 检查卷文件大小(不应占用 10GB)
meta_path = os.path.join("vm-panel", "storage", "images", "test-vol.qcow2.meta")
if os.path.exists(meta_path):
    meta_size = os.path.getsize(meta_path)
    if meta_size < 1024:  # 小于1KB而不是10GB
        print(f"  ✅ 卷元数据大小正常: {meta_size} bytes (而非 10GB)")
        PASS += 1
    else:
        print(f"  ❌ 卷元数据异常: {meta_size} bytes")
        FAIL += 1
else:
    print(f"  ❌ 卷元数据文件缺失: {meta_path}")
    FAIL += 1

test("扩容卷", "POST", "/api/pools/test-pool/volumes/test-vol.qcow2/resize", 200,
    send_data={"size_gb": 50})
test("删除卷", "DELETE", "/api/pools/test-pool/volumes/test-vol.qcow2", 200)
test("删除不存在卷", "DELETE", "/api/pools/test-pool/volumes/no-vol", 400)

# 清理测试池
test("删除存储池", "DELETE", "/api/pools/test-pool", 200)

# ═══════════════════════════════════════════
#  9. ISO 管理
# ═══════════════════════════════════════════
print("\n═══ 9. ISO ═══")
test("ISO列表(空)", "GET", "/api/isos", 200)
test("删除不存在ISO", "DELETE", "/api/isos/no.iso", 400)

# ═══════════════════════════════════════════
#  10. 边界条件
# ═══════════════════════════════════════════
print("\n═══ 10. 边界条件 ═══")
# Content-Type 检查
req = urllib.request.Request(f"{BASE}/api/vms", 
    data='{"name":"bad"}'.encode(), method="POST")
req.add_header("Content-Type", "text/plain")
try:
    resp = urllib.request.urlopen(req)
    print(f"  ❌ POST /api/vms (text/plain) 不应成功")
    FAIL += 1
except urllib.error.HTTPError as e:
    body = json.loads(e.read().decode())
    if e.code == 400 and "application/json" in body.get("error", ""):
        print(f"  ✅ POST /api/vms (text/plain) → 400 [正确拒绝]")
        PASS += 1
    else:
        print(f"  ❌ POST /api/vms (text/plain) → 意外的 {e.code}")
        FAIL += 1

# 静态文件路径穿越 (Flask 会将路径归一化, ../config.py → config.py 即不存在)
test("穿越测试(相对路径)", "GET", "/static/../config.py", 404)

# 真实路径穿越测试: 尝试用编码绕过
import http.client
conn = http.client.HTTPConnection("localhost", 8080)
conn.request("GET", "/static/..%5cconfig.py")
resp = conn.getresponse()
resp.read()
if resp.status == 403 or resp.status == 404:
    print(f"  ✅ 编码路径穿越被阻止 → {resp.status}")
    PASS += 1
else:
    print(f"  ❌ 编码路径穿越: 意外状态 {resp.status}")
    FAIL += 1
conn.close()

# ═══════════════════════════════════════════
#  结果
# ═══════════════════════════════════════════
print(f"\n{'═'*50}")
print(f"  📊 测试结果: ✅ {PASS} 通过 / ❌ {FAIL} 失败 / 共 {PASS+FAIL} 项")
print(f"{'═'*50}")
sys.exit(0 if FAIL == 0 else 1)
