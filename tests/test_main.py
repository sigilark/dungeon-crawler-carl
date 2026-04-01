import json
from unittest.mock import patch

import pytest

SAMPLE_ACHIEVEMENT = {
    "title": "Baptism by Arabica",
    "description": "New Achievement! You hydrated your keyboard. Reward!",
    "reward": "+5 to Perceived Momentum",
}


def test_parse_args_defaults():
    """Default args: no trigger, no raw."""
    with patch("sys.argv", ["main.py"]):
        from main import parse_args
        args = parse_args()
        assert args.trigger is None
        assert args.raw is False


def test_parse_args_trigger():
    with patch("sys.argv", ["main.py", "--trigger", "spilled coffee"]):
        from main import parse_args
        args = parse_args()
        assert args.trigger == "spilled coffee"


def test_parse_args_raw():
    with patch("sys.argv", ["main.py", "--raw"]):
        from main import parse_args
        args = parse_args()
        assert args.raw is True


def test_parse_args_trigger_and_raw():
    with patch("sys.argv", ["main.py", "--trigger", "broke prod", "--raw"]):
        from main import parse_args
        args = parse_args()
        assert args.trigger == "broke prod"
        assert args.raw is True


@patch("main.archive.save", return_value={"id": 1})
@patch("main.generate", return_value=SAMPLE_ACHIEVEMENT)
@patch("main.print_achievement")
@patch("main.ANTHROPIC_API_KEY", "sk-test")
def test_main_normal_mode(mock_display, mock_gen, mock_save):
    """Normal mode: generates and prints achievement."""
    with patch("sys.argv", ["main.py"]):
        from main import main
        main()
    mock_gen.assert_called_once_with(trigger=None)
    mock_display.assert_called_once_with(SAMPLE_ACHIEVEMENT)


@patch("main.archive.save", return_value={"id": 1})
@patch("main.generate", return_value=SAMPLE_ACHIEVEMENT)
@patch("main.print_achievement")
@patch("main.ANTHROPIC_API_KEY", "sk-test")
def test_main_with_trigger(mock_display, mock_gen, mock_save):
    """Trigger mode: passes trigger to generate."""
    with patch("sys.argv", ["main.py", "--trigger", "spilled coffee"]):
        from main import main
        main()
    mock_gen.assert_called_once_with(trigger="spilled coffee")
    mock_display.assert_called_once_with(SAMPLE_ACHIEVEMENT)


@patch("main.generate", return_value=SAMPLE_ACHIEVEMENT)
@patch("main.ANTHROPIC_API_KEY", "sk-test")
def test_main_raw_mode(mock_gen, capsys):
    """Raw mode: prints JSON and exits 0."""
    with patch("sys.argv", ["main.py", "--raw"]):
        from main import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed == SAMPLE_ACHIEVEMENT


@patch("main.ANTHROPIC_API_KEY", "")
def test_main_missing_api_key(capsys):
    """Missing API key: prints setup message and exits 1."""
    with patch("sys.argv", ["main.py"]):
        from main import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Setup required" in captured.err


@patch("main.generate", side_effect=ValueError("parse failed"))
@patch("main.ANTHROPIC_API_KEY", "sk-test")
def test_main_generation_error(mock_gen, capsys):
    """Generation error: prints error and exits 1."""
    with patch("sys.argv", ["main.py"]):
        from main import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Generation error" in captured.err


@patch("main.generate", side_effect=OSError("no key"))
@patch("main.ANTHROPIC_API_KEY", "sk-test")
def test_main_config_error(mock_gen, capsys):
    """Config error: prints error and exits 1."""
    with patch("sys.argv", ["main.py"]):
        from main import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Configuration error" in captured.err


@patch("main.generate", side_effect=RuntimeError("API down"))
@patch("main.ANTHROPIC_API_KEY", "sk-test")
def test_main_api_error(mock_gen, capsys):
    """API error: prints error and exits 1."""
    with patch("sys.argv", ["main.py"]):
        from main import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "API error" in captured.err
