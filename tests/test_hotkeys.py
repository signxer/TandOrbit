"""全局快捷键解析测试"""

from app.hotkeys import (
    _MAC_KEYCODES,
    _WIN_VK,
    parse_hotkey,
)


class TestParseHotkey:
    def test_parse_ctrl_alt_1(self) -> None:
        mods, key = parse_hotkey("Ctrl+Alt+1")
        assert mods == frozenset({"control", "alt"})
        assert key == "1"

    def test_parse_mac_option(self) -> None:
        mods, key = parse_hotkey("Ctrl+Option+3")
        assert mods == frozenset({"control", "alt"})
        assert key == "3"

    def test_parse_cmd_shift_f9(self) -> None:
        mods, key = parse_hotkey("Cmd+Shift+F9")
        assert mods == frozenset({"meta", "shift"})
        assert key == "F9"

    def test_parse_case_insensitive(self) -> None:
        mods, key = parse_hotkey("ctrl+alt+a")
        assert mods == frozenset({"control", "alt"})
        assert key == "A"

    def test_parse_invalid_no_modifier(self) -> None:
        assert parse_hotkey("1") is None
        assert parse_hotkey("") is None

    def test_parse_invalid_modifier(self) -> None:
        assert parse_hotkey("Foo+Bar+1") is None

    def test_parse_unknown_key(self) -> None:
        assert parse_hotkey("Ctrl+Alt+????") is None

    def test_parse_duplicate_modifiers(self) -> None:
        mods, key = parse_hotkey("Ctrl+Ctrl+1")
        assert mods == frozenset({"control"})
        assert key == "1"


class TestKeyTables:
    def test_mac_keycodes_present(self) -> None:
        for token in ("1", "A", "Z", "SPACE", "TAB", "RETURN", "F1", "F12"):
            assert token in _MAC_KEYCODES, token

    def test_mac_f_key_sequence(self) -> None:
        assert _MAC_KEYCODES["F1"] == 122
        assert _MAC_KEYCODES["F12"] == 111

    def test_win_vk_present(self) -> None:
        for token in ("1", "A", "Z", "SPACE", "RETURN", "F1", "F12"):
            assert token in _WIN_VK, token

    def test_win_vk_values(self) -> None:
        assert _WIN_VK["A"] == 0x41
        assert _WIN_VK["1"] == 0x31
        assert _WIN_VK["F1"] == 0x70
        assert _WIN_VK["F12"] == 0x7B
