from murray3d.gui.workers import run_callable


def test_run_callable_success():
    ok, value = run_callable(lambda: 40 + 2)
    assert ok is True and value == 42


def test_run_callable_captures_exception():
    def boom():
        raise ValueError("nope")

    ok, value = run_callable(boom)
    assert ok is False
    assert isinstance(value, str) and "nope" in value
