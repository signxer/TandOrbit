"""显示器枚举解析测试（Windows EnumDisplayDevices + BetterDisplay identifiers）"""

from app.events import EventBus
from plugins.betterdisplay.plugin import BetterDisplayPlugin
from plugins.multimonitortool.plugin import MultiMonitorToolPlugin


class TestMultiMonitorToolParsing:
    """MultiMonitorTool 插件：EnumDisplayDevices JSON 解析"""

    def test_parse_empty(self) -> None:
        plugin = MultiMonitorToolPlugin(EventBus(), {})
        assert plugin._parse_displays("") == []
        assert plugin._parse_displays(None) == []
        assert plugin._parse_displays("[]") == []

    def test_parse_basic(self) -> None:
        plugin = MultiMonitorToolPlugin(EventBus(), {})
        output = (
            '[{"id": 1, "name": "\\\\\\\\.\\\\DISPLAY1", "is_primary": true, '
            '"is_enabled": true, "width": 0, "height": 0}, '
            '{"id": 2, "name": "\\\\\\\\.\\\\DISPLAY2", "is_primary": false, '
            '"is_enabled": true, "width": 0, "height": 0}]'
        )
        displays = plugin._parse_displays(output)
        assert len(displays) == 2
        assert displays[0].id == 1
        assert displays[0].is_primary
        assert displays[0].is_enabled
        assert displays[1].id == 2
        assert not displays[1].is_primary

    def test_parse_disabled_display(self) -> None:
        plugin = MultiMonitorToolPlugin(EventBus(), {})
        output = (
            '[{"id": 1, "name": "DISPLAY1", "is_primary": true, '
            '"is_enabled": false, "width": 0, "height": 0}]'
        )
        displays = plugin._parse_displays(output)
        assert len(displays) == 1
        assert not displays[0].is_enabled

    def test_parse_invalid_json(self) -> None:
        plugin = MultiMonitorToolPlugin(EventBus(), {})
        assert plugin._parse_displays("not json") == []

    def test_parse_missing_id_skipped(self) -> None:
        plugin = MultiMonitorToolPlugin(EventBus(), {})
        output = '[{"name": "DISPLAY1", "is_enabled": true}]'
        assert plugin._parse_displays(output) == []


class TestBetterDisplayParsing:
    """BetterDisplay 插件：identifiers 解析"""

    def test_parse_newline_separated_objects(self) -> None:
        plugin = BetterDisplayPlugin(EventBus(), {})
        output = (
            '{"tagID": 1441673168, "name": "DELL U2720Q", "deviceType": "Display", "main": 1}\n'
            '{"tagID": 1441673169, "name": "LG 27GN950", "deviceType": "Display", "main": 0}'
        )
        displays = plugin._parse_identifiers(output)
        assert len(displays) == 2
        assert displays[0].id == 1441673168
        assert displays[0].is_primary
        assert not displays[1].is_primary

    def test_parse_json_array(self) -> None:
        plugin = BetterDisplayPlugin(EventBus(), {})
        output = (
            '[{"tagID": 1, "name": "A", "deviceType": "Display", "main": 1}, '
            '{"tagID": 2, "name": "B", "deviceType": "Display", "main": 0}]'
        )
        displays = plugin._parse_identifiers(output)
        assert len(displays) == 2
        assert displays[1].id == 2

    def test_parse_main_missing_falls_back_to_first(self) -> None:
        plugin = BetterDisplayPlugin(EventBus(), {})
        output = (
            '{"tagID": 10, "name": "A", "deviceType": "Display"}\n'
            '{"tagID": 11, "name": "B", "deviceType": "Display"}'
        )
        displays = plugin._parse_identifiers(output)
        assert len(displays) == 2
        assert displays[0].is_primary
        assert not displays[1].is_primary

    def test_parse_skips_virtual_screens(self) -> None:
        plugin = BetterDisplayPlugin(EventBus(), {})
        output = (
            '{"tagID": 1, "name": "Real", "deviceType": "Display", "main": 1}\n'
            '{"tagID": 2, "name": "Virtual", "deviceType": "VirtualScreen"}'
        )
        displays = plugin._parse_identifiers(output)
        assert len(displays) == 1
        assert displays[0].name == "Real"

    def test_parse_string_main_values(self) -> None:
        plugin = BetterDisplayPlugin(EventBus(), {})
        output = (
            '{"tagID": 1, "name": "A", "deviceType": "Display", "main": "on"}\n'
            '{"tagID": 2, "name": "B", "deviceType": "Display", "main": "off"}'
        )
        displays = plugin._parse_identifiers(output)
        assert displays[0].is_primary
        assert not displays[1].is_primary

    def test_parse_empty_and_invalid(self) -> None:
        plugin = BetterDisplayPlugin(EventBus(), {})
        assert plugin._parse_identifiers("") == []
        assert plugin._parse_identifiers("garbage") == []


