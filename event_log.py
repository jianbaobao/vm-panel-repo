"""
VM Management Panel - 操作日志模块

记录所有 API 操作的审计日志：时间、用户、操作、目标、结果。
"""
import os
import json
from datetime import datetime


class EventLog:
    """轻量事件日志引擎 — 持久化到 JSON"""

    def __init__(self, log_dir=None, max_entries=500):
        self.log_dir = log_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "config"
        )
        self.max_entries = max_entries
        self._cache = None
        self._file = os.path.join(self.log_dir, "events.json")

    def _load(self):
        if self._cache is not None:
            return self._cache
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._cache = []
        else:
            self._cache = []
        return self._cache

    def _save(self):
        os.makedirs(self.log_dir, exist_ok=True)
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, indent=2, ensure_ascii=False)

    def log(self, action, target, detail="", result="success"):
        """
        记录一条操作日志

        Args:
            action: 操作类型 (create/delete/start/stop/...)
            target: 操作对象 (vm-name/net-name/...)
            detail: 详细描述
            result: 结果 (success/fail)
        """
        events = self._load()
        event = {
            "id": len(events) + 1,
            "time": datetime.now().isoformat(),
            "action": action,
            "target": target,
            "detail": detail,
            "result": result,
        }
        events.append(event)
        # 限制条目数
        if len(events) > self.max_entries:
            events = events[-self.max_entries:]
        self._cache = events
        self._save()
        return event

    def list(self, limit=50, offset=0, action_filter=None):
        """获取日志列表，支持过滤和分页"""
        events = self._load()
        if action_filter:
            events = [e for e in events if e["action"] == action_filter]
        # 倒序 (最新的在前)
        events = list(reversed(events))
        total = len(events)
        page = events[offset:offset + limit]
        return page, total

    def clear(self):
        """清空所有日志"""
        self._cache = []
        self._save()

    def stats(self):
        """获取日志统计"""
        events = self._load()
        action_counts = {}
        for e in events:
            action_counts[e["action"]] = action_counts.get(e["action"], 0) + 1
        return {
            "total": len(events),
            "actions": action_counts,
        }


# 全局单例
_elog = EventLog()


def log_event(action, target, detail="", result="success"):
    return _elog.log(action, target, detail, result)


def get_event_log():
    return _elog
