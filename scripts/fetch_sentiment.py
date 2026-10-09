"""Eksperimentell sektorsentiment: yfinance-nyheter per aksje (primær), GDELT (supplement), FinBERT på CPU.

Sektortilordning: nyheter hentes for de største beholdningene i hver sektor-ETF (tickers i config.yaml).
Score per artikkel = P(positiv) minus P(negativ) på tittelen. 7 dagers snitt per sektor.
z-score beregnes på tvers av sektorer med nok artikler (relativ sentiment denne uken).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from .common import SourceError, get_logger, load_config, run_group, zscores, _num
from .sources import http_get

log = get_logger("sentiment")


def parse_news_item(item: dict) -> tuple[Optional[str], Optional[datetime]]:
    """Støtter både nytt (content.title/pubDate) og eldre (title/providerPublishTime) yfinance-skjema.
    Returnerer (tittel, UTC-tidspunkt). Mangler tittel eller tidspunkt gir det None."""
    content = item.get("content") if isinstance(item.get("content"), dict) else None
    title = (content or {}).get("title") or item.get("title")
    ts = None
    raw = (content or {}).get("pubDate") or (content or {}).get("displayTime")
    if raw:
        try:
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            ts = None
    elif item.get("providerPublishTime") is not None:
        try:
            ts = datetime.fromtimestamp(float(item["providerPublishTime"]), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            ts = None
    if ts is not None and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    title = " ".join(str(title).split()) if title else None
    return title, ts


def select_titles(items: list[dict], days: int, now: datetime) -> list[str]:
    """Titler publisert de siste `days` dagene. Artikler uten gyldig tidspunkt droppes."""
    cutoff = now - timedelta(days=days)
    out = []
    for it in items or []:
        title, ts = parse_news_item(it)
        if title and ts and ts >= cutoff:
            out.append(title)
    return out


def yf_titles(tickers: list[str], scfg: dict) -> tuple[list[str], list[str]]:
    """Hent nyhetstitler for tickerne. Returnerer (unike titler, feilmeldinger per ticker).
    Kaster SourceError hvis alle tickere feilet med unntak."""
    import yfinance as yf  # importeres her slik at modulen kan testes uten yfinance

    now = datetime.now(timezone.utc)
    seen, titles, errors = set(), [], []
    for i, t in enumerate(tickers):
        if i:
            time.sleep(scfg["news_ticker_gap_seconds"])
        try:
            items = yf.Ticker(t).news
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{t}: {type(exc).__name__}: {exc}")
            log.error("yfinance news %s feilet: %s", t, exc)
            continue
        for title in select_titles(items, scfg["news_days"], now):
            if title.lower() not in seen:
                seen.add(title.lower())
                titles.append(title)
    if len(errors) == len(tickers) and tickers:
        raise SourceError("yfinance news feilet for alle tickere: " + " | ".join(errors[:3]))
    return titles, errors


def gdelt_titles(scfg: dict, keywords: list[str], settings: dict) -> list[str]:
    query = "(" + " OR ".join(keywords) + ") sourcelang:english"
    params = {"query": query, "mode": "artlist", "format": "json",
              "maxrecords": scfg["gdelt_maxrecords"], "timespan": scfg["gdelt_timespan"],
              "sort": "datedesc"}
    # GDELT svarer 429 ved for tett trafikk: vent lenge og prøv igjen, ett kall per forsøk
    waits = scfg.get("rate_limit_waits", [30, 60, 90])
    for attempt in range(len(waits) + 1):
        try:
            r = http_get(scfg["gdelt_url"], params=params, timeout=settings["http_timeout"], retries=1)
            break
        except SourceError as exc:
            if "429" not in str(exc) or attempt == len(waits):
                raise
            log.warning("GDELT 429, venter %d s før nytt forsøk", waits[attempt])
            time.sleep(waits[attempt])
    try:
        data = r.json()
    except ValueError as exc:
        raise SourceError(f"GDELT ga ikke JSON: {r.text[:120]!r}") from exc
    seen, titles = set(), []
    for a in data.get("articles", []) or []:
        t = " ".join(str(a.get("title", "")).split())
        if t and t.lower() not in seen:
            seen.add(t.lower())
            titles.append(t)
    return titles


def load_finbert(scfg: dict):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer  # tung import
    import torch

    tok = AutoTokenizer.from_pretrained(scfg["model"])
    model = AutoModelForSequenceClassification.from_pretrained(scfg["model"]).eval()
    labels = {int(i): l.lower() for i, l in model.config.id2label.items()}

    def score(texts: list[str]) -> list[float]:
        out: list[float] = []
        for i in range(0, len(texts), 32):
            batch = texts[i:i + 32]
            enc = tok(batch, padding=True, truncation=True, max_length=scfg["max_tokens"], return_tensors="pt")
            with torch.no_grad():
                probs = torch.softmax(model(**enc).logits, dim=-1)
            pos = next(i for i, l in labels.items() if l == "positive")
            neg = next(i for i, l in labels.items() if l == "negative")
            out.extend((probs[:, pos] - probs[:, neg]).tolist())
        return out

    return score


def build() -> dict:
    cfg = load_config()
    settings, scfg = cfg["settings"], cfg["sentiment"]
    rows: dict = {}
    titles_by_sector: dict[str, list[str]] = {}
    counts: dict[str, dict] = {}
    model_error = None

    for sid, spec in scfg["sectors"].items():
        errs: list[str] = []
        titles: list[str] = []
        counts[sid] = {"yfinance": 0, "gdelt": 0}
        try:
            titles, _ = yf_titles(spec["tickers"], scfg)
            counts[sid]["yfinance"] = len(titles)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"yfinance: {exc}")
            log.error("Nyheter %s feilet: %s", sid, exc)
        if scfg.get("gdelt_supplement") and len(titles) < scfg["min_articles"]:
            try:
                time.sleep(scfg["request_gap_seconds"])
                seen = {t.lower() for t in titles}
                extra = [t for t in gdelt_titles(scfg, spec["keywords"], settings) if t.lower() not in seen]
                titles += extra
                counts[sid]["gdelt"] = len(extra)
            except Exception as exc:  # noqa: BLE001
                errs.append(f"GDELT: {exc}")
                log.error("GDELT %s feilet: %s", sid, exc)
        if errs and not titles:
            rows[sid] = {"id": sid, "name": spec["name"], "status": "missing", "error": " | ".join(errs)}
        else:
            titles_by_sector[sid] = titles

    scorer = None
    if any(titles_by_sector.values()):
        try:
            scorer = load_finbert(scfg)
        except Exception as exc:  # noqa: BLE001
            model_error = f"{type(exc).__name__}: {exc}"
            log.error("FinBERT kunne ikke lastes: %s", model_error)

    for sid, titles in titles_by_sector.items():
        spec = scfg["sectors"][sid]
        if titles and scorer is None:
            rows[sid] = {"id": sid, "name": spec["name"], "status": "missing",
                         "error": f"Sentimentmodell utilgjengelig: {model_error}", "n_articles": len(titles)}
            continue
        mean = float(sum(scorer(titles)) / len(titles)) if titles else None
        rows[sid] = {"id": sid, "name": spec["name"], "status": "ok", "error": None,
                     "n_articles": len(titles), "n_by_source": counts[sid],
                     "mean_score": _num(mean, 4),
                     "hidden": len(titles) < scfg["min_articles"], "z": None}

    shown = [r for r in rows.values() if r["status"] == "ok" and not r["hidden"]]
    for r, z in zip(shown, zscores([r["mean_score"] for r in shown])):
        r["z"] = _num(z, 2)
    return {"indicators": {}, "rows": rows, "min_articles": scfg["min_articles"],
            "timespan": f"{scfg['news_days']}d", "model": scfg["model"], "model_error": model_error,
            "source": "yfinance-nyheter for de største aksjene i hver sektor-ETF (GDELT som supplement), FinBERT",
            "z_note": "z-score er relativ: sektorens 7 dagers snitt mot snittet av sektorene med nok artikler denne uken."}


def main() -> None:
    run_group("sentiment", build, log)


if __name__ == "__main__":
    main()
