from pathlib import Path

from murray3d.gui.viewer import ASSETS_DIR, VIEWER_HTML, build_viewer_widget


def test_viewer_paths_exist():
    assert VIEWER_HTML.exists()
    assert (ASSETS_DIR / "model-viewer.min.js").exists()


def test_build_viewer_widget_returns_class():
    """Verify factory function returns a class (not an instance).

    Calling build_viewer_widget() lazily imports PySide6 and defines the
    ModelViewer QWidget subclass; this operation doesn't require a QApplication
    or display, making it safe in headless test environments.
    """
    result = build_viewer_widget()
    assert isinstance(result, type), "build_viewer_widget() should return a class"
