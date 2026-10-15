"""Test av porten for planlagte kjøringer, inkludert forsinkelser og sommer- og vintertid. Rene tidspunkter, ingen data."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import should_run as sr


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


# sommertid (CEST, UTC+2): midnatt Oslo = 22:00 UTC. vintertid (CET, UTC+1): midnatt Oslo = 23:00 UTC.
CASES = [
    ("sommer, 22:07 UTC (00:07 Oslo), gårsdagens data", "schedule", "2026-10-14T22:07", "2026-10-14T09:05", True),
    ("sommer, 22:37 UTC, allerede oppdatert 00:08", "schedule", "2026-10-14T22:37", "2026-10-14T22:08", False),
    ("sommer, forsinket til 03:00 UTC, gårsdagens data", "schedule", "2026-10-15T03:00", "2026-10-14T09:05", True),
    ("sommer, forsinket 5t som observert (04:07 til 09:04 UTC), gårsdagens data", "schedule", "2026-10-15T09:04", "2026-10-14T09:05", True),
    ("sommer, oppdatert i går ettermiddag før midnatt Oslo, kjører etter midnatt", "schedule", "2026-10-14T22:07", "2026-10-14T21:30", True),
    ("sommer, oppdatert etter midnatt i dag, hopper over", "schedule", "2026-10-15T04:07", "2026-10-14T22:08", False),
    ("vinter, 22:07 UTC (23:07 Oslo), før midnatt", "schedule", "2026-11-10T22:07", "2026-11-10T00:30", False),
    ("vinter, 23:07 UTC (00:07 Oslo), gårsdagens data", "schedule", "2026-11-10T23:07", "2026-11-10T00:30", True),
    ("omstilling til vintertid 25. okt: 24. okt 22:07 UTC = 00:07 CEST, kjører", "schedule", "2026-10-24T22:07", "2026-10-24T09:00", True),
    ("etter omstilling 25. okt: 22:07 UTC = 23:07 CET, før midnatt", "schedule", "2026-10-25T22:07", "2026-10-25T09:00", False),
    ("etter omstilling 25. okt: 23:07 UTC = 00:07 CET, kjører", "schedule", "2026-10-25T23:07", "2026-10-25T09:00", True),
    ("omstilling til sommertid 28. mars 2027, 22:07 UTC = 00:07 CEST 29. mars", "schedule", "2027-03-28T22:07", "2027-03-28T09:00", True),
    ("manuell kjøring før midnatt i dag teller ikke", "schedule", "2026-10-14T22:07", "2026-10-14T21:00", True),
    ("manuell kjøring etter midnatt i dag teller", "schedule", "2026-10-15T04:07", "2026-10-14T22:30", False),
    ("manuell kjøring kjører alltid, også rett etter forrige", "workflow_dispatch", "2026-10-14T04:30", "2026-10-14T04:29", True),
]


@pytest.mark.parametrize("name,event,now,last,expected", CASES, ids=[c[0] for c in CASES])
def test_decide(name, event, now, last, expected):
    run, why = sr.decide(event, utc(now), utc(last))
    assert run is expected and why


def test_unknown_last_run_runs():
    assert sr.decide("schedule", utc("2026-10-14T22:07"), None)[0] is True


def test_last_run_reads_meta_and_tolerates_bad_files(tmp_path):
    ok = tmp_path / "meta.json"
    ok.write_text('{"run_at": "2026-10-13T10:34:19+00:00"}', encoding="utf-8")
    assert sr.last_run(ok) == utc("2026-10-13T10:34:19")
    assert sr.last_run(tmp_path / "mangler.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("ikke json", encoding="utf-8")
    assert sr.last_run(bad) is None
    nokey = tmp_path / "nokey.json"
    nokey.write_text("{}", encoding="utf-8")
    assert sr.last_run(nokey) is None


def test_exactly_one_update_per_day_with_all_cron_times_and_delays():
    """Simulerer alle planlagte tidspunkt (22:07, 22:37, 23:07, 23:37, 04:07, 06:07 UTC) med og uten forsinkelse, sommer og
    vinter: nøyaktig én kjøring per Oslo-døgn skal oppdatere, og den skal starte etter 00:00 Oslo."""
    from datetime import timedelta

    crons = ("22:07", "22:37", "23:07", "23:37", "04:07", "06:07")
    for first_day, last0 in (("2026-10-14", "2026-10-14T09:05"), ("2026-11-10", "2026-11-10T09:05")):
        for delay in (0, 90, 360):
            last = utc(last0)
            ran = []
            d0 = datetime.fromisoformat(first_day)
            starts = []
            for hhmm in crons:
                day = d0 if hhmm >= "22:00" else d0 + timedelta(days=1)
                starts.append(utc(f"{day:%Y-%m-%d}T{hhmm}") + timedelta(minutes=delay))
            for start in sorted(starts):
                run, _ = sr.decide("schedule", start, last)
                if run:
                    ran.append(start)
                    last = start
            assert len(ran) == 1, (first_day, delay, ran)
            assert ran[0].astimezone(sr.OSLO).date() > d0.date()
