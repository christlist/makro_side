"""Test av sitebyggingen: versjonerte URL-er (cache-busting) og at data kopieres. Små filer i tmp, ikke markedsdata."""
import re

from scripts import build_site


def make_root(tmp_path, css="a{}"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "vendor").mkdir(parents=True)
    (tmp_path / "data").mkdir()
    (tmp_path / "docs" / "index.html").write_text(
        '<link rel="stylesheet" href="style.css"><script src="vendor/plotly-basic.min.js"></script>'
        '<script src="render.js"></script><script src="app.js"></script>', encoding="utf-8")
    (tmp_path / "docs" / "style.css").write_text(css, encoding="utf-8")
    (tmp_path / "docs" / "render.js").write_text("r", encoding="utf-8")
    (tmp_path / "docs" / "app.js").write_text("a", encoding="utf-8")
    (tmp_path / "docs" / "vendor" / "plotly-basic.min.js").write_text("p", encoding="utf-8")
    (tmp_path / "data" / "x.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_assets_get_content_hash_and_data_is_copied(tmp_path):
    root = make_root(tmp_path)
    out = build_site.build(root, root / "data")
    html = (out / "index.html").read_text(encoding="utf-8")
    for ref in ("style.css", "vendor/plotly-basic.min.js", "render.js", "app.js"):
        assert re.search(rf'(href|src)="{re.escape(ref)}\?v=[0-9a-f]{{10}}"', html), ref
    assert (out / "data" / "x.json").exists()
    assert (root / "docs" / "index.html").read_text(encoding="utf-8").count("?v=") == 0  # kilden er urørt


def test_hash_changes_only_when_content_changes(tmp_path):
    n = [0]

    def css_version(css):
        n[0] += 1
        root = make_root(tmp_path / f"r{n[0]}", css)
        out = build_site.build(root, root / "data")
        return re.search(r"style\.css\?v=([0-9a-f]+)", (out / "index.html").read_text(encoding="utf-8")).group(1)

    assert css_version("a{}") == css_version("a{}")
    assert css_version("a{}") != css_version("b{}")