class TestBetterDisplayNestedParsing:
    """identifiers 输出为嵌套对象（{"identifiers": [...]}）的解析"""

    def test_parse_nested_object(self) -> None:
        plugin = BetterDisplayPlugin(EventBus(), {})
        output = (
            '{"identifiers": ['
            '{"tagID": 100, "name": "DELL U2720Q", "deviceType": "Display", "main": 1},'
            '{"tagID": 200, "name": "LG 27GN950", "deviceType": "Display", "main": 0}'
            "]}"
        )
        displays = plugin._parse_identifiers(output)
        assert len(displays) == 2
        assert displays[0].id == 100
        assert displays[0].name == "DELL U2720Q"
        assert displays[0].is_primary
        assert not displays[1].is_primary

    def test_parse_displays_key(self) -> None:
        plugin = BetterDisplayPlugin(EventBus(), {})
        output = (
            '{"displays": [{"tagID": 5, "name": "A", "deviceType": "Display"}]}'
        )
        displays = plugin._parse_identifiers(output)
        assert len(displays) == 1
        assert displays[0].id == 5




class TestDisplayIdentity:
    """Monitor ID 身份解析与匹配（用 json.dumps 构造，避免转义问题）"""

    @staticmethod
    def _displays(*rows: dict) -> str:
        import json
        return json.dumps(list(rows))

    def test_parse_monitor_id(self) -> None:
        plugin = MultiMonitorToolPlugin(EventBus(), {})
        output = self._displays(
            {"id": 3, "name": "DISPLAY3", "is_primary": True, "is_enabled": True,
             "monitor_id": r"MONITOR\DEL41A6\{abc}\0001", "device_id": r"\?\PCI#1"},
            {"id": 4, "name": "DISPLAY4", "is_primary": False, "is_enabled": True,
             "monitor_id": r"MONITOR\GSM5B9F\{def}\0001", "device_id": r"\?\PCI#2"},
        )
        displays = plugin._parse_displays(output)
        assert len(displays) == 2
        assert "DEL41A6" in displays[0].monitor_id
        assert displays[1].monitor_id.startswith(r"MONITOR\GSM")

    def test_find_by_exact_monitor_id(self) -> None:
        plugin = MultiMonitorToolPlugin(EventBus(), {})
        displays = plugin._parse_displays(self._displays(
            {"id": 3, "name": "DISPLAY3", "is_primary": True, "is_enabled": True,
             "monitor_id": r"MONITOR\DEL41A6\{abc}\0001"},
            {"id": 4, "name": "DISPLAY4", "is_primary": False, "is_enabled": True,
             "monitor_id": r"MONITOR\GSM5B9F\{def}\0001"},
        ))
        found = plugin.find_display_by_identity(displays, r"MONITOR\DEL41A6\{abc}\0001")
        assert found is not None and found.id == 3

    def test_find_by_short_monitor_id(self) -> None:
        plugin = MultiMonitorToolPlugin(EventBus(), {})
        displays = plugin._parse_displays(self._displays(
            {"id": 4, "name": "DISPLAY4", "is_primary": False, "is_enabled": True,
             "monitor_id": r"MONITOR\GSM5B9F\{def}\0001"},
        ))
        found = plugin.find_display_by_identity(displays, "GSM5B9F")
        assert found is not None and found.id == 4

    def test_find_returns_none_when_missing(self) -> None:
        plugin = MultiMonitorToolPlugin(EventBus(), {})
        displays = plugin._parse_displays(self._displays(
            {"id": 3, "name": "DISPLAY3", "is_primary": True, "is_enabled": True,
             "monitor_id": r"MONITOR\DEL41A6\{abc}\0001"},
        ))
        assert plugin.find_display_by_identity(displays, "NOPE") is None
        assert plugin.find_display_by_identity(displays, "") is None
