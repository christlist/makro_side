"""Verifiser alle kandidatkilder i config.yaml. Skriver en tabell (OK/FEIL, siste dato) til stdout.
Kjøres lokalt eller som første steg i workflowen. Avslutter alltid med kode 0."""
from __future__ import annotations

from .common import load_config
from .sources import candidate_label, fetch_candidate


def candidates(cfg: dict):
    for grp in ("volatility", "macro"):
        for k, spec in cfg[grp]["series"].items():
            for c in spec["candidates"]:
                yield f"{grp}.{k}", c
    for k, spec in cfg["equities"]["indices"].items():
        for c in spec["candidates"]:
            yield f"equities.{k}", c
    for c in cfg["equities"]["benchmark"]["candidates"]:
        yield "equities.benchmark", c
    for k, spec in cfg["equities"]["sectors"].items():
        yield f"sectors.{k}", {"source": "yfinance", "symbol": spec["symbol"]}
    for c in cfg["mood"]["bond_candidates"]:
        yield "mood.bond", c


def main() -> None:
    cfg = load_config()
    print("| Indikator | Kilde | Status | Siste dato | Obs |\n|---|---|---|---|---|")
    for ind, c in candidates(cfg):
        try:
            s = fetch_candidate(c, cfg["settings"])
            print(f"| {ind} | {candidate_label(c)} | OK | {s.index[-1].date()} | {len(s)} |")
        except Exception as exc:  # noqa: BLE001
            print(f"| {ind} | {candidate_label(c)} | FEIL | {str(exc)[:80]} | |")


if __name__ == "__main__":
    main()
