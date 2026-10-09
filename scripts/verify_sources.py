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


def verify_news(cfg: dict) -> None:
    from .fetch_sentiment import yf_titles

    print("\n| Sektor | Kilde | Status | Råelementer | Med tittel | Med dato | Nye nok | Tickere uten feil | Feltnavn (første element) |\n|---|---|---|---|---|---|---|---|---|")
    scfg = cfg["sentiment"]
    for sid, spec in scfg["sectors"].items():
        try:
            titles, errs, st = yf_titles(spec["tickers"], scfg)
            print(f"| {sid} | yfinance news | OK | {st['raw_items']} | {st['with_title']} | {st['with_date']} | {st['kept']} | "
                  f"{len(spec['tickers']) - len(errs)}/{len(spec['tickers'])} | {', '.join(st['sample_keys'])[:120]} |")
        except Exception as exc:  # noqa: BLE001
            print(f"| {sid} | yfinance news | FEIL | {str(exc)[:80]} | |")


def main() -> None:
    cfg = load_config()
    print("| Indikator | Kilde | Status | Siste dato | Obs |\n|---|---|---|---|---|")
    for ind, c in candidates(cfg):
        try:
            s = fetch_candidate(c, cfg["settings"])
            print(f"| {ind} | {candidate_label(c)} | OK | {s.index[-1].date()} | {len(s)} |")
        except Exception as exc:  # noqa: BLE001
            print(f"| {ind} | {candidate_label(c)} | FEIL | {str(exc)[:80]} | |")
    try:
        verify_news(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"\nNyhetssjekk feilet: {exc}")


if __name__ == "__main__":
    main()
