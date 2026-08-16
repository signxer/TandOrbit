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
