"""Test av porten for planlagte kjøringer, inkludert forsinkelser og sommer- og vintertid. Rene tidspunkter, ingen data."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import should_run as sr


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


# sommertid (CEST, UTC+2): 06:00 Oslo = 04:00 UTC. vintertid (CET, UTC+1): 06:00 Oslo = 05:00 UTC.
CASES = [
    ("sommer, 04:07 UTC (06:07 Oslo), gårsdagens data", "schedule", "2026-10-14T04:07", "2026-10-13T10:34", True),
    ("sommer, 05:07 UTC, allerede oppdatert 06:08", "schedule", "2026-10-14T05:07", "2026-10-14T04:08", False),
    ("sommer, 03:30 UTC (05:30 Oslo), for tidlig", "schedule", "2026-10-14T03:30", "2026-10-13T10:34", False),
    ("sommer, forsinket til 10:00 UTC, gårsdagens data", "schedule", "2026-10-14T10:00", "2026-10-13T10:34", True),
    ("sommer, forsinket 5t51m som observert, gårsdagens data", "schedule", "2026-10-10T11:14", "2026-10-09T13:02", True),
    ("vinter, 04:07 UTC (05:07 Oslo), for tidlig", "schedule", "2026-11-10T04:07", "2026-11-09T05:08", False),
    ("vinter, 05:07 UTC (06:07 Oslo), gårsdagens data", "schedule", "2026-11-10T05:07", "2026-11-09T05:08", True),
    ("omstilling til vintertid 25. okt, 04:07 UTC = 05:07 CET", "schedule", "2026-10-25T04:07", "2026-10-24T04:08", False),
    ("omstilling til vintertid 25. okt, 05:07 UTC = 06:07 CET", "schedule", "2026-10-25T05:07", "2026-10-24T04:08", True),
    ("omstilling til sommertid 28. mars 2027, 04:07 UTC = 06:07 CEST", "schedule", "2027-03-28T04:07", "2027-03-27T05:08", True),
    ("manuell oppdatering kl. 03:00 Oslo i dag teller ikke som dagens 06-oppdatering", "schedule", "2026-10-14T04:07", "2026-10-14T01:00", True),
    ("manuell oppdatering etter 06 i dag teller", "schedule", "2026-10-14T09:00", "2026-10-14T06:30", False),
    ("manuell kjøring kjører alltid, også rett etter forrige", "workflow_dispatch", "2026-10-14T04:30", "2026-10-14T04:29", True),
    ("manuell kjøring kjører alltid, også før 06", "workflow_dispatch", "2026-10-14T01:00", "2026-10-14T00:30", True),
]


@pytest.mark.parametrize("name,event,now,last,expected", CASES, ids=[c[0] for c in CASES])
def test_decide(name, event, now, last, expected):
    run, why = sr.decide(event, utc(now), utc(last))
    assert run is expected and why


def test_unknown_last_run_runs_after_six():
    assert sr.decide("schedule", utc("2026-10-14T04:07"), None)[0] is True
    assert sr.decide("schedule", utc("2026-10-14T03:00"), None)[0] is False


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
    """Simulerer alle planlagte tidspunkt (04:07, 04:37, 05:07, 05:37, 06:07 UTC) med og uten forsinkelse, sommer og vinter:
    nøyaktig én av dem skal kjøre, og det skal være den første som starter etter 06:00 Oslo."""
    from datetime import timedelta

    for day, delays in (("2026-10-14", (0, 90, 360)), ("2026-11-10", (0, 90, 360))):
        for delay in delays:
            last = utc("2026-10-13T10:34" if day == "2026-10-14" else "2026-11-09T05:08")
            ran = []
            for hhmm in ("04:07", "04:37", "05:07", "05:37", "06:07"):
                start = utc(f"{day}T{hhmm}") + timedelta(minutes=delay)
                run, _ = sr.decide("schedule", start, last)
                if run:
                    ran.append(start)
                    last = start  # pipelinen skriver meta.json ved start av kjøringen (konservativt)
            assert len(ran) == 1, (day, delay, ran)
            assert ran[0].astimezone(sr.OSLO).hour >= 6
