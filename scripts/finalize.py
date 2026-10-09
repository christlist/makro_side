"""Samler kjøringsinfo i data/meta.json (tidspunkt, hvilke indikatorer og kilder som mangler)."""
from __future__ import annotations

from .common import get_logger, now_iso, read_json, write_json

log = get_logger("finalize")
GROUPS = ["volatility", "macro", "equities", "mood", "regime"]


def main() -> None:
    missing, groups = [], {}
    for g in GROUPS:
        d = read_json(g)
        if d is None:
            groups[g] = {"generated_at": None, "ok": False}
            missing.append({"group": g, "id": "*", "error": "Filen mangler eller er ugyldig"})
            continue
        groups[g] = {"generated_at": d.get("generated_at"), "ok": not d.get("group_error")}
        for k, v in d.get("indicators", {}).items():
            if v.get("status") != "ok":
                missing.append({"group": g, "id": k, "error": v.get("error")})
        for k, v in (d.get("sectors", {}).get("rows") or {}).items():
            if v.get("status") != "ok":
                missing.append({"group": "sectors", "id": k, "error": v.get("error")})
        for k, v in (d.get("rows") or {}).items():
            if v.get("status") != "ok":
                missing.append({"group": g, "id": k, "error": v.get("error")})
        if d.get("group_error"):
            missing.append({"group": g, "id": "*", "error": d["group_error"]})
    write_json("meta", {"run_at": now_iso(), "groups": groups, "missing": missing})
    log.info("Mangler totalt: %d", len(missing))


if __name__ == "__main__":
    main()
