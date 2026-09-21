#!/usr/bin/env python3
"""Opt-in live desktop test. Uses uniquely tagged tasks and removes only those tasks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

CLI = str(Path.home()/'.local/bin/omatask')
PANEL = str(Path.home()/'.local/bin/omatask-panel')
TAG = 'omatask-smoke-' + uuid.uuid4().hex[:8]
created = []


def run(*args):
    return subprocess.check_output(args,text=True,stderr=subprocess.PIPE).strip()


def cli(*args):return json.loads(run(CLI,'--json',*args))


def status():return json.loads(run('omarchy-shell','local.omatask-'+screen,'status'))


def wait(predicate, label, timeout=12):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=predicate()
        if value:return value
        time.sleep(0.15)
    raise AssertionError('Timeout: '+label+'; status='+str(status()))


def key(name):
    assert status()['opened'], 'Panel closed; refusing to type into another app'
    run('wtype','-k',name)


def type_text(text):
    assert status()['opened'], 'Panel closed; refusing to type into another app'
    run('wtype','--',text)


def capture(name):
    state=status()
    r=state['rect']
    geometry=f"{monitor['x']+r['x']},{monitor['y']+r['y']} {r['width']}x{r['height']}"
    run('grim','-g',geometry,'/tmp/'+name)


monitors=json.loads(run('hyprctl','monitors','-j'))
monitor=next(m for m in monitors if m['focused'])
screen=monitor['name']
def reset_test_filter():
    current = status()
    if current['query'].startswith('omatask-smoke-') or current['query'] == 'Проверка виджета':
        run(PANEL, 'open')
        wait(lambda:status()['inputFocused'], 'cleanup input focus')
        key('Down'); type_text('/')
        run('wtype','-M','ctrl','a','-m','ctrl','-k','BackSpace')
        key('Return')
        wait(lambda:status()['query']=='', 'cleanup search cleared')
    if status()['opened']:
        while status()['view'] != 'today':
            before = status()['view']
            type_text('f')
            wait(lambda:status()['view'] != before, 'cleanup view')
        type_text('a')
    run(PANEL,'close')


def invoke_binding(description):
    # wtype uses a synthetic keymap which Hyprland does not resolve like a
    # physical keyboard for global shortcuts. Verify the registered binding
    # and invoke its actual compositor dispatcher instead.
    bindings=json.loads(run('hyprctl','binds','-j'))
    binding=next(b for b in bindings if b.get('description')==description)
    assert binding['modmask']==72 and binding['key'] in ('T','N'), binding
    command = 'omarchy-shell shell toggle local.omatask' if description == 'Omatask: tasks' else PANEL + ' quick'
    # o.bind converts this string to hl.dsp.exec_cmd; test its command in
    # the compositor environment. Private __lua dispatchers cannot be called externally.
    run('hyprctl','eval','hl.exec_cmd(' + json.dumps(command) + ')')


def check_search_from_input():
    """Exercise the real TextField key path, without creating a task."""
    assert status()['inputFocused'] and status()['mode']=='add'
    run('wtype','-M','ctrl','a','-m','ctrl','-k','BackSpace')
    type_text('/')
    wait(lambda:status()['mode']=='search' and status()['inputFocused'],'slash opens search from empty input')
    query=TAG+'/path'
    type_text(query);key('Return')
    wait(lambda:status()['query']==query and status()['rows']==0 and status()['listFocused'],'search consumes its shortcut and preserves slashes in the query')
    assert not status()['detailShown']
    key('Escape')
    wait(lambda:status()['query']=='' and status()['mode']=='add' and status()['opened'],'Esc clears search without closing panel')
    type_text('/')
    wait(lambda:status()['inputFocused'],'search draft focus')
    type_text(TAG);key('Escape')
    wait(lambda:status()['query']=='' and status()['mode']=='add' and status()['opened'] and status()['listFocused'],'Esc cancels search draft')
    type_text('a')
    wait(lambda:status()['mode']=='add' and status()['inputFocused'],'return to creation')
    type_text('Read /tmp/notes')
    assert status()['mode']=='add', 'A slash inside a title must stay ordinary text'
    run('wtype','-M','ctrl','a','-m','ctrl','-k','BackSpace')


if '--shortcuts-only' in sys.argv:
    reset_test_filter()
    invoke_binding('Omatask: tasks')
    wait(lambda:status()['opened'] and status()['inputFocused'],'Super+Alt+T opens panel')
    check_search_from_input()
    invoke_binding('Omatask: tasks')
    wait(lambda:not status()['opened'],'Super+Alt+T closes panel')
    invoke_binding('Omatask: new task')
    wait(lambda:status()['opened'] and status()['inputFocused'],'Super+Alt+N opens quick entry')
    check_search_from_input()
    run(PANEL,'close')
    assert json.loads(run('omarchy-shell','local.omatask-reminders','status'))['ready']
    assert not run('hyprctl','configerrors')
    log=run('quickshell','log','-p','/usr/share/omarchy/shell','--tail','500','--no-color')
    problems=[line for line in log.splitlines() if 'WARN' in line and 'local.omatask' in line]
    assert not problems, problems
    for m in monitors:
        data=json.loads(run('omarchy-shell','local.omatask-'+m['name'],'status'))
        assert data['loaded'] and not data['error'], data
    print('PASS registered Super+Alt+T/N and their commands / slash search from both input fields / Esc exits search and cancels drafts / literal slash inside titles / both outputs / active enabled worker / clean widget log')
    raise SystemExit(0)


try:
    deadline=time.monotonic()+15
    while True:
        try:
            ready=status()
            if ready.get('loaded') and 'rect' in ready:break
        except (subprocess.CalledProcessError,ValueError):pass
        if time.monotonic()>deadline:raise AssertionError('Updated widget did not become ready')
        time.sleep(0.25)
    run(PANEL,'quick')
    wait(lambda:status()['inputFocused'],'quick input focus')
    type_text('Invalid !wrong')
    key('Return')
    wait(lambda:status()['error'] and not status()['busy'],'visible parser error')
    assert status()['opened']
    run('wtype','-M','ctrl','a','-m','ctrl')
    type_text('Проверка виджета today 23:59 #'+TAG+' !high')
    key('Return')
    task=wait(lambda:next(iter(cli('list','all','--tag',TAG)),None),'GUI task persisted')
    created.append(task['id'])
    wait(lambda:not status()['opened'],'quick closes on success')
    for m in monitors:
        data=json.loads(run('omarchy-shell','local.omatask-'+m['name'],'status'))
        assert data['count'] >= 1, data
    print('PASS quick entry / Unicode / two-output counter',flush=True)

    run(PANEL,'open')
    wait(lambda:status()['inputFocused'],'open focus')
    # Empty input ↓ enters keyboard navigation; search selects only our task.
    key('Down');type_text('/');type_text(TAG);key('Return')
    # Tag is not part of text search. Search by unique title instead.
    wait(lambda:status()['query']==TAG and status()['rows']==0,'search result')
    type_text('/');run('wtype','-M','ctrl','a','-m','ctrl');type_text('Проверка виджета');key('Return')
    wait(lambda:status()['rows']==1,'search finds task')
    key('Down')
    wait(lambda:status()['selectedId']==task['id'],'select search result')
    assert not status()['detailShown'], 'Search Enter must not open details'
    time.sleep(0.2)
    capture('omatask-widget.png')
    type_text('s')
    wait(lambda:status()['mode']=='snooze' and status()['inputFocused'],'snooze editor')
    key('Return')
    wait(lambda:any(d['rule_id'] is None and d['state']=='pending' for d in cli('show',task['id'])['deliveries']),'snooze persisted')
    wait(lambda:not status()['busy'],'snooze completed')
    print('PASS search / selection / snooze',flush=True)

    type_text('e')
    wait(lambda:status()['mode']=='edit' and status()['inputFocused'],'edit editor')
    type_text('Готовый виджет '+TAG);key('Return')
    wait(lambda:cli('show',task['id'])['title']=='Готовый виджет '+TAG,'rename saved')
    wait(lambda:not status()['busy'],'rename complete')
    type_text('/');run('wtype','-M','ctrl','a','-m','ctrl');type_text(TAG);key('Return')
    wait(lambda:status()['rows']==1,'renamed task found')
    key('Down')
    wait(lambda:status()['selectedId']==task['id'],'renamed task selected')
    key('Return');wait(lambda:status()['detailShown'],'task details')
    key('Escape')
    type_text('d');wait(lambda:cli('show',task['id'])['status']=='completed','done persisted')
    wait(lambda:not status()['busy'],'done complete')
    print('PASS title edit / details / complete',flush=True)
    while status()['view'] != 'all':
        before = status()['view']
        type_text('f')
        wait(lambda:status()['view'] != before, 'switch to All')
    wait(lambda:status()['view']=='all' and status()['rows']==1,'All view includes completed')
    key('Down')
    wait(lambda:status()['selectedId']==task['id'],'select completed task')
    type_text('r')
    wait(lambda:cli('show',task['id'])['status']=='active' and not status()['busy'],'reopen')
    type_text('x')
    wait(lambda:status()['deleteConfirm'],'delete confirmation')
    key('Right');key('Return')
    wait(lambda:not cli('list','all','--tag',TAG),'delete persisted')
    print('PASS view switch / reopen / confirmed deletion / parser errors',flush=True)
    run(PANEL,'close')

    # Test the actual plugin worker and freedesktop notification server.
    notification=cli('add','Omatask: проверка уведомлений','--literal','--tag',TAG,'--remind-at','in 1m')
    created.append(notification['id'])
    cli('remind',notification['id'],'--at','2000-01-01T00:00:00+00:00')
    wait(lambda:any(d['state']=='sent' for d in cli('show',notification['id'])['deliveries']),
         'plugin notification delivery',timeout=15)
    print('PASS real reminder delivery through the plugin and desktop D-Bus',flush=True)
finally:
    # Include tasks created by GUI before an assertion failed; match unique tag only.
    try:
        for task in cli('list','all','--tag',TAG):
            cli('delete',task['id'])
        reset_test_filter()
        for m in monitors:run('omarchy-shell','local.omatask-'+m['name'],'refresh')
    except Exception as exc:print('Cleanup needs attention:',exc,flush=True)
