"""Stable, scriptable CLI. JSON is stdout only; errors are stderr."""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from zoneinfo import ZoneInfoNotFoundError
from pathlib import Path
from .domain import PRIORITIES, STATUSES
from .engine import Engine
from .persistence import Store
from .recurrence import Rule
from .timeutil import parse_date, duration
from .reminders import dispatch


def parser():
    p = argparse.ArgumentParser(prog='omatask')
    p.add_argument('--db', help='SQLite path (default: XDG_DATA_HOME/omatask/tasks.db)')
    p.add_argument('--timezone', help='IANA zone; defaults to system timezone')
    p.add_argument('--json', action='store_true', help='Machine-readable output')
    commands = p.add_subparsers(dest='command', required=True)
    for name in ('add','edit'):
        c = commands.add_parser(name)
        c.add_argument('text' if name == 'add' else 'id')
        if name == 'edit':
            c.add_argument('--title')
        c.add_argument('--description')
        c.add_argument('--tag', action='append', help='Repeat for multiple tags; edit replaces tags')
        c.add_argument('--project')
        if name == 'add':
            c.add_argument('--literal', action='store_true', help='Disable metadata parser')
            c.add_argument('--remind', action='append', default=[])
            c.add_argument('--remind-at', action='append', default=[])
        else:
            c.add_argument('--clear-tags', action='store_true')
        c.add_argument('--priority', choices=PRIORITIES)
        c.add_argument('--due', help='ISO / today / tomorrow / weekday [HH:MM] / in 2h; none clears')
        c.add_argument('--repeat', choices=['minute','hour','day','week','month','none'])
        c.add_argument('--interval', type=int)
        c.add_argument('--count', type=int)
        c.add_argument('--until')
        c.add_argument('--weekdays', help='mon,wed,fri')
    for name in ('list','search'):
        c = commands.add_parser(name)
        c.add_argument('query' if name == 'search' else 'view', nargs='?' if name == 'list' else None, default='all' if name == 'list' else None)
        c.add_argument('--project')
        c.add_argument('--tag')
        c.add_argument('--status', choices=STATUSES)
        c.add_argument('--priority', choices=PRIORITIES)
        c.add_argument('--due', help='YYYY-MM-DD')
        c.add_argument('--recurring', action='store_true')
    for name in ('show','done','cancel','reopen','delete'):
        commands.add_parser(name).add_argument('id')
    c = commands.add_parser('remind')
    c.add_argument('id'); c.add_argument('offset', nargs='?'); c.add_argument('--at')
    c = commands.add_parser('snooze')
    c.add_argument('id'); c.add_argument('duration', choices=None)
    c = commands.add_parser('worker')
    c.add_argument('--once', action='store_true'); c.add_argument('--interval', type=float, default=10)
    c = commands.add_parser('ui')
    c.add_argument('view', nargs='?', default='today')
    commands.add_parser('quick')
    c = commands.add_parser('backup'); c.add_argument('path')
    c = commands.add_parser('subtask')
    c.add_argument('id'); c.add_argument('action', choices=['add','done','reopen','delete']); c.add_argument('value')
    commands.add_parser('stats')
    commands.add_parser('bar')
    c = commands.add_parser('widget', help='Native panel JSON snapshot')
    c.add_argument('view', nargs='?', default='today', choices=['today','tomorrow','upcoming','overdue','completed','recurring','all'])
    c.add_argument('--query', default='')
    c = commands.add_parser('export'); c.add_argument('path', nargs='?', default='-'); c.add_argument('--format', choices=['json','markdown'], default='json')
    c = commands.add_parser('import'); c.add_argument('path')
    return p


def build_rule(args, engine):
    if not args.repeat:
        if any(getattr(args, k) is not None for k in ('interval','count','until','weekdays')):
            raise ValueError('--interval/--count/--until/--weekdays require --repeat')
        return None
    if args.repeat == 'none':
        return None
    days = None
    if args.weekdays:
        names = ['mon','tue','wed','thu','fri','sat','sun']
        days = sorted(set(names.index(x.lower()) for x in args.weekdays.split(',')))
    return Rule(args.repeat, args.interval if args.interval is not None else 1, args.count,
                parse_date(args.until, engine.zone, engine.clock()).isoformat() if args.until else None, days).to_dict()


