"""SQLite repository: versioned migrations and explicit write transactions."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .domain import Task

MIGRATIONS = [
    ["""CREATE TABLE tasks (
        id TEXT PRIMARY KEY, title TEXT NOT NULL CHECK(length(trim(title))>0),
        description TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('active','completed','cancelled')),
        priority TEXT NOT NULL CHECK(priority IN ('low','normal','high','urgent')),
        created_at TEXT NOT NULL, due_at TEXT, completed_at TEXT, timezone TEXT NOT NULL,
        recurrence TEXT CHECK(recurrence IS NULL OR json_valid(recurrence)), anchor_at TEXT,
        occurrence_index INTEGER NOT NULL DEFAULT 0 CHECK(occurrence_index>=0))""",
     """CREATE TABLE occurrences (id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        sequence INTEGER NOT NULL CHECK(sequence>=0), due_at TEXT, completed_at TEXT NOT NULL,
        UNIQUE(task_id,sequence))""",
     """CREATE TABLE reminder_rules (id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK(kind IN ('absolute','relative')), value TEXT NOT NULL)""",
     """CREATE TABLE deliveries (id TEXT PRIMARY KEY, rule_id TEXT REFERENCES reminder_rules(id) ON DELETE CASCADE,
        task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE, sequence INTEGER NOT NULL CHECK(sequence>=0),
        fire_at TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('pending','sent','cancelled')),
        delivered_at TEXT, UNIQUE(rule_id,sequence))""",
     "CREATE INDEX deliveries_due ON deliveries(state,fire_at)",
     "CREATE INDEX tasks_due ON tasks(status,due_at)"],
]
MIGRATIONS.append([
    "ALTER TABLE tasks ADD COLUMN tags TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(tags))",
    "ALTER TABLE tasks ADD COLUMN project TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE tasks ADD COLUMN subtasks TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(subtasks))",
])
MIGRATIONS.append([
    "ALTER TABLE occurrences RENAME TO occurrences_v1",
    """CREATE TABLE occurrences (id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        sequence INTEGER NOT NULL CHECK(sequence>=0), due_at TEXT, completed_at TEXT NOT NULL,
        reopened_at TEXT, subtasks TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(subtasks)))""",
    "INSERT INTO occurrences(id,task_id,sequence,due_at,completed_at) SELECT id,task_id,sequence,due_at,completed_at FROM occurrences_v1",
    "DROP TABLE occurrences_v1",
    "CREATE UNIQUE INDEX current_completion ON occurrences(task_id,sequence) WHERE reopened_at IS NULL",
])
MIGRATIONS.append([
    """CREATE TABLE reminder_rules_v4 (id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK(kind IN ('absolute','relative','clock')), value TEXT NOT NULL)""",
    "INSERT INTO reminder_rules_v4 SELECT * FROM reminder_rules",
    """CREATE TABLE deliveries_v4 (id TEXT PRIMARY KEY, rule_id TEXT REFERENCES reminder_rules_v4(id) ON DELETE CASCADE,
        task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE, sequence INTEGER NOT NULL CHECK(sequence>=0),
        fire_at TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('pending','sent','cancelled')),
        delivered_at TEXT, UNIQUE(rule_id,sequence))""",
    "INSERT INTO deliveries_v4 SELECT * FROM deliveries",
    "DROP TABLE deliveries",
    "DROP TABLE reminder_rules",
    "ALTER TABLE reminder_rules_v4 RENAME TO reminder_rules",
    "ALTER TABLE deliveries_v4 RENAME TO deliveries",
    "CREATE INDEX deliveries_due ON deliveries(state,fire_at)",
])
JSON_FIELDS = {"recurrence", "tags", "subtasks"}
TABLES = ("tasks", "occurrences", "reminder_rules", "deliveries")


def default_path():
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "omatask/tasks.db"


class Store:
    def __init__(self, path=None):
        self.path = str(path or default_path())
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
        self.db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("PRAGMA journal_mode=WAL")
        try:
            with self.transaction():
                version = self.db.execute("PRAGMA user_version").fetchone()[0]
                if version > len(MIGRATIONS):
                    raise ValueError("Database is newer than this application; upgrade omatask")
                for index in range(version, len(MIGRATIONS)):
                    for statement in MIGRATIONS[index]:
                        self.db.execute(statement)
                    self.db.execute(f"PRAGMA user_version={index + 1}")
        except BaseException:
            self.db.close()
            raise

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def close(self):
        self.db.close()

    def get(self, task_id):
        if not isinstance(task_id, str) or not task_id:
            raise ValueError('Task ID must be a non-empty string')
        rows = self.db.execute("SELECT * FROM tasks WHERE id=? OR substr(id,1,?)=?", (task_id, len(task_id), task_id)).fetchall()
        if not rows:
            raise KeyError(f"Task not found: {task_id}")
        if len(rows) != 1:
            raise ValueError("Ambiguous task ID; use a longer prefix")
        return self.decode(rows[0])

    @staticmethod
    def decode(row):
        data = dict(row)
        for key in JSON_FIELDS:
            if data.get(key) is not None:
                data[key] = json.loads(data[key])
        return Task(**data)

    def all(self):
        return [self.decode(r) for r in self.db.execute("SELECT * FROM tasks")]

    def save(self, task, new=False):
        task.validate()
        values = task.to_dict()
        for key in JSON_FIELDS:
            if values[key] is not None:
                values[key] = json.dumps(values[key], ensure_ascii=False)
        if new:
            self.db.execute(f"INSERT INTO tasks ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", list(values.values()))
        else:
            self.db.execute(f"UPDATE tasks SET {','.join(k+'=?' for k in values if k!='id')} WHERE id=?", [v for k,v in values.items() if k!='id'] + [task.id])

    def backup(self, path):
        if self.path != ":memory:" and Path(path).resolve() == Path(self.path).resolve():
            raise ValueError("Backup must use a different path")
        # Reserve the destination atomically, including dangling symlinks, and
        # keep task data private even when the caller's umask permits sharing.
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ValueError("Backup destination already exists") from None
        os.close(fd)
        target = sqlite3.connect(path)
        try:
            self.db.backup(target)
        finally:
            target.close()
