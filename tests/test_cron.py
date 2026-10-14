from datetime import datetime,timezone
import pytest
from server.cron import parse,next_run

@pytest.mark.parametrize('value',['','* * * *','60 * * * *','* 24 * * *','* * 0 * *','* * * 13 *','* * * * 8','*/0 * * * *','1,,2 * * * *','* * * * MON','9-2 * * * *'])
def test_bad_cron_rejected(value):
    with pytest.raises(ValueError):parse(value)

@pytest.mark.parametrize('cron,start,expected',[
 ('*/15 * * * *','2026-10-14T00:00:00+00:00','2026-10-14T00:15:00+00:00'),
 ('5,35 9-17/2 * * *','2026-10-14T09:06:00+00:00','2026-10-14T09:35:00+00:00'),
 ('0 9 * * 1-5','2026-10-16T10:00:00+00:00','2026-10-19T09:00:00+00:00'),
 ('0 0 1 * 1','2026-10-14T00:00:00+00:00','2026-10-19T00:00:00+00:00'),
 ('0 0 * * 7','2026-10-14T00:00:00+00:00','2026-10-18T00:00:00+00:00'),
 ('0 0 29 2 *','2026-10-14T00:00:00+00:00','2028-02-29T00:00:00+00:00')])
def test_next_cron(cron,start,expected):
    assert next_run(cron,datetime.fromisoformat(start),'UTC').isoformat()==expected


def test_impossible_date_and_unknown_zone_rejected():
    with pytest.raises(ValueError,match='matching date'):next_run('0 0 31 2 *',datetime(2026,1,1,tzinfo=timezone.utc))
    with pytest.raises(ValueError,match='timezone'):next_run('* * * * *',datetime.now(timezone.utc),'Invalid/Zone')


def test_timezone_and_dst():
    from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
    try:ZoneInfo('America/New_York')
    except ZoneInfoNotFoundError:pytest.skip('IANA timezone data required')
    assert next_run('0 9 * * *',datetime(2026,10,14,tzinfo=timezone.utc),'Asia/Seoul').isoformat()=='2026-10-15T09:00:00+09:00'
    # Missing 02:30 in spring is skipped; repeated 01:30 in fall runs twice.
    assert next_run('30 2 * * *',datetime.fromisoformat('2026-03-08T05:00:00+00:00'),'America/New_York').day==9
    assert next_run('30 1 * * *',datetime.fromisoformat('2026-11-01T05:30:00+00:00'),'America/New_York').astimezone(timezone.utc).hour==6
