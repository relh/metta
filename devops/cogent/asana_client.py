"""Asana API client for the Cogent agent platform.

Thin wrapper using urllib.request — no SDK. Fetches tasks assigned to the agent user,
reads full task context (description, comments, custom fields), and posts results back.
"""

import json
import os
import urllib.request
from datetime import datetime

from pydantic import BaseModel

ASANA_BASE = "https://app.asana.com/api/1.0"


class TaskComment(BaseModel):
    author: str
    text: str
    created_at: str


class TaskContext(BaseModel):
    gid: str
    name: str
    notes: str
    project_names: list[str]
    tags: list[str]
    custom_fields: dict[str, str]
    due_on: str | None
    parent_name: str | None
    parent_notes: str | None
    comments: list[TaskComment]
    skill: str | None = None
    branch: str | None = None

    def to_prompt(self) -> str:
        lines = [f"# Asana Task: {self.name}"]

        meta_parts = []
        if self.project_names:
            meta_parts.append(f"**Project:** {', '.join(self.project_names)}")
        if self.tags:
            meta_parts.append(f"**Tags:** {', '.join(self.tags)}")
        if self.due_on:
            meta_parts.append(f"**Due:** {self.due_on}")
        if self.custom_fields:
            cf = ", ".join(f"{k}: {v}" for k, v in self.custom_fields.items())
            meta_parts.append(f"**Custom fields:** {cf}")
        if meta_parts:
            lines.append("")
            lines.extend(meta_parts)

        if self.parent_name:
            lines.append("")
            lines.append(f"**Parent task:** {self.parent_name}")
            if self.parent_notes:
                lines.append(f"> {self.parent_notes}")

        if self.notes:
            lines.append("")
            lines.append("## Description")
            lines.append("")
            lines.append(self.notes)

        if self.comments:
            lines.append("")
            lines.append("## Comments")
            lines.append("")
            for c in self.comments:
                ts = c.created_at[:16].replace("T", " ")
                lines.append(f"[{c.author}, {ts}]: {c.text}")

        return "\n".join(lines)

    @property
    def latest_comment_time(self) -> str | None:
        if not self.comments:
            return None
        return max(c.created_at for c in self.comments)


class AsanaClient:
    def __init__(
        self,
        token: str,
        workspace_gid: str,
        agent_user_gid: str,
        running_tag_gid: str,
    ):
        self.token = token
        self.workspace_gid = workspace_gid
        self.agent_user_gid = agent_user_gid
        self.running_tag_gid = running_tag_gid

    @classmethod
    def from_env(cls) -> "AsanaClient":
        return cls(
            token=os.environ["ASANA_TOKEN"],
            workspace_gid=os.environ["ASANA_WORKSPACE_GID"],
            agent_user_gid=os.environ["ASANA_AGENT_USER_GID"],
            running_tag_gid=os.environ["ASANA_RUNNING_TAG_GID"],
        )

    def _request(self, method: str, path: str, data: dict | None = None) -> dict:
        url = f"{ASANA_BASE}{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(
            url,
            method=method,
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        return json.loads(urllib.request.urlopen(req).read())

    def get_assigned_tasks(self) -> list[dict]:
        """Incomplete tasks assigned to the agent user."""
        now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        path = (
            f"/tasks?assignee={self.agent_user_gid}"
            f"&workspace={self.workspace_gid}"
            f"&completed_since={now_iso}"
            f"&opt_fields=name,completed"
        )
        resp = self._request("GET", path)
        return [t for t in resp["data"] if not t.get("completed")]

    def get_task_context(self, task_gid: str) -> TaskContext:
        opt_fields = ",".join(
            [
                "name",
                "notes",
                "custom_fields",
                "custom_fields.name",
                "custom_fields.display_value",
                "tags",
                "tags.name",
                "projects",
                "projects.name",
                "due_on",
                "parent",
                "parent.name",
                "parent.notes",
            ]
        )
        task = self._request("GET", f"/tasks/{task_gid}?opt_fields={opt_fields}")["data"]

        stories = self._request(
            "GET",
            f"/tasks/{task_gid}/stories?opt_fields=text,created_by.name,resource_subtype,created_at",
        )["data"]
        comments = [
            TaskComment(
                author=s["created_by"]["name"],
                text=s["text"],
                created_at=s["created_at"],
            )
            for s in stories
            if s.get("resource_subtype") == "comment_added"
        ]

        custom_fields: dict[str, str] = {}
        skill = None
        branch = None
        for cf in task.get("custom_fields") or []:
            name = cf.get("name", "")
            value = cf.get("display_value") or ""
            if not value:
                continue
            custom_fields[name] = value
            if name.lower() == "skill":
                skill = value
            elif name.lower() == "branch":
                branch = value

        parent = task.get("parent")

        return TaskContext(
            gid=task_gid,
            name=task["name"],
            notes=task.get("notes") or "",
            project_names=[p["name"] for p in task.get("projects") or []],
            tags=[t["name"] for t in task.get("tags") or []],
            custom_fields=custom_fields,
            due_on=task.get("due_on"),
            parent_name=parent["name"] if parent else None,
            parent_notes=parent.get("notes") if parent else None,
            comments=comments,
            skill=skill,
            branch=branch,
        )

    def post_comment(self, task_gid: str, text: str):
        self._request("POST", f"/tasks/{task_gid}/stories", {"data": {"text": text}})

    def complete_task(self, task_gid: str):
        self._request("PUT", f"/tasks/{task_gid}", {"data": {"completed": True}})

    def add_tag(self, task_gid: str, tag_gid: str):
        self._request("POST", f"/tasks/{task_gid}/addTag", {"data": {"tag": tag_gid}})

    def remove_tag(self, task_gid: str, tag_gid: str):
        self._request("POST", f"/tasks/{task_gid}/removeTag", {"data": {"tag": tag_gid}})
