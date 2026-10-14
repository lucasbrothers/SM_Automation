"""Numeric five-field cron expressions with explicit IANA timezone handling."""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
import re


def field(text,low,high):
    result=set()
    for part in text.split(','):
        match=re.fullmatch(r'(\*|\d+(?:-\d+)?)(?:/(\d+))?',part)
        if not match:raise ValueError('Use numbers, *, commas, ranges and /steps in cron fields')
        base,step=match.groups();step=int(step or 1)
        if not 1<=step<=high+1:raise ValueError('Invalid cron step')
        if base=='*':start,end=low,high
        elif '-' in base:start,end=map(int,base.split('-'))
        else:start=int(base);end=high if match.group(2) else start
        if not low<=start<=end<=high:raise ValueError(f'Cron value must be within {low}–{high}')
        result.update(range(start,end+1,step))
    return result


def parse(expression):
    if not isinstance(expression,str) or len(expression)>200 or len(expression.split())!=5:
        raise ValueError('Cron needs five fields: minute hour day month weekday')
    parts=expression.split();limits=[(0,59),(0,23),(1,31),(1,12),(0,7)]
    values=[field(text,*bounds) for text,bounds in zip(parts,limits)]
    values[4]={n%7 for n in values[4]}
    return parts,values


def zone(name):
    if not isinstance(name,str) or not name or len(name)>64:raise ValueError('Enter an IANA timezone')
    if name=='UTC':return timezone.utc
    try:return ZoneInfo(name)
    except (ValueError,ZoneInfoNotFoundError):raise ValueError('Unknown timezone: '+name) from None


def next_run(expression,after,timezone_name='UTC'):
    parts,values=parse(expression);tz=zone(timezone_name)
    if after.tzinfo is None:raise ValueError('Cron requires a timezone-aware start time')
    instant=after.astimezone(timezone.utc);day=instant.astimezone(tz).date()
    for _ in range(366*8+1):
        dom=day.day in values[2];dow=(day.weekday()+1)%7 in values[4]
        day_match=(dom and dow) if parts[2].startswith('*') or parts[4].startswith('*') else (dom or dow)
        if day.month in values[3] and day_match:
            candidates=set()
            for hour in values[1]:
                for minute in values[0]:
                    naive=datetime(day.year,day.month,day.day,hour,minute)
                    for fold in (0,1):
                        candidate=naive.replace(tzinfo=tz,fold=fold).astimezone(timezone.utc)
                        if candidate>instant and candidate.astimezone(tz).replace(tzinfo=None)==naive:candidates.add(candidate)
            if candidates:return min(candidates).astimezone(tz)
        day+=timedelta(days=1)
    raise ValueError('Cron has no matching date within eight years')
