def test_run_gui_is_callable():
    from murray3d.gui.app import run_gui
    assert callable(run_gui)
