from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from typing import Any

from .models import new_id, now_iso
from .privacy import sanitize_diagnostic
from .store import ProjectStore
from .workflow import execute_plan


class PlanTaskManager:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="aida-plan")
        self._lock = Lock()
        self._tasks: dict[str, dict[str, Any]] = {}
        self._cancellations: dict[str, Event] = {}

    def start(self, project_directory: str, plan_id: str, language: str) -> dict[str, Any]:
        store = ProjectStore(project_directory)
        plan = store.get_plan(plan_id)
        with self._lock:
            for task in self._tasks.values():
                if task["planId"] == plan_id and task["status"] in {"queued", "running", "cancelling"}:
                    raise ValueError("The analysis plan already has an active task")
            if plan["status"] == "running":
                # A running status without an in-memory task means the prior app process was interrupted.
                plan["status"] = "failed"
                for step in plan["steps"]:
                    if step["status"] in {"queued", "running"}:
                        step["status"] = "failed"
                        step["error"] = "The previous application session ended before this step completed"
                store.save_plan(plan)
                store.audit("analysis.plan.interrupted", {"planId": plan_id})
            task_id = new_id("task")
            task = {
                "id": task_id, "planId": plan_id, "projectDirectory": project_directory,
                "status": "queued", "progress": 0.0, "message": "Queued",
                "createdAt": now_iso(), "updatedAt": now_iso(), "result": None, "error": None,
            }
            self._tasks[task_id] = task
            self._cancellations[task_id] = Event()
        self._executor.submit(self._run, task_id, language)
        return self.snapshot(task_id, include_result=False)

    def _run(self, task_id: str, language: str) -> None:
        with self._lock:
            task = self._tasks[task_id]
            task["status"] = "cancelling" if self._cancellations[task_id].is_set() else "running"
            task["message"] = "Cancellation requested" if task["status"] == "cancelling" else "Running"
            task["updatedAt"] = now_iso()
            project_directory = task["projectDirectory"]
            plan_id = task["planId"]
            cancellation = self._cancellations[task_id]

        def progress(event: dict[str, Any]) -> None:
            with self._lock:
                current = self._tasks[task_id]
                current["progress"] = float(event.get("progress", current["progress"]))
                current["message"] = str(event.get("message", current["message"]))
                current["updatedAt"] = now_iso()

        try:
            result = execute_plan(ProjectStore(project_directory), plan_id, language, cancellation.is_set, progress)
            with self._lock:
                task = self._tasks[task_id]
                task["result"] = result
                task["status"] = "cancelled" if result.get("cancelled") else "failed" if result.get("error") else "completed"
                task["progress"] = 1.0 if task["status"] == "completed" else task["progress"]
                task["message"] = {"completed": "Completed", "failed": "Failed", "cancelled": "Cancelled"}[task["status"]]
                task["updatedAt"] = now_iso()
        except Exception as error:
            diagnostic = sanitize_diagnostic(error)
            with self._lock:
                task = self._tasks[task_id]
                task["status"] = "failed"
                task["error"] = diagnostic
                task["message"] = diagnostic
                task["updatedAt"] = now_iso()

    def cancel(self, task_id: str, project_directory: str | None = None) -> dict[str, Any]:
        with self._lock:
            if task_id not in self._tasks:
                raise KeyError(f"Unknown task: {task_id}")
            task = self._tasks[task_id]
            if project_directory and ProjectStore(project_directory).root != ProjectStore(task["projectDirectory"]).root:
                raise ValueError("The task does not belong to this project")
            if task["status"] in {"queued", "running"}:
                self._cancellations[task_id].set()
                task["status"] = "cancelling"
                task["message"] = "Cancellation requested"
                task["updatedAt"] = now_iso()
        return self.snapshot(task_id, include_result=False, project_directory=project_directory)

    def snapshot(self, task_id: str, include_result: bool = True, project_directory: str | None = None) -> dict[str, Any]:
        with self._lock:
            if task_id not in self._tasks:
                raise KeyError(f"Unknown task: {task_id}")
            if project_directory and ProjectStore(project_directory).root != ProjectStore(self._tasks[task_id]["projectDirectory"]).root:
                raise ValueError("The task does not belong to this project")
            task = json.loads(json.dumps(self._tasks[task_id], ensure_ascii=False, default=str))
        if not include_result:
            task.pop("result", None)
        task["plan"] = ProjectStore(task["projectDirectory"]).get_plan(task["planId"])
        task.pop("projectDirectory", None)
        return {"task": task}


plan_tasks = PlanTaskManager()
