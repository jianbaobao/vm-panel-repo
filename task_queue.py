"""
VM Management Panel - 异步任务队列

支持后台执行耗时操作 (克隆、快照等)，
通过 SSE 向前端推送进度。
"""
import os
import json
import time
import uuid
import threading
from datetime import datetime
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task:
    def __init__(self, name, action, target, params=None):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.action = action
        self.target = target
        self.params = params or {}
        self.status = TaskStatus.PENDING
        self.progress = 0
        self.message = ""
        self.result = None
        self.error = None
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.finished_at = None
        self._cancel_flag = threading.Event()

    def cancel(self):
        self._cancel_flag.set()
        self.status = TaskStatus.CANCELLED
        self.finished_at = datetime.now().isoformat()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "action": self.action,
            "target": self.target,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at,
        }


class TaskQueue:
    """异步任务队列 — 单 worker 顺序执行"""

    def __init__(self, store_file=None):
        self._tasks = {}  # id -> Task
        self._queue = []
        self._lock = threading.Lock()
        self._worker = None
        self._store_file = store_file or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "config", "tasks.json"
        )
        self._load_tasks()

    def _load_tasks(self):
        if os.path.exists(self._store_file):
            try:
                with open(self._store_file) as f:
                    data = json.load(f)
                for t in data:
                    task = Task(t["name"], t["action"], t["target"], t.get("params"))
                    task.id = t["id"]
                    task.status = TaskStatus(t["status"])
                    task.progress = t.get("progress", 0)
                    task.message = t.get("message", "")
                    task.error = t.get("error")
                    task.created_at = t["created_at"]
                    task.updated_at = t.get("updated_at", task.created_at)
                    task.finished_at = t.get("finished_at")
                    self._tasks[task.id] = task
            except Exception:
                pass

    def _save_tasks(self):
        os.makedirs(os.path.dirname(self._store_file), exist_ok=True)
        with open(self._store_file, "w") as f:
            json.dump([t.to_dict() for t in self._tasks.values()], f, indent=2)

    def add_task(self, name, action, target, params=None, handler=None):
        task = Task(name, action, target, params)
        with self._lock:
            self._tasks[task.id] = task
            if handler:
                self._queue.append((task, handler))
            self._save_tasks()
        # 启动 worker
        self._ensure_worker()
        return task

    def _ensure_worker(self):
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._process_queue, daemon=True)
            self._worker.start()

    def _process_queue(self):
        while True:
            item = None
            with self._lock:
                if self._queue:
                    item = self._queue.pop(0)
            if item is None:
                break  # 队列为空，退出 worker

            task, handler = item
            try:
                task.status = TaskStatus.RUNNING
                task.updated_at = datetime.now().isoformat()
                self._save_tasks()

                def update_progress(pct, msg=""):
                    task.progress = min(pct, 100)
                    task.message = msg
                    task.updated_at = datetime.now().isoformat()
                    self._save_tasks()

                result = handler(task, update_progress)
                task.status = TaskStatus.COMPLETED
                task.progress = 100
                task.result = result
                task.message = "Completed"
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.message = f"Failed: {e}"
            finally:
                task.finished_at = datetime.now().isoformat()
                task.updated_at = task.finished_at
                self._save_tasks()

        with self._lock:
            self._worker = None

    def list_tasks(self, limit=50):
        tasks = list(self._tasks.values())
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return [t.to_dict() for t in tasks[:limit]]

    def get_task(self, task_id):
        t = self._tasks.get(task_id)
        return t.to_dict() if t else None

    def cancel_task(self, task_id):
        t = self._tasks.get(task_id)
        if t and t.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            t.cancel()
            self._save_tasks()
            return True
        return False

    def clear_finished(self):
        with self._lock:
            self._tasks = {k: v for k, v in self._tasks.items()
                          if v.status in (TaskStatus.PENDING, TaskStatus.RUNNING)}
            self._save_tasks()


# 全局单例
_queue = TaskQueue()


def get_queue():
    return _queue
