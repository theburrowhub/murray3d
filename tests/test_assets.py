from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "murray3d" / "gui" / "assets"


def test_model_viewer_present_and_nonempty():
    js = ASSETS / "model-viewer.min.js"
    assert js.exists(), "Ejecuta: python -m murray3d.gui.assets.download_model_viewer"
    assert js.stat().st_size > 100_000


def test_viewer_html_references_local_js_and_capture():
    html = (ASSETS / "viewer.html").read_text()
    assert "./model-viewer.min.js" in html
    assert "captureOrbit" in html
    assert "window.modelReady" in html
