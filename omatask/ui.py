"""Minimal curses adapter. Commands delegate to Engine; no task rules in UI."""
import curses
import json
import shlex
import sqlite3
from .parser import parse
from .timeutil import parse_date
from .domain import PRIORITIES


def put(screen, row, text, attr=0):
    h, w = screen.getmaxyx()
    if 0 <= row < h and w > 1:
        try:
            screen.addnstr(row, 0, str(text).replace('\n', ' '), w-1, attr)
        except curses.error:
            pass


def prompt(screen, label, initial=''):
    text = initial
    curses.curs_set(1)
    try:
        while True:
            row = screen.getmaxyx()[0]-1
            screen.move(row, 0); screen.clrtoeol()
            put(screen, row, label + text)
            screen.refresh()
            key = screen.get_wch()
            if key in ('\n','\r'):
                return text
            if key == '\x1b':
                return None
            if key in (curses.KEY_BACKSPACE, '\x7f', '\b'):
                text = text[:-1]
            elif key == '\x15':
                text = ''
            elif isinstance(key, str) and key.isprintable():
                text += key
    finally:
        curses.curs_set(0)


def add_text(engine, text):
    return engine.add(**parse(text,engine.zone,engine.clock()))


def details(screen, data):
    lines = json.dumps(data, ensure_ascii=False, indent=2).splitlines()
    offset = 0
    while True:
        screen.erase()
        height = screen.getmaxyx()[0]-2
        for i, line in enumerate(lines[offset:offset+height]):
            put(screen, i, line)
        put(screen, height+1, 'j/k scroll · q/Esc/Enter back')
        key = screen.get_wch()
        if key in ('q','\x1b','\n','\r'):
            return
        if key in ('j',curses.KEY_DOWN):
            offset = min(max(0,len(lines)-height), offset+1)
        if key in ('k',curses.KEY_UP):
            offset = max(0,offset-1)


def run(engine, view='today', quick=False):
    curses.wrapper(lambda screen: loop(screen, engine, view, quick))


def loop(screen, engine, view, quick):
    curses.curs_set(0)
    screen.keypad(True)
    selection, query, message = 0, '', ''
    draft = ''
    filters = {}
    while True:
        tasks = engine.list(view=view, query=query or None, **filters)
        selection = max(0,min(selection,len(tasks)-1))
        screen.erase()
        h, _ = screen.getmaxyx()
        put(screen, 0, f'OMATASK · {view} · {len(tasks)} tasks · {query} {filters or ""}', curses.A_BOLD)
        visible = max(1,h-5)
        offset = (selection // visible)*visible
        for index, task in enumerate(tasks[offset:offset+visible], offset):
            put(screen, index-offset+2, f'{task.id[:8]} {task.status:9} {task.priority:6} {task.due_at or "—"}  {task.title} [{sum(s["done"] for s in task.subtasks)}/{len(task.subtasks)}]', curses.A_REVERSE if index == selection else 0)
        put(screen,h-3,'a add · d done · c cancel · r reopen · x delete · e edit · / search · f view')
        put(screen,h-2,'Enter details · s snooze · p priority · m project · t tags · b checklist · q quit | ' + message)
        screen.refresh()
        try:
            key = 'a' if quick else screen.get_wch()
            message = ''
            if key in ('q','\x1b'):
                return
            if key in ('j',curses.KEY_DOWN):
                selection += 1
            elif key in ('k',curses.KEY_UP):
                selection = max(0,selection-1)
            elif key == 'a':
                text = prompt(screen,'New task: ',draft)
                if text:
                    draft = text
                    task = add_text(engine,text)
                    message = 'Created ' + task.id[:8]
                    draft = ''
                if quick:
                    return
            elif key == '/':
                answer = prompt(screen,'Search: ',query)
                if answer is not None:
                    query, selection = answer, 0
            elif key == 'f':
                answer = prompt(screen,'View + filters (all tag=work project=Work priority=high): ')
                if answer:
                    parts = shlex.split(answer)
                    new_view = parts[0]
                    new_filters = {}
                    for part in parts[1:]:
                        name, sep, value = part.partition('=')
                        if not sep or name not in ('tag','project','status','priority','due'):
                            raise ValueError('Filters: tag/project/status/priority/due=value')
                        new_filters[name] = value
                    engine.list(view=new_view, **new_filters)
                    view, filters, selection = new_view, new_filters, 0
            elif tasks:
                task = tasks[selection]
                if key in ('\n','\r'):
                    details(screen,engine.show(task.id))
                elif key in ('d','c','r'):
                    getattr(engine,{'d':'done','c':'cancel','r':'reopen'}[key])(task.id)
                elif key == 'x':
                    if prompt(screen,'Delete task and its history? Type yes: ') == 'yes':
                        engine.delete(task.id)
                elif key == 'e':
                    field = prompt(screen,'Edit title/description/due/recurrence: ', 'title')
                    if field in ('title','description','due','recurrence'):
                        current = task.title if field=='title' else task.description if field=='description' else task.due_at or '' if field=='due' else json.dumps(task.recurrence)
                        value = prompt(screen,field+': ',current)
                        if value is not None:
                            if field=='due':
                                engine.edit(task.id,due_at=parse_date(value,task.timezone,engine.clock()).isoformat() if value else None)
                            elif field=='recurrence':
                                engine.edit(task.id,recurrence=json.loads(value) if value else None)
                            else:
                                engine.edit(task.id,**{field:value})
                elif key == 'm':
                    value = prompt(screen,'Project: ',task.project)
                    if value is not None:engine.edit(task.id,project=value)
                elif key == 't':
                    value = prompt(screen,'Tags (space separated): ',' '.join(task.tags))
                    if value is not None:engine.edit(task.id,tags=value.split())
                elif key == 'b':
                    details(screen,engine.show(task.id)['subtasks'])
                    action = prompt(screen,'Checklist add/done/reopen/delete: ')
                    if action:
                        value = prompt(screen,'Title for add; subtask ID otherwise: ')
                        if value:engine.subtask(task.id,action,value)
                elif key == 'n':
                    value = prompt(screen,'Remind before due (30m) or at ISO/time: ')
                    if value:
                        from .timeutil import duration
                        if value.startswith('at '):engine.remind(task.id,at=parse_date(value[3:],task.timezone,engine.clock()))
                        else:engine.remind(task.id,seconds=duration(value))
                elif key == 'p':
                    engine.edit(task.id,priority=PRIORITIES[(PRIORITIES.index(task.priority)+1)%4])
                elif key == 's':
                    value = prompt(screen,'Snooze 10m/30m/1h/evening/tomorrow: ')
                    if value:
                        engine.snooze(task.id,value)
        except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as exc:
            message = str(exc)
            if quick:
                put(screen,h-2,message)
                screen.refresh(); screen.get_wch()
