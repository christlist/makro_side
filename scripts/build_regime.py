"""Regimestatus: snitt av stress-persentiler fra volatilitet, kreditt, dollar og aksjer."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from .common import DATA_DIR, get_logger, load_config, now_iso, read_json, write_json, _num

log = get_logger("regime")


def light(stress_pct: float, rcfg: dict) -> str:
    if stress_pct >= rcfg["light"]["red_from"]:
        return "red"
    if stress_pct >= rcfg["light"]["yellow_from"]:
        return "yellow"
    return "green"


def overall(mean_stress: float, rcfg: dict) -> str:
    if mean_stress >= rcfg["overall"]["stress_from"]:
        return "stress"
    if mean_stress >= rcfg["overall"]["elevated_from"]:
        return "elevated"
    return "calm"


def compute(cfg: dict, files: dict, today: Optional[pd.Timestamp] = None) -> dict:
    rcfg = cfg["regime"]
    today = today if today is not None else pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    items, used = [], []
    for inp in rcfg["inputs"]:
        base = {"id": inp["id"], "file": inp["file"], "label": inp["label"], "direction": inp["direction"]}
        f = files.get(inp["file"])
        ind = (f or {}).get("indicators", {}).get(inp["id"])
        if f is None:
            items.append({**base, "status": "missing", "reason": f"Filen {inp['file']}.json mangler"})
            continue
        if ind is None or ind.get("status") != "ok":
            items.append({**base, "status": "missing", "reason": (ind or {}).get("error") or "Indikator mangler"})
            continue
        age = (today - pd.Timestamp(ind["last_date"])).days
        if ind.get("percentile_10y") is None:
            items.append({**base, "status": "missing", "last_date": ind["last_date"],
                          "reason": "For kort historikk til persentilrang"})
            continue
        if age > rcfg["max_age_days"]:
            items.append({**base, "status": "missing", "last_date": ind["last_date"],
                          "reason": f"Data for gamle ({age} dager, siste punkt {ind['last_date']})"})
            continue
        pct = ind["percentile_10y"]
        stress = pct if inp["direction"] == "higher_is_stress" else 100.0 - pct
        row = {**base, "status": "ok", "value": ind["last_value"], "decimals": ind["decimals"], "unit": ind["unit"],
               "last_date": ind["last_date"], "stale": ind.get("stale", False),
               "percentile_10y": pct, "stress_percentile": _num(stress, 1),
               "change_1w": ind.get("change_1w"), "change_kind": ind.get("change_kind"),
               "window_years": ind.get("window_years"), "light": light(stress, rcfg)}
        items.append(row)
        used.append(row)

    result = {"generated_at": now_iso(), "items": items, "n_used": len(used), "n_total": len(items),
              "rule": {"min_indicators": rcfg["min_indicators"], "light": rcfg["light"],
                       "overall": rcfg["overall"], "max_age_days": rcfg["max_age_days"]}}
    if len(used) < rcfg["min_indicators"]:
        result.update({"status": "missing", "state": None, "mean_stress": None,
                       "error": f"Data mangler: {len(used)} av {len(items)} indikatorer tilgjengelig, "
                                f"minst {rcfg['min_indicators']} kreves."})
    else:
        mean = sum(r["stress_percentile"] for r in used) / len(used)
        result.update({"status": "ok", "state": overall(mean, rcfg), "mean_stress": _num(mean, 1), "error": None})
    return result


def main() -> None:
    cfg = load_config()
    files = {n: read_json(n) for n in {i["file"] for i in cfg["regime"]["inputs"]}}
    result = compute(cfg, files)
    write_json("regime", result)
    log.info("Regime: %s (snitt %s, %d/%d indikatorer)", result["state"], result["mean_stress"],
             result["n_used"], result["n_total"])


if __name__ == "__main__":
    main()
