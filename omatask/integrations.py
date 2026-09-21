"""Shell-agnostic status projection. Waybar and Quickshell consume the same JSON."""
import html


def bar_status(engine):
    tasks = engine.list('today')
    overdue = engine.list('overdue')
    return {'text':f'Tasks: {len(tasks)}', 'count':len(tasks),
            'tooltip':html.escape('\n'.join(f'{t.title} ({t.priority})' for t in tasks) or 'No tasks today'),
            'class':'overdue' if overdue else 'normal', 'overdue':len(overdue)}


def widget_snapshot(engine, view='today', query=''):
    """Consistent read projection for a native panel; all filtering stays in core."""
    from zoneinfo import ZoneInfo
    from .timeutil import instant

    engine.store.db.execute('BEGIN')
    try:
        summary = bar_status(engine)
        tasks = engine.list(view, query=query or None)
        rows = []
        for task in tasks:
            row = task.to_dict()
            row['due_label'] = (instant(task.due_at).astimezone(ZoneInfo(engine.zone))
                                .strftime('%d %b · %H:%M') if task.due_at else 'No due date')
            daily_times = [r['value'] for r in engine.store.db.execute(
                "SELECT value FROM reminder_rules WHERE task_id=? AND kind='clock' ORDER BY value", (task.id,))]
            row['daily_reminder_label'] = (f'{len(daily_times)}× {daily_times[0]}–{daily_times[-1]}' if daily_times else '')
            row['overdue'] = (task.status == 'active' and task.due_at is not None
                              and instant(task.due_at) < engine.clock())
            row['progress'] = {'done': sum(s['done'] for s in task.subtasks),
                               'total': len(task.subtasks)}
            rows.append(row)
        result = {'summary': summary, 'view': view, 'query': query,
                  'timezone': engine.zone, 'tasks': rows}
        engine.store.db.execute('COMMIT')
        return result
    except BaseException:
        engine.store.db.execute('ROLLBACK')
        raise
