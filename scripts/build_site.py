"""Bygg site/ = docs/ + data/*.json. Brukes lokalt og i workflowen før deploy.

CSS og JS får innholdsbasert versjon i URL-en (?v=hash). GitHub Pages lar nettleseren mellomlagre filer i
noen minutter, og uten versjon kan en ny index.html kjøre mot gammel CSS og JS. Med hash i URL-en hentes
filen på nytt akkurat når innholdet er endret."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .common import DATA_DIR, ROOT

VERSIONED = ["style.css", "render.js", "app.js", "vendor/plotly-basic.min.js"]


def version_assets(site: Path) -> dict[str, str]:
    """Legg ?v=<hash> på referanser til VERSIONED i index.html. Returnerer {fil: hash}."""
    index = site / "index.html"
    html = index.read_text(encoding="utf-8")
    versions: dict[str, str] = {}
    for rel in VERSIONED:
        f = site / rel
        if not f.exists():
            continue
        h = hashlib.sha256(f.read_bytes()).hexdigest()[:10]
        for attr in ("href", "src"):
            html = html.replace(f'{attr}="{rel}"', f'{attr}="{rel}?v={h}"')
        versions[rel] = h
    index.write_text(html, encoding="utf-8")
    return versions


def build(root: Path = ROOT, data_dir: Path = DATA_DIR) -> Path:
    out = root / "site"
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(root / "docs", out)
    (out / "data").mkdir(exist_ok=True)
    for f in data_dir.glob("*.json"):
        shutil.copy(f, out / "data" / f.name)
    version_assets(out)
    return out


def main() -> None:
    print(f"Bygget {build()}")


if __name__ == "__main__":
    main()
