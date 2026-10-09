"""Volatilitet og opsjonsmarked: VIX, VIX3M, VIX/VIX3M, VVIX, SKEW, VSTOXX."""
from __future__ import annotations

from .common import build_indicator, clean_series, get_logger, load_config, missing_indicator, run_group
from .sources import build_series_group, candidate_label, fetch_first

log = get_logger("volatility")


def vstoxx_proxy(vcfg: dict, settings: dict, original_error: str) -> dict:
    """Realisert 21d volatilitet i Euro STOXX 50 som merket proxy når V2TX mangler.
    Feiler også proxyen, beholdes «Data mangler» med begge feilmeldingene."""
    spec = vcfg["vstoxx_proxy"]
    try:
        s, cand = fetch_first(spec["candidates"], settings)
        s = clean_series(s)
        rv = (s.pct_change().rolling(21).std() * (252 ** 0.5) * 100.0).dropna()
        ind = build_indicator(spec, "vstoxx", "volatility", rv, settings,
                              source=f"Proxy: realisert vol 21d, {candidate_label(cand)}", proxy=True)
        ind["proxy_reason"] = f"VSTOXX (V2TX) utilgjengelig: {original_error[:200]}"
        return ind
    except Exception as exc:  # noqa: BLE001
        log.error("VSTOXX-proxy mangler: %s", exc)
        return missing_indicator(vcfg["series"]["vstoxx"], "vstoxx", "volatility",
                                 f"{original_error} | Proxy: {exc}")


def build() -> dict:
    cfg = load_config()
    settings = cfg["settings"]
    vcfg = cfg["volatility"]
    indicators, raw = build_series_group(vcfg["series"], "volatility", settings)

    spec = vcfg["derived"]["vix_vix3m"]
    if "vix" in raw and "vix3m" in raw:
        ratio = (raw["vix"] / raw["vix3m"]).dropna()
        try:
            src = f"Beregnet: {indicators['vix']['source']} / {indicators['vix3m']['source']}"
            ind = build_indicator(spec, "vix_vix3m", "volatility", ratio, settings, source=src)
            thr = spec["inversion_threshold"]
            ind["inversion_threshold"] = thr
            ind["inverted"] = bool(ind["last_value"] > thr)
            indicators["vix_vix3m"] = ind
        except Exception as exc:  # noqa: BLE001
            indicators["vix_vix3m"] = missing_indicator(spec, "vix_vix3m", "volatility", str(exc))
    else:
        absent = [k for k in ("vix", "vix3m") if k not in raw]
        indicators["vix_vix3m"] = missing_indicator(
            spec, "vix_vix3m", "volatility", "Mangler grunnserie: " + ", ".join(absent))
    if indicators["vstoxx"]["status"] != "ok":
        indicators["vstoxx"] = vstoxx_proxy(vcfg, settings, indicators["vstoxx"]["error"])
    return {"indicators": indicators}


def main() -> None:
    run_group("volatility", build, log)


if __name__ == "__main__":
    main()