def execute(args, engine):
    cmd = args.command
    if cmd == 'add':
        from .parser import parse
        data = {'title':args.text} if args.literal else parse(args.text, engine.zone, engine.clock())
        if args.description is not None:data['description']=args.description
        if args.priority is not None:data['priority']=args.priority
        if args.due is not None:
            data['due'] = parse_date(args.due, engine.zone, engine.clock()) if args.due != 'none' else None
        rule = build_rule(args, engine)
        if args.repeat:data['recurrence']=rule
        if args.tag is not None:data['tags']=args.tag
        if args.project is not None:data['project']=args.project
        specs = data.setdefault('reminder_specs', [])
        specs.extend({'seconds':duration(v)} for v in args.remind)
        specs.extend({'at':parse_date(v,engine.zone,engine.clock())} for v in args.remind_at)
        return engine.add(**data)
    if cmd == 'edit':
        changes = {k: getattr(args,k) for k in ('title','description','priority','project') if getattr(args,k) is not None}
        if args.tag is not None or args.clear_tags:
            changes['tags']=sorted(set(args.tag or []))
        if args.due is not None:
            changes['due_at'] = parse_date(args.due, engine.zone, engine.clock()).isoformat() if args.due != 'none' else None
        rule = build_rule(args, engine)
        if args.repeat:
            changes['recurrence'] = rule
        return engine.edit(args.id, **changes)
    if cmd in ('done','cancel','reopen','delete','show'):
        return getattr(engine, cmd)(args.id)
    if cmd in ('list','search'):
        return engine.list(view=args.view if cmd == 'list' else 'all', query=args.query if cmd == 'search' else None,
                           status=args.status, priority=args.priority, due=args.due, recurring=args.recurring, project=args.project, tag=args.tag)
    if cmd == 'remind':
        return engine.remind(args.id, seconds=duration(args.offset) if args.offset else None,
                             at=parse_date(args.at, engine.store.get(args.id).timezone, engine.clock()) if args.at else None)
    if cmd == 'snooze':
        return engine.snooze(args.id, args.duration)
    if cmd == 'subtask':
        return engine.subtask(args.id,args.action,args.value)
    if cmd == 'stats':
        return engine.stats()
    if cmd == 'widget':
        from .integrations import widget_snapshot
        print(json.dumps(widget_snapshot(engine, args.view, args.query), ensure_ascii=False))
        return None
    if cmd == 'bar':
        from .integrations import bar_status
        print(json.dumps(bar_status(engine),ensure_ascii=False))
        return None
    if cmd == 'import':
        from .transfer import import_data
        return import_data(engine.store,json.loads(Path(args.path).read_text()))
    if cmd == 'export':
        from .transfer import export_data, markdown
        content = json.dumps(export_data(engine.store),ensure_ascii=False,indent=2)+'\n' if args.format == 'json' else markdown(engine.store)
        if args.path == '-':
            sys.stdout.write(content)
        else:
            # Exclusive creation prevents accidental overwrite of backups or the live database.
            with open(args.path, 'x', encoding='utf-8',
                      opener=lambda path, flags: os.open(path, flags, 0o600)) as file:
                file.write(content)
        return None
    if cmd == 'backup':
        engine.store.backup(args.path)
        return {'backup': args.path}
    if cmd == 'worker':
        if args.interval <= 0:
            raise ValueError('Worker interval must be positive')
        while True:
            sent = dispatch(engine.store)
            if args.once:
                return {'sent': sent}
            time.sleep(args.interval)
    if cmd in ('ui','quick'):
        from .ui import run
        run(engine, view=getattr(args,'view','today'), quick=cmd == 'quick')
        return None


def serializable(value):
    if hasattr(value, 'to_dict'):
        return value.to_dict()
    raise TypeError(type(value).__name__)


def output(result, as_json=False):
    if result is None:
        return
    if as_json:
        print(json.dumps(result, default=serializable, ensure_ascii=False))
    elif isinstance(result, list):
        for task in result:
            print(f'{task.id[:8]}  {task.status:9} {task.priority:6} {task.due_at or "—":32} {task.title}  [{sum(s["done"] for s in task.subtasks)}/{len(task.subtasks)}]')
    elif hasattr(result,'title'):
        print(f'{result.id[:8]}  {result.title}  [{result.status}]')
    else:
        print(json.dumps(result, default=serializable, ensure_ascii=False, indent=2))


def main(argv=None):
    args = parser().parse_args(argv)
    store = None
    try:
        store = Store(args.db)
        output(execute(args, Engine(store, args.timezone)), args.json)
        return 0
    except ZoneInfoNotFoundError as exc:
        print(f'omatask: Unknown IANA timezone: {exc}', file=sys.stderr); return 2
    except KeyError as exc:
        print(f'omatask: {exc}', file=sys.stderr); return 3
    except (ValueError, TypeError, OverflowError) as exc:
        print(f'omatask: {exc}', file=sys.stderr); return 2
    except (OSError, sqlite3.Error, subprocess.SubprocessError) as exc:
        print(f'omatask: {exc}', file=sys.stderr); return 1
    except KeyboardInterrupt:
        return 130
    finally:
        if store:
            store.close()
