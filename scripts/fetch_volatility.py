"""Volatilitet og opsjonsmarked: VIX, VIX3M, VIX/VIX3M, VVIX, SKEW, VSTOXX."""
from __future__ import annotations

from .common import build_indicator, get_logger, load_config, missing_indicator, run_group
from .sources import build_series_group

log = get_logger("volatility")


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
    return {"indicators": indicators}


def main() -> None:
    run_group("volatility", build, log)


if __name__ == "__main__":
    main()
