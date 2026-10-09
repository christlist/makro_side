"""Oppsummering på norsk, regelbasert fra de ferdige JSON-filene. Ingen tall konstrueres:
hver setning er en mal fylt med verdier fra datafilene, og utelates hvis dataene mangler."""
from __future__ import annotations

from typing import Optional

from .common import get_logger, now_iso, read_json, write_json

log = get_logger("summary")

STATE_NB = {"calm": "rolig", "elevated": "forhøyet", "stress": "stress"}
MOOD_NB = {"extreme_fear": "ekstrem frykt", "fear": "frykt", "neutral": "nøytral", "greed": "grådighet",
           "extreme_greed": "ekstrem grådighet"}
HEALTH_GROUPS = ("volatility", "macro")


def nb(x: float, dec: int = 0) -> str:
    return f"{x:.{dec}f}".replace(".", ",")


def signed(x: float, dec: int = 1) -> str:
    return ("+" if x > 0 else "−" if x < 0 else "") + nb(abs(x), dec)


def regime_point(regime: Optional[dict]) -> Optional[dict]:
    if not regime:
        return None
    if regime.get("status") != "ok":
        return {"kind": "regime", "text": "Regimet kan ikke beregnes: Data mangler for for mange indikatorer."}
    greens = sum(1 for i in regime["items"] if i.get("light") == "green")
    n = regime["n_used"]
    return {"kind": "regime",
            "text": f"Regimet er {STATE_NB.get(regime['state'], regime['state'])}. Snittet av stress-persentilene er "
                    f"{nb(regime['mean_stress'])} av 100, og {greens} av {n} indikatorer er grønne."}


def mood_point(mood: Optional[dict]) -> Optional[dict]:
    mk = (mood or {}).get("market") or {}
    if mk.get("status") != "ok":
        return {"kind": "mood", "text": "Stemningsindeksen kan ikke beregnes: Data mangler."}
    ch = mk.get("change_1w")
    move = "" if ch is None else (f", {signed(ch, 0)} poeng siste uke" if ch else ", uendret siste uke")
    text = f"Stemningen er {MOOD_NB.get(mk['label'], mk['label'])} ({nb(mk['score'])} av 100{move})."
    comps = [c for c in mk.get("components", []) if c.get("status") == "ok" and c.get("in_index", True)]
    if len(comps) >= 2:
        hi = max(comps, key=lambda c: c["score"])
        lo = min(comps, key=lambda c: c["score"])
        if hi["score"] - lo["score"] >= 60:
            text += f" Komponentene spriker: {hi['label']} peker mot grådighet, {lo['label']} mot frykt."
    return {"kind": "mood", "text": text}


def unusual(files: dict, low: float = 10.0, high: float = 90.0) -> list[dict]:
    out = []
    for g in HEALTH_GROUPS:
        for k, ind in ((files.get(g) or {}).get("indicators") or {}).items():
            p = ind.get("percentile_10y")
            if ind.get("status") == "ok" and p is not None and (p >= high or p <= low):
                out.append({"id": k, "name": ind["name"], "percentile": p, "value": ind["last_value"],
                            "decimals": ind.get("decimals", 2), "unit": ind.get("unit"),
                            "last_date": ind["last_date"], "direction": "high" if p >= high else "low",
                            "window_years": ind.get("window_years")})
    return sorted(out, key=lambda x: abs(x["percentile"] - 50), reverse=True)


def unusual_point(items: list[dict]) -> dict:
    if not items:
        return {"kind": "unusual", "text": "Ingen av volatilitets- og kredittindikatorene ligger utenfor normalområdet (10. til 90. persentil mot 10 år)."}
    hi = [i for i in items if i["direction"] == "high"]
    lo = [i for i in items if i["direction"] == "low"]
    parts = []
    if hi:
        parts.append("uvanlig høyt: " + ", ".join(f"{i['name']} (persentil {nb(i['percentile'])})" for i in hi))
    if lo:
        parts.append("uvanlig lavt: " + ", ".join(f"{i['name']} (persentil {nb(i['percentile'])})" for i in lo))
    return {"kind": "unusual", "text": "Utenfor normalområdet: " + "; ".join(parts) + "."}


def term_point(vol: Optional[dict]) -> Optional[dict]:
    ind = ((vol or {}).get("indicators") or {}).get("vix_vix3m")
    if ind and ind.get("status") == "ok" and ind.get("inverted"):
        return {"kind": "term", "text": "VIX-termstrukturen er invertert: markedet priser inn mer uro på kort sikt enn lenger frem."}
    return None


def equity_point(eq: Optional[dict]) -> Optional[dict]:
    spx = ((eq or {}).get("indicators") or {}).get("spx")
    if not spx or spx.get("status") != "ok" or spx.get("ret_1m") is None:
        return None
    text = f"S&P 500 har gitt {signed(spx['ret_1m'])} % siste måned"
    if spx.get("dist200") is not None:
        text += f" og ligger {nb(abs(spx['dist200']), 1)} % {'over' if spx['dist200'] >= 0 else 'under'} 200 dagers snitt"
    text += "."
    b = ((eq.get("sectors") or {}).get("breadth"))
    if b:
        text += f" {b['above_200d']} av {b['total']} sektorer ligger over 200 dagers snitt."
    return {"kind": "equities", "text": text}


def health(files: dict, mood: Optional[dict]) -> dict:
    total, ok, missing, dates = 0, 0, [], []
    for g in (*HEALTH_GROUPS, "equities"):
        for k, ind in ((files.get(g) or {}).get("indicators") or {}).items():
            if k.endswith("_dist200"):
                continue
            total += 1
            if ind.get("status") == "ok":
                ok += 1
                dates.append(ind["last_date"])
            else:
                missing.append(ind.get("name", k))
    for c in ((mood or {}).get("market") or {}).get("components", []):
        if not c.get("in_index", True):
            continue  # eksperimentelle komponenter teller ikke i datahelsen før de er med i indeksen
        total += 1
        if c.get("status") == "ok":
            ok += 1
            dates.append(c["last_date"])
        else:
            missing.append(c["label"])
    proxies = [ind["name"] for g in (*HEALTH_GROUPS, "equities")
               for k, ind in ((files.get(g) or {}).get("indicators") or {}).items()
               if ind.get("status") == "ok" and ind.get("proxy") and not k.endswith("_dist200")]
    return {"n_total": total, "n_ok": ok, "missing": missing, "proxies": proxies,
            "latest_data_date": max(dates) if dates else None, "oldest_data_date": min(dates) if dates else None}


def compute(files: dict) -> dict:
    points = [p for p in (regime_point(files.get("regime")), mood_point(files.get("mood")),
                          unusual_point(unusual(files)), term_point(files.get("volatility")),
                          equity_point(files.get("equities"))) if p]
    reg = files.get("regime") or {}
    mk = (files.get("mood") or {}).get("market") or {}
    return {"generated_at": now_iso(), "points": points, "unusual": unusual(files),
            "regime": {"state": reg.get("state"), "mean_stress": reg.get("mean_stress"), "status": reg.get("status")},
            "mood": {"score": mk.get("score"), "label": mk.get("label"), "change_1w": mk.get("change_1w"),
                     "status": mk.get("status")},
            "health": health(files, files.get("mood"))}


def main() -> None:
    files = {n: read_json(n) for n in ("regime", "volatility", "macro", "equities", "mood")}
    s = compute(files)
    write_json("summary", s)
    log.info("Oppsummering: %d punkter, %d av %d indikatorer ok", len(s["points"]), s["health"]["n_ok"], s["health"]["n_total"])


if __name__ == "__main__":
    main()
