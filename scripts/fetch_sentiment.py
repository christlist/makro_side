"""Eksperimentell sektorsentiment: GDELT DOC API (titler) + FinBERT på CPU.

Score per artikkel = P(positiv) minus P(negativ). 7 dagers snitt per sektor.
z-score beregnes på tvers av sektorer med nok artikler (relativ sentiment denne uken).
"""
from __future__ import annotations

import time

from .common import SourceError, get_logger, load_config, run_group, zscores, _num
from .sources import http_get

log = get_logger("sentiment")


def gdelt_titles(scfg: dict, keywords: list[str], settings: dict) -> list[str]:
    query = "(" + " OR ".join(keywords) + ") sourcelang:english"
    r = http_get(scfg["gdelt_url"],
                 params={"query": query, "mode": "artlist", "format": "json",
                         "maxrecords": scfg["gdelt_maxrecords"], "timespan": scfg["gdelt_timespan"],
                         "sort": "datedesc"},
                 timeout=settings["http_timeout"], retries=settings["http_retries"])
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
    model_error = None

    for i, (sid, spec) in enumerate(scfg["sectors"].items()):
        if i:
            time.sleep(scfg["request_gap_seconds"])
        try:
            titles_by_sector[sid] = gdelt_titles(scfg, spec["keywords"], settings)
            log.info("GDELT %s: %d unike titler", sid, len(titles_by_sector[sid]))
        except Exception as exc:  # noqa: BLE001
            log.error("GDELT %s feilet: %s", sid, exc)
            rows[sid] = {"id": sid, "name": spec["name"], "status": "missing", "error": str(exc)}

    scorer = None
    if titles_by_sector:
        try:
            scorer = load_finbert(scfg)
        except Exception as exc:  # noqa: BLE001
            model_error = f"{type(exc).__name__}: {exc}"
            log.error("FinBERT kunne ikke lastes: %s", model_error)

    for sid, titles in titles_by_sector.items():
        spec = scfg["sectors"][sid]
        if scorer is None:
            rows[sid] = {"id": sid, "name": spec["name"], "status": "missing",
                         "error": f"Sentimentmodell utilgjengelig: {model_error}", "n_articles": len(titles)}
            continue
        mean = float(sum(scorer(titles)) / len(titles)) if titles else None
        rows[sid] = {"id": sid, "name": spec["name"], "status": "ok", "error": None,
                     "n_articles": len(titles), "mean_score": _num(mean, 4),
                     "hidden": len(titles) < scfg["min_articles"], "z": None}

    shown = [r for r in rows.values() if r["status"] == "ok" and not r["hidden"]]
    for r, z in zip(shown, zscores([r["mean_score"] for r in shown])):
        r["z"] = _num(z, 2)
    return {"indicators": {}, "rows": rows, "min_articles": scfg["min_articles"],
            "timespan": scfg["gdelt_timespan"], "model": scfg["model"], "model_error": model_error,
            "source": "GDELT DOC API (artikkeltitler), FinBERT",
            "z_note": "z-score er relativ: sektorens 7 dagers snitt mot snittet av sektorene med nok artikler denne uken."}


def main() -> None:
    run_group("sentiment", build, log)


if __name__ == "__main__":
    main()
