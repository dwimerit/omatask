from dataclasses import dataclass, field, asdict
from .recurrence import Rule
from .timeutil import instant
from zoneinfo import ZoneInfo

PRIORITIES = ("low", "normal", "high", "urgent")
STATUSES = ("active", "completed", "cancelled")


@dataclass
class Task:
    id: str
    title: str
    description: str
    status: str
    priority: str
    created_at: str
    due_at: str | None
    completed_at: str | None
    timezone: str
    recurrence: dict | None
    anchor_at: str | None
    occurrence_index: int = 0

    tags: list[str] = field(default_factory=list)
    project: str = ""
    subtasks: list[dict] = field(default_factory=list)

    def validate(self):
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("Task ID must be a non-empty string")
        if not isinstance(self.description, str):
            raise ValueError("Description must be a string")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("Title cannot be empty")
        if self.priority not in PRIORITIES or self.status not in STATUSES:
            raise ValueError("Invalid priority/status")
        if not isinstance(self.tags, list) or any(not isinstance(t, str) or not t.strip() for t in self.tags):
            raise ValueError("Tags must be non-empty strings")
        if not isinstance(self.project, str):
            raise ValueError("Project must be a string")
        if not isinstance(self.subtasks, list):
            raise ValueError("Subtasks must be a list")
        ids = set()
        for sub in self.subtasks:
            if not isinstance(sub, dict) or set(sub) != {"id", "title", "done"} or not isinstance(sub["title"], str) or not sub["title"].strip() or type(sub["done"]) is not bool or not isinstance(sub["id"], str) or not sub["id"] or sub["id"] in ids:
                raise ValueError("Invalid or duplicate subtask")
            ids.add(sub["id"])
        ZoneInfo(self.timezone)
        for value in (self.created_at, self.due_at, self.completed_at, self.anchor_at):
            if value:
                instant(value)
        if (self.status == "completed") != (self.completed_at is not None):
            raise ValueError("Completion timestamp must agree with status")
        if type(self.occurrence_index) is not int or self.occurrence_index < 0:
            raise ValueError("Invalid occurrence index")
        if self.recurrence is not None:
            if not isinstance(self.recurrence, dict) or not self.recurrence:
                raise ValueError("Recurrence must be a non-empty object or null")
            Rule(**self.recurrence)
            if not self.due_at or not self.anchor_at:
                raise ValueError("Recurring task needs a due date")

    def to_dict(self):
        return asdict(self)
