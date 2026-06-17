"""
VM Management Panel - 示例插件: Docker 容器管理

演示第三方插件如何注册 API 路由和导航菜单。
"""
from plugins import PluginBase


class Plugin(PluginBase):
    name = "docker-monitor"
    version = "1.0.0"
    description = "Docker container monitoring — list & inspect containers"
    author = "VM Panel Team"
    homepage = ""

    def register_routes(self, app):
        """注册 /api/plugins/docker/* 路由"""

        @app.route("/api/plugins/docker/ps", methods=["GET"])
        def docker_ps():
            """列出 Docker 容器 (模拟/真实)"""
            try:
                import docker as docker_lib
                client = docker_lib.from_env()
                containers = client.containers.list(all=True)
                result = []
                for c in containers:
                    result.append({
                        "id": c.short_id,
                        "name": c.name,
                        "image": c.image.tags[0] if c.image.tags else "unknown",
                        "status": c.status,
                        "state": c.state,
                    })
                client.close()
                return {"ok": True, "data": result, "source": "docker"}, 200
            except ImportError:
                # docker 库未安装 — 返回模拟数据
                mock = [
                    {"id": "a1b2c3d4", "name": "nginx-web", "image": "nginx:latest",
                     "status": "Up 3 days", "state": "running"},
                    {"id": "e5f6g7h8", "name": "redis-cache", "image": "redis:7-alpine",
                     "status": "Up 2 weeks", "state": "running"},
                    {"id": "i9j0k1l2", "name": "mysql-db", "image": "mysql:8.0",
                     "status": "Exited (0) 5 days ago", "state": "exited"},
                ]
                return {"ok": True, "data": mock, "source": "simulated"}, 200
            except Exception as e:
                return {"ok": False, "error": str(e)}, 500

        @app.route("/api/plugins/docker/info/<container_id>", methods=["GET"])
        def docker_inspect(container_id):
            """查看容器详情"""
            try:
                import docker as docker_lib
                client = docker_lib.from_env()
                c = client.containers.get(container_id)
                info = {
                    "id": c.short_id,
                    "name": c.name,
                    "image": c.image.tags[0] if c.image.tags else "unknown",
                    "status": c.status,
                    "state": c.state,
                    "created": c.attrs.get("Created", ""),
                }
                client.close()
                return {"ok": True, "data": info}, 200
            except ImportError:
                mock = {
                    "id": container_id,
                    "name": f"container-{container_id[:8]}",
                    "image": "nginx:latest",
                    "status": "Up 3 days",
                    "state": "running",
                    "created": "2026-06-10T10:00:00Z",
                }
                return {"ok": True, "data": mock}, 200
            except Exception as e:
                return {"ok": False, "error": str(e)}, 500

        @app.route("/api/plugins/docker/stats", methods=["GET"])
        def docker_stats():
            """Docker 统计概览"""
            try:
                import docker as docker_lib
                client = docker_lib.from_env()
                containers = client.containers.list(all=True)
                running = sum(1 for c in containers if c.status == "running")
                total = len(containers)
                client.close()
                return {"ok": True, "data": {"running": running, "total": total, "images": 5}}, 200
            except ImportError:
                return {"ok": True, "data": {"running": 2, "total": 3, "images": 5}, "source": "simulated"}, 200

    def register_menu(self):
        """注册导航项"""
        return [
            ("Docker", "/plugins/docker", "bi bi-box"),
        ]

    def get_status(self):
        """返回运行状态"""
        try:
            import docker as docker_lib
            client = docker_lib.from_env()
            info = client.info()
            client.close()
            return {
                "enabled": True,
                "docker_version": info.get("ServerVersion", "unknown"),
                "containers": info.get("Containers", 0),
                "running": info.get("ContainersRunning", 0),
            }
        except ImportError:
            return {"enabled": True, "docker_version": "simulated", "containers": 3, "running": 2}
        except Exception:
            return {"enabled": True, "error": "Docker not available"}
