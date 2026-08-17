"""Agent HTTP 服务冒烟测试（双平台：Windows 上价值最大，Mac 上也跑）

用 starlette TestClient 直接测 ASGI 应用，无需真实端口。
覆盖：健康检查、无插件错误路径、token 鉴权、切换声明仲裁。
"""

from starlette.testclient import TestClient

from app.communication.agent_server import AgentServer
from app.enums import Mode
from app.events import EventBus
from app.state.state_machine import StateManager


def _client(server: AgentServer) -> TestClient:
    return TestClient(server.create_app())


class TestAgentSmoke:
    def test_health_endpoint(self) -> None:
        resp = _client(AgentServer()).get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_status_endpoint(self) -> None:
        resp = _client(AgentServer()).get("/api/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_display_list_without_plugin_returns_503(self) -> None:
        resp = _client(AgentServer()).get("/api/display/list")
        assert resp.status_code == 503
        assert resp.json()["success"] is False

    def test_unknown_route_404(self) -> None:
        resp = _client(AgentServer()).get("/api/nonexistent")
        assert resp.status_code == 404


class TestAgentAuth:
    def test_auth_token_required(self) -> None:
        server = AgentServer()
        server.set_auth_token("secret-token")
        client = _client(server)

        # 未授权：除 /api/health 外一律 401
        assert client.get("/api/status").status_code == 401
        assert client.post("/api/display/disable", json={"display_id": 2}).status_code == 401
        assert client.post("/api/power/shutdown").status_code == 401
        # 健康检查放行（在线探测依赖它）
        assert client.get("/api/health").status_code == 200
        # 错误 token 也拒绝
        assert client.get("/api/status", headers={"Authorization": "Bearer wrong"}).status_code == 401
        # 正确 token 通过
        resp = client.get("/api/status", headers={"Authorization": "Bearer secret-token"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_no_token_disables_auth(self) -> None:
        # 未配置 token（默认）→ 不鉴权，兼容旧部署
        resp = _client(AgentServer()).get("/api/status")
        assert resp.status_code == 200


class TestModeClaim:
    def test_claim_accepted_when_idle(self) -> None:
        resp = _client(AgentServer()).post("/api/mode/claim", json={"mode": "SHARE"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_claim_conflict_when_transitioning(self) -> None:
        sm = StateManager(EventBus())
        sm.force_set(Mode.MAC)
        sm.set_target(Mode.WINDOWS)
        sm.begin_transition()
        server = AgentServer()
        server.set_state_manager(sm)
        resp = _client(server).post("/api/mode/claim", json={"mode": "SHARE"})
        assert resp.status_code == 409
        assert resp.json()["error"] == "conflict"

    def test_claim_busy_within_window(self) -> None:
        """1 秒内的重复声明拒绝（缩小两端同时发起竞态）"""
        client = _client(AgentServer())
        assert client.post("/api/mode/claim", json={"mode": "MAC"}).status_code == 200
        resp = client.post("/api/mode/claim", json={"mode": "WINDOWS"})
        assert resp.status_code == 409
        assert resp.json()["error"] == "busy"


class TestRemoteModePersistence:
    def test_persist_last_mode_preserves_custom_config(self, tmp_path) -> None:
        from app.config import ConfigManager

        cm = ConfigManager(tmp_path / "config.yaml")
        cm.load()
        cm.update({
            "windows": {"host": "10.20.30.40", "port": 5010},
            "display": {"primary_id": 3, "secondary_id": 4},
            "agent_token": "keep-me",
        })
        server = AgentServer(config_manager=cm)
        server._persist_last_mode(Mode.WINDOWS)

        reloaded = ConfigManager(tmp_path / "config.yaml")
        cfg = reloaded.load()
        assert cfg.last_mode == "WINDOWS"
        assert cfg.windows.host == "10.20.30.40"
        assert cfg.windows.port == 5010
        assert cfg.display.primary_id == 3
        assert cfg.display.secondary_id == 4
        assert cfg.agent_token == "keep-me"
