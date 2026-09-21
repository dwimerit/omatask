"""Predictable English token grammar, pure and separately testable.

Metadata tokens may occur anywhere. Quote a whole title using CLI --literal when
metadata-like words are intended literally. Project names with spaces: +"Side Project".
"""
import re
import shlex
from .timeutil import parse_date, duration, WEEKDAYS, now
from .recurrence import Rule
from .daily_window import spread_times, window_due


def parse(text, zone, clock=None):
    clock = clock or now()
    tokens = shlex.split(text)
    result = {'title':'', 'tags':[], 'project':'', 'priority':'normal', 'due':None,
              'recurrence':None, 'reminder_specs':[]}
    title=[]; rule={}; due_text=None; index=0
    daily_count = None
    daily_range = None
    while index < len(tokens):
        token=tokens[index]
        low=token.lower()
        def take():
            nonlocal index
            index += 1
            if index >= len(tokens):
                raise ValueError(f'Missing value after {token}')
            return tokens[index]
        if low == 'goal' or re.fullmatch(r'\d+x', low):
            if daily_count is not None:
                raise ValueError('Only one daily reminder count is allowed')
            daily_count = int(take()) if low == 'goal' else int(low[:-1])
        elif low == 'between' or re.fullmatch(r'\d{2}:\d{2}-\d{2}:\d{2}', token):
            if daily_range is not None:
                raise ValueError('Only one daily reminder window is allowed')
            daily_range = take() if low == 'between' else token
        elif token.startswith('#') and len(token)>1:
            result['tags'].append(token[1:])
        elif token.startswith('+') and len(token)>1:
            result['project']=token[1:]
        elif token.startswith('!'):
            if token[1:] not in ('low','normal','high','urgent'):
                raise ValueError('Priority: !low/!normal/!high/!urgent')
            result['priority']=token[1:]
        elif low in ('today','tomorrow',*WEEKDAYS) or re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:T.*)?',token):
            if due_text is not None:
                raise ValueError('Only one due date is allowed')
            due_text=token
            if index+1 < len(tokens) and re.fullmatch(r'\d{2}:\d{2}',tokens[index+1]):
                due_text += ' ' + take()
        elif re.fullmatch(r'\d{2}:\d{2}',token):
            if due_text is not None:
                raise ValueError('Only one due time is allowed')
            due_text=token
        elif low == 'in':
            if index+1 < len(tokens) and re.fullmatch(r'\d+[mhdw]',tokens[index+1]):
                if due_text is not None:
                    raise ValueError('Only one due date is allowed')
                due_text='in '+take()
            else:
                title.append(token)
        elif low == 'remind':
            value=take()
            if value == 'at':
                value=take()
                # Absolute ISO value or one quoted date expression.
                result['reminder_specs'].append({'at':parse_date(value,zone,clock)})
            else:
                result['reminder_specs'].append({'seconds':duration(value)})
        elif low in ('daily','weekly','monthly'):
            if 'frequency' in rule:raise ValueError('Only one recurrence rule is allowed')
            rule['frequency']={'daily':'day','weekly':'week','monthly':'month'}[low]
        elif low == 'every':
            if 'frequency' in rule:raise ValueError('Only one recurrence rule is allowed')
            value=take().lower()
            match=re.fullmatch(r'([1-9]\d*)(m|h|d|w|mo)',value)
            if match:
                rule.update(frequency={'m':'minute','h':'hour','d':'day','w':'week','mo':'month'}[match[2]],interval=int(match[1]))
            else:
                names=['mon','tue','wed','thu','fri','sat','sun']
                rule.update(frequency='week',weekdays=sorted(set(names.index(d) for d in value.split(','))))
        elif low == 'count':
            rule['count']=int(take())
        elif low == 'until':
            rule['until']=parse_date(take(),zone,clock).isoformat()
        else:
            title.append(token)
        index += 1
    result['title']=' '.join(title).strip()
    if not result['title']:
        raise ValueError('Title cannot be empty')
    result['tags']=sorted(set(result['tags']))
    if due_text:
        result['due']=parse_date(due_text,zone,clock)
    if daily_count is not None or daily_range is not None:
        if daily_count is None or daily_range is None:
            raise ValueError('Use daily 8x 08:00-22:00 (or daily goal 8 between 08:00-22:00)')
        if rule.get('frequency') != 'day' or rule.get('interval', 1) != 1:
            raise ValueError('A daily reminder window requires daily')
        if result['reminder_specs']:
            raise ValueError('Daily window already schedules reminders; do not combine it with remind')
        if due_text and not (due_text.lower() in ('today', 'tomorrow', *WEEKDAYS) or re.fullmatch(r'\d{4}-\d{2}-\d{2}', due_text)):
            raise ValueError('With a daily window specify a start date without a time, for example tomorrow')
        times = spread_times(daily_count, daily_range)
        result['due'] = window_due(times, result['due'], zone, clock)
        result['reminder_specs'] = [{'local_time': value} for value in times]
    if rule:
        if 'frequency' not in rule:
            raise ValueError('count/until require recurrence')
        result['recurrence']=Rule(**rule).to_dict()
    return result
