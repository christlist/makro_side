"""Bygg site/ = docs/ + data/*.json. Brukes lokalt og i workflowen før deploy."""
from __future__ import annotations

import shutil

from .common import DATA_DIR, ROOT


def main() -> None:
    out = ROOT / "site"
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "docs", out)
    (out / "data").mkdir(exist_ok=True)
    for f in DATA_DIR.glob("*.json"):
        shutil.copy(f, out / "data" / f.name)
    print(f"Bygget {out}")


if __name__ == "__main__":
    main()
