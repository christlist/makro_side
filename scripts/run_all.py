"""Kjør hele pipelinen i riktig rekkefølge: datagrupper, regime, stemning, oppsummering, kjøringsinfo.
Ett steg som feiler stopper ikke de andre. Skriver alltid gyldige JSON-filer, og kode 0 ved avslutning."""
from __future__ import annotations

from . import (build_regime, build_summary, fetch_equities, fetch_macro, fetch_mood, fetch_volatility, finalize)
from .common import get_logger

log = get_logger("run_all")

STEPS = [("volatilitet", fetch_volatility.main), ("kreditt, renter og råvarer", fetch_macro.main),
         ("aksjer og sektorer", fetch_equities.main), ("regime", build_regime.main), ("stemning", fetch_mood.main),
         ("oppsummering", build_summary.main), ("kjøringsinfo", finalize.main)]


def main() -> None:
    failed = []
    for name, fn in STEPS:
        try:
            fn()
        except Exception:  # noqa: BLE001
            log.exception("Steget %s feilet", name)
            failed.append(name)
    log.info("Ferdig. Steg som feilet helt: %s", ", ".join(failed) if failed else "ingen")


if __name__ == "__main__":
    main()
