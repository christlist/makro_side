"""Midlertidig diagnostikk, runde 2: frie alternativer til NAAIM (posisjonering og opsjonsstemning). Bare lesing."""
from __future__ import annotations

import requests

UA = {"User-Agent": "Mozilla/5.0 (makro_side probe)"}


def get(url, **kw):
    try:
        return requests.get(url, headers=UA, timeout=30, **kw)
    except Exception as exc:  # noqa: BLE001
        print(f"  FEIL {url}: {type(exc).__name__}: {str(exc)[:120]}")
        return None


def cftc():
    print("=== CFTC ===")
    for ds, name in (("6dca-aqww", "legacy"), ("gpe5-46if", "tff")):
        for code in ("13874A", "209742", "239742", "1170E1"):
            r = get(f"https://publicreporting.cftc.gov/resource/{ds}.json",
                    params={"$where": f"cftc_contract_market_code='{code}'", "$order": "report_date_as_yyyy_mm_dd DESC", "$limit": 600})
            if r is None:
                continue
            try:
                rows = r.json()
            except ValueError:
                print(f"  {name} {code}: ikke JSON {r.text[:100]!r}")
                continue
            if not isinstance(rows, list) or not rows:
                print(f"  {name} {code}: {r.status_code} ingen rader {str(rows)[:100]}")
                continue
            f = rows[0]
            keys = [k for k in f if "noncomm_positions_long_all" == k or "noncomm_positions_short_all" == k or k.startswith("lev_money_positions") or k == "open_interest_all"]
            print(f"  {name} {code}: {len(rows)} rader, siste {f.get('report_date_as_yyyy_mm_dd', '')[:10]}, eldste {rows[-1].get('report_date_as_yyyy_mm_dd', '')[:10]}, "
                  f"{f.get('market_and_exchange_names')} | {[(k, f[k]) for k in keys][:6]}")


def cboe_pcr():
    print("=== CBOE put/call ===")
    base = "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/"
    for name in ("totalpc.csv", "equitypc.csv", "indexpc.csv", "vixpc.csv", "spxpc.csv"):
        r = get(base + name)
        if r is None:
            continue
        lines = r.text.splitlines()
        print(f"  {name}: {r.status_code} {len(lines)} linjer | første: {lines[:3]} | siste: {lines[-2:]}")


def yahoo_vol():
    print("=== Yahoo volatilitetsindekser ===")
    import yfinance as yf

    for sym in ["^VDAX", "^VXN", "^RVX", "^VXEEM", "^GVZ", "^OVX", "^VIX9D", "^VIX6M", "^V1X", "^VHSI", "^VKOSPI"]:
        try:
            df = yf.Ticker(sym).history(period="10d")
            print(f"  {sym}: {len(df)} rader", (str(df.index[-1].date()) + " " + str(round(float(df['Close'].iloc[-1]), 2))) if len(df) else "")
        except Exception as exc:  # noqa: BLE001
            print(f"  {sym}: FEIL {type(exc).__name__}")


if __name__ == "__main__":
    cftc()
    cboe_pcr()
    yahoo_vol()
