"""Midlertidig diagnostikk: hva leverer NAAIM og mulige V2TX-kilder til GitHub-runnerne? Bare lesing, skriver til stdout."""
from __future__ import annotations

import re

import requests

UA = {"User-Agent": "Mozilla/5.0 (makro_side probe)"}


def get(url, **kw):
    try:
        return requests.get(url, headers=UA, timeout=30, **kw)
    except Exception as exc:  # noqa: BLE001
        print(f"  FEIL {url}: {type(exc).__name__}: {str(exc)[:150]}")
        return None


def naaim():
    print("=== NAAIM ===")
    url = "https://naaim.org/programs/naaim-exposure-index/"
    r = get(url)
    if r is None:
        return
    h = r.text
    print("status", r.status_code, "endelig url", r.url, "lengde", len(h), "type", r.headers.get("content-type"))
    print("antall <table:", len(re.findall("<table", h, flags=re.I)), "| wp-json:", h.count("wp-json"), "| admin-ajax:", h.count("admin-ajax"),
          "| chart:", len(re.findall("chart", h, flags=re.I)), "| csv:", len(re.findall("csv", h, flags=re.I)), "| download:", len(re.findall("download", h, flags=re.I)))
    anchors = re.findall(r"""<a\s[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>""", h, flags=re.I | re.S)
    keep = [(a, re.sub(r"<[^>]+>|\s+", " ", t).strip()[:50]) for a, t in anchors
            if re.search(r"download|data|xls|csv|histor|inception|upload|zip|pdf", a + t, flags=re.I)]
    print("lenker med data-ord:", len(keep))
    for a, t in keep[:40]:
        print("  ", a[:140], "|", t)
    print("uploads-url-er:", sorted(set(re.findall(r"""https?://[^\s"'<>]*wp-content/uploads/[^\s"'<>]+""", h)))[:30])
    print("skript:", re.findall(r"""<script[^>]+src=["']([^"']+)["']""", h)[:25])
    for m in list(re.finditer(r"download|histor|inception", h, flags=re.I))[:8]:
        s = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h[max(0, m.start() - 120):m.end() + 160]))
        print("  ...", s.strip()[:260])
    tbl = re.search(r"<table.*?</table>", h, flags=re.I | re.S)
    if tbl:
        print("første tabell (tekst):", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", tbl.group(0)))[:500])
    # Vanlige datafilsti-gjetninger (HEAD)
    for g in ["https://naaim.org/wp-json/wp/v2/pages?slug=naaim-exposure-index", "https://naaim.org/naaim-exposure-index.csv"]:
        rr = get(g)
        if rr is not None:
            print("gjetning", g, rr.status_code, rr.headers.get("content-type"), rr.text[:150].replace("\n", " "))


def v2tx():
    print("=== V2TX ===")
    for sym in ["^V2TX", "^VSTOXX", "V2TX.DE", "V2TX.F", "^V2X", "VSTOXX.FGI"]:
        try:
            import yfinance as yf

            df = yf.Ticker(sym).history(period="10d")
            print(f"  yfinance {sym}: {len(df)} rader", (str(df.index[-1].date()) + " " + str(round(float(df['Close'].iloc[-1]), 2))) if len(df) else "")
        except Exception as exc:  # noqa: BLE001
            print(f"  yfinance {sym}: FEIL {type(exc).__name__}")
    for u in ["https://www.stoxx.com/document/Indices/Current/HistoricalData/h_v2tx.txt",
              "https://www.stoxx.com/document/Indices/Current/HistoricalData/hV2TX.txt",
              "https://www.stoxx.com/document/Indices/Current/HistoricalData/v2tx.txt",
              "https://www.stoxx.com/index-details?symbol=V2TX",
              "https://stooq.com/q/d/l/?s=v2tx.f&i=d",
              "https://query1.finance.yahoo.com/v8/finance/chart/%5EV2TX?range=5d&interval=1d"]:
        r = get(u)
        if r is not None:
            print(f"  {r.status_code} {u} | {r.headers.get('content-type')} | {len(r.text)} tegn | {r.text[:160]!r}")


if __name__ == "__main__":
    naaim()
    v2tx()
