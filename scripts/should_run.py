"""Port for planlagte kjøringer: skal pipelinen kjøre nå? Bare standardbibliotek, så den kan kjøres uten installasjon.

GitHub forsinker planlagte kjøringer, noen ganger med timer. Derfor er regelen ikke «klokken er 06», men:
kjør hvis klokken i Oslo er RUN_HOUR:00 eller senere, og forrige oppdatering skjedde før dagens RUN_HOUR:00 (Oslo).
RUN_HOUR er 0: dagens oppdatering starter ved midnatt, slik at selv med flere timers forsinkelse er siden oppdatert
i løpet av natten eller tidlig morgen. Første kjøring som starter etter midnatt tar dagens oppdatering, uansett hvor sent.
De andre planlagte kjøringene samme dag ser at det allerede er oppdatert og hopper over. Kjøringer som starter før
midnatt i Oslo (22:07 UTC om vinteren) hoppes over. Manuell kjøring kjører alltid."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")
RUN_HOUR = 0


def last_run(meta_path: Path) -> datetime | None:
    try:
        d = datetime.fromisoformat(json.loads(meta_path.read_text(encoding="utf-8"))["run_at"])
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def decide(event: str, now: datetime, last: datetime | None) -> tuple[bool, str]:
    """Returnerer (kjør, begrunnelse). `now` og `last` må ha tidssone."""
    if event != "schedule":
        return True, "Manuell kjøring: kjører alltid."
    now_oslo = now.astimezone(OSLO)
    cutoff = now_oslo.replace(hour=RUN_HOUR, minute=0, second=0, microsecond=0)
    if now_oslo < cutoff:
        return False, f"Klokken er {now_oslo:%H:%M} i Oslo, før {RUN_HOUR:02d}:00: hopper over."
    if last is not None and last.astimezone(OSLO) >= cutoff:
        return False, f"Allerede oppdatert i dag etter {RUN_HOUR:02d}:00 ({last.astimezone(OSLO):%H:%M} Oslo): hopper over."
    return True, f"Klokken er {now_oslo:%H:%M} i Oslo og dagens oppdatering mangler: kjører."


def main() -> None:
    event = os.environ.get("GITHUB_EVENT_NAME", "schedule")
    run, why = decide(event, datetime.now(timezone.utc), last_run(Path("data/meta.json")))
    print(why)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"run={'true' if run else 'false'}\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
