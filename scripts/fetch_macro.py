"""Kreditt, renter, dollar og råvarer fra FRED."""
from __future__ import annotations

from .common import get_logger, load_config, run_group
from .sources import build_series_group

log = get_logger("macro")


def build() -> dict:
    cfg = load_config()
    indicators, _ = build_series_group(cfg["macro"]["series"], "macro", cfg["settings"])
    return {"indicators": indicators}


def main() -> None:
    run_group("macro", build, log)


if __name__ == "__main__":
    main()
