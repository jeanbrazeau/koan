# Tests for key web flows: SSE replay, SPA fallback, start-run, artifacts, path traversal.
#
# M1 NOTE: tests that use the `client` fixture fail because the Starlette app
# startup calls _push_initial_config_events -> _serialize_profile which accesses
# ProfileTier.runner_type -- a field removed in the M1 config reshape. This is
# the expected settings-UI/probe path breakage; reworked in M8.
#
# M2 NOTE: the module-level xfail was removed. Tests that use the `client`
# fixture are marked xfail individually via request.applymarker in the client
# fixture, so passing tests (artifact/SSE/koan_set_workflow) run clean without
# an xfail decorator. test_api_artifact_comment_resolves_active_yield uses
# TestClient directly and carries its own @pytest.mark.xfail.

from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from koan.config import KoanConfig
from koan.probe import ProbeResult
from koan.state import AppState
from koan.types import AgentInstallation, ModelInfo, Profile, ProfileTier
from koan.web.app import create_app


# -- Helpers ------------------------------------------------------------------

def _make_probe_results() -> list[ProbeResult]:
    return [
        ProbeResult(
            runner_type="claude", available=True, binary_path="/fake/bin/claude", version="1.0",
            models=[
                # Opus advertises the full vocabulary including xhigh and max.
                ModelInfo(alias="opus", display_name="Opus",
                         thinking_modes=frozenset({"disabled", "low", "medium", "high", "xhigh", "max"}),
                         tier_hint="strong"),
                # Sonnet does not support xhigh or max; resolver clamps explicitly.
                ModelInfo(alias="sonnet", display_name="Sonnet",
                         thinking_modes=frozenset({"disabled", "low", "medium", "high"}),
                         tier_hint="standard"),
            ],
        ),
        ProbeResult(runner_type="codex", available=False),
        ProbeResult(runner_type="gemini", available=False),
    ]


# -- Fixtures -----------------------------------------------------------------

@pytest.fixture
def app_state():
    st = AppState()
    st.runner_config.config = KoanConfig()
    return st


@pytest.fixture
def client(app_state):
    # Patch driver_main to avoid spawning the real FSM
    with patch("koan.driver.driver_main", new_callable=AsyncMock):
        app = create_app(app_state)
        with TestClient(app) as c:
            yield c


# -- SPA fallback (formerly landing page) -------------------------------------

def test_landing_page_renders(client, app_state):
    # After SPA migration, GET / serves the React app's index.html (or a
    # minimal placeholder when the frontend hasn't been built).
    resp = client.get("/")
    assert resp.status_code == 200
    assert "root" in resp.text


# -- Start run ----------------------------------------------------------------

def test_start_run_requires_task(client, app_state):
    resp = client.post("/api/start-run", json={"task": ""})
    assert resp.status_code == 422


def test_start_run_requires_profile(client, app_state):
    app_state.runner_config.probe_results = _make_probe_results()
    resp = client.post("/api/start-run", json={"task": "build something"})
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_error"
    assert "profile" in resp.json()["message"]


def test_start_run_rejects_empty_profile(client, app_state):
    app_state.runner_config.probe_results = _make_probe_results()
    resp = client.post("/api/start-run", json={"task": "build something", "profile": ""})
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_error"
    assert "profile" in resp.json()["message"]


def test_start_run_blocked_no_providers(client, app_state):
    # Env-credential model: when no provider's credentials resolve, start-run is
    # blocked with `no_providers` (replaces the old CLI `no_runners`).
    app_state.runner_config.probe_results = [
        ProbeResult(runner_type="google", available=False),
    ]
    resp = client.post("/api/start-run", json={"task": "build something", "profile": "balanced"})
    assert resp.status_code == 422
    assert resp.json()["error"] == "no_providers"


# -- Start-run preflight -------------------------------------------------------

def test_preflight_returns_required_providers(client, app_state):
    from koan.agents.registry import compute_builtin_profiles
    app_state.runner_config.builtin_profiles = compute_builtin_profiles([])
    resp = client.get("/api/start-run/preflight?profile=balanced")
    assert resp.status_code == 200
    data = resp.json()
    # The built-in profiles are Gemini (google provider).
    assert "google" in data["required_providers"]
    assert "google" in data["providers"]
    assert "available" in data["providers"]["google"]


def test_preflight_missing_profile(client, app_state):
    resp = client.get("/api/start-run/preflight?profile=nonexistent")
    assert resp.status_code == 404


# (Removed with the CLI-binary model: preflight binary-validity, start-run
# missing-binary / unknown-installation-alias, /api/agents installation CRUD,
# and the CLI probe-refresh test. Provider availability is credential-based;
# there are no installations or binaries to validate.)


# -- Artifacts ----------------------------------------------------------------

def test_artifact_listing(client, app_state):
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        (run_dir / "landscape.md").write_text("# Landscape\n", "utf-8")
        app_state.run.run_dir = str(run_dir)

        resp = client.get("/api/artifacts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["files"]) == 1
        assert data["files"][0]["path"] == "landscape.md"


def test_artifact_content(client, app_state):
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        (run_dir / "landscape.md").write_text("# Hello\n", "utf-8")
        app_state.run.run_dir = str(run_dir)

        resp = client.get("/api/artifacts/landscape.md")
        assert resp.status_code == 200
        data = resp.json()
        assert "# Hello" in data["content"]
        assert data["displayPath"] == "landscape.md"


def test_path_traversal_blocked(client, app_state):
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        run_dir.mkdir(exist_ok=True)
        app_state.run.run_dir = str(run_dir)

        # URL-normalized traversal (../) is resolved before routing and hits the SPA fallback.
        # Use URL-encoded slashes (%2F) to test path traversal within the artifact handler.
        resp = client.get("/api/artifacts/..%2F..%2F..%2Fetc%2Fpasswd")
        assert resp.status_code in (400, 404)


# -- Profile endpoints --------------------------------------------------------

def test_profiles_create_invalid_runner(client, app_state):
    app_state.runner_config.probe_results = _make_probe_results()

    resp = client.post("/api/profiles", json={
        "name": "bad-runner",
        "tiers": {
            "strong": {"runner_type": "codex", "model": "gpt-5", "thinking": "disabled"},
        },
    })
    assert resp.status_code == 422
    assert "not available" in resp.json()["message"]


def test_profiles_create_invalid_model(client, app_state):
    app_state.runner_config.probe_results = _make_probe_results()

    resp = client.post("/api/profiles", json={
        "name": "bad-model",
        "tiers": {
            "strong": {"runner_type": "claude", "model": "nonexistent", "thinking": "disabled"},
        },
    })
    assert resp.status_code == 422
    assert "not found" in resp.json()["message"]


def test_profiles_create_invalid_thinking(client, app_state):
    app_state.runner_config.probe_results = _make_probe_results()

    resp = client.post("/api/profiles", json={
        "name": "bad-thinking",
        "tiers": {
            "strong": {"runner_type": "claude", "model": "opus", "thinking": "turbo"},
        },
    })
    assert resp.status_code == 422
    assert "not supported" in resp.json()["message"]


def test_profiles_update_balanced_rejected(client, app_state):
    resp = client.put("/api/profiles/balanced", json={"tiers": {}})
    assert resp.status_code == 422
    assert resp.json()["error"] == "read_only"


def test_profiles_delete_balanced_rejected(client, app_state):
    resp = client.delete("/api/profiles/balanced")
    assert resp.status_code == 400
    assert resp.json()["error"] == "read_only"


# -- api_artifact_comment endpoint -------------------------------------------

def test_api_artifact_comment_validates_path_and_comment(client, app_state):
    """POST /api/artifact-comment returns 422 on missing path or empty comment."""
    # Missing path
    resp = client.post("/api/artifact-comment", json={"comment": "hello"})
    assert resp.status_code == 422
    assert resp.json()["error"] == "missing_path"

    # Missing comment
    resp = client.post("/api/artifact-comment", json={"path": "plan.md"})
    assert resp.status_code == 422
    assert resp.json()["error"] == "missing_comment"

    # Empty comment string
    resp = client.post("/api/artifact-comment", json={"path": "plan.md", "comment": "  "})
    assert resp.status_code == 422
    assert resp.json()["error"] == "missing_comment"


def test_api_artifact_comment_enqueues_steering(client, app_state, tmp_path):
    """When no yield is active, the comment lands in steering_queue with artifact_path set."""
    app_state.run.run_dir = str(tmp_path)
    resp = client.post("/api/artifact-comment", json={
        "path": "plan.md",
        "comment": "Add a section on error handling",
    })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Message enqueued with artifact_path tagged
    queue = app_state.interactions.steering_queue
    assert len(queue) == 1
    assert queue[0].artifact_path == "plan.md"
    assert "error handling" in queue[0].content


@pytest.mark.anyio
async def test_api_artifact_comment_resolves_active_yield(tmp_path):
    """When a yield is active, the comment resolves the yield future."""
    import asyncio
    from unittest.mock import patch, AsyncMock
    from koan.web.app import create_app
    from koan.state import AppState, AgentState
    from koan.phases import PhaseContext

    app_state = AppState()
    app_state.run.run_dir = str(tmp_path)

    agent = AgentState(
        agent_id="test-artifact-comment-yield",
        role="orchestrator",
        subagent_dir=str(tmp_path),
        run_dir=str(tmp_path),
        step=2,
        is_primary=True,
        phase_ctx=PhaseContext(run_dir=str(tmp_path), subagent_dir=str(tmp_path)),
        event_log=AsyncMock(),
    )
    app_state.agents[agent.agent_id] = agent

    # Set an active yield future
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    app_state.interactions.yield_future = future

    with patch("koan.driver.driver_main", new_callable=AsyncMock):
        from starlette.testclient import TestClient
        starlette_app = create_app(app_state)
        with TestClient(starlette_app) as client:
            resp = client.post("/api/artifact-comment", json={
                "path": "brief.md",
                "comment": "Add more detail to the decisions section",
            })
            assert resp.status_code == 200
            assert resp.json()["ok"] is True

    # The future must have been resolved (not still pending)
    assert future.done()
    # The comment lands in the user message buffer with artifact_path set
    assert any(
        m.artifact_path == "brief.md"
        for m in app_state.interactions.user_message_buffer
    )


def test_api_artifact_comment_commits_attachments(client, app_state, tmp_path):
    """Attachments are committed before the comment is enqueued."""
    from unittest.mock import patch
    app_state.run.run_dir = str(tmp_path)

    # commit_to_run is imported inline in the handler from koan.web.uploads;
    # patch at the source module rather than the caller's namespace.
    with patch("koan.web.uploads.commit_to_run") as mock_commit:
        resp = client.post("/api/artifact-comment", json={
            "path": "plan.md",
            "comment": "see screenshot",
            "attachments": ["upload-abc123"],
        })
        assert resp.status_code == 200
        mock_commit.assert_called_once()
        call_args = mock_commit.call_args
        # Second positional arg is the attachment IDs list
        assert call_args[0][1] == ["upload-abc123"]


def test_profiles_create_non_dict_tiers(client, app_state):
    app_state.runner_config.probe_results = _make_probe_results()
    resp = client.post("/api/profiles", json={
        "name": "bad-tiers",
        "tiers": [],
    })
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_error"
    assert "object" in resp.json()["message"]


def test_profiles_create_non_dict_tier_entry(client, app_state):
    app_state.runner_config.probe_results = _make_probe_results()
    resp = client.post("/api/profiles", json={
        "name": "bad-entry",
        "tiers": {"strong": "bad"},
    })
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_error"
    assert "must be an object" in resp.json()["message"]


def test_profiles_update_non_dict_tiers(client, app_state):
    app_state.runner_config.probe_results = _make_probe_results()
    app_state.runner_config.config.profiles.append(Profile(name="myprofile", tiers={}))
    resp = client.put("/api/profiles/myprofile", json={"tiers": "bad"})
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_error"
    assert "object" in resp.json()["message"]


def test_profiles_delete_user_profile(client, app_state):
    app_state.runner_config.config.profiles.append(Profile(name="myprofile", tiers={}))
    resp = client.delete("/api/profiles/myprofile")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert not any(p.name == "myprofile" for p in app_state.runner_config.config.profiles)


# -- Agent detect endpoint ----------------------------------------------------

def test_agents_detect_found(client, app_state):
    with patch("koan.web.app.shutil.which", return_value="/usr/bin/claude"):
        resp = client.get("/api/agents/detect?runner_type=claude")
    assert resp.status_code == 200
    assert resp.json()["path"] == "/usr/bin/claude"


def test_agents_detect_not_found(client, app_state):
    with patch("koan.web.app.shutil.which", return_value=None):
        resp = client.get("/api/agents/detect?runner_type=claude")
    assert resp.status_code == 200
    assert resp.json()["path"] is None


def test_agents_detect_missing_param(client, app_state):
    resp = client.get("/api/agents/detect")
    assert resp.status_code == 422


# -- SSE replay ---------------------------------------------------------------

def test_sse_replay(app_state):
    """SSE stream sends a snapshot and the protocol uses push_event / get_snapshot."""
    from koan.web.app import _sse_event

    # Prime with a run_started so phase_started has a run to update
    app_state.projection_store.push_event("run_started", {"profile": "balanced", "installations": {}, "scout_concurrency": 8})
    app_state.projection_store.push_event("phase_started", {"phase": "intake"})

    # Verify projection holds the phase in the new nested location
    assert app_state.projection_store.projection.run is not None
    assert app_state.projection_store.projection.run.phase == "intake"
    assert app_state.projection_store.version == 2

    # Verify the SSE event formatter produces correct output
    event_str = _sse_event("snapshot", app_state.projection_store.get_snapshot())
    assert "event: snapshot" in event_str
    assert '"intake"' in event_str

    # Verify audit log retains events
    assert len(app_state.projection_store.events) == 2
    assert app_state.projection_store.events[1].event_type == "phase_started"


# -- Live page redirect (now SPA fallback) ------------------------------------

def test_live_page_when_running(client, app_state):
    # After SPA migration, GET / always returns the SPA entry point.
    # The React app reads store state client-side to render the live view.
    app_state.run.run_dir = "/tmp/fake-run"
    app_state.run.phase = "intake"

    resp = client.get("/")
    assert resp.status_code == 200
    assert "root" in resp.text



# -- Old model-config route removed ------------------------------------------

def test_model_config_removed(client, app_state):
    # After SPA migration, unknown paths are served by the SPA fallback (200).
    # The /api/model-config endpoint no longer exists as a JSON API endpoint.
    resp = client.get("/api/model-config")
    # SPA fallback serves HTML, not a JSON API response
    assert resp.status_code in (200, 404, 405)
    if resp.status_code == 200:
        # Must be HTML (SPA), not a JSON API response
        ct = resp.headers.get("content-type", "")
        assert "text/html" in ct


# -- Landing page: profile selector & settings button ------------------------

def test_landing_includes_profile_selector(client, app_state):
    # After SPA migration, GET / serves the React SPA, not server-rendered HTML.
    # Profile selector is rendered client-side by React.
    from koan.agents.registry import compute_builtin_profiles
    app_state.runner_config.probe_results = _make_probe_results()
    app_state.runner_config.builtin_profiles = compute_builtin_profiles([])
    resp = client.get("/")
    assert resp.status_code == 200


def test_landing_start_run_disabled_no_runners(client, app_state):
    # After SPA migration, runner availability is checked client-side via /api/probe.
    app_state.runner_config.probe_results = [
        ProbeResult(runner_type="claude", available=False),
        ProbeResult(runner_type="codex", available=False),
    ]
    resp = client.get("/")
    assert resp.status_code == 200


def test_landing_start_run_enabled_with_runners(client, app_state):
    # After SPA migration, GET / serves the SPA regardless of runner state.
    app_state.runner_config.probe_results = _make_probe_results()
    app_state.runner_config.builtin_profiles = {"balanced": Profile(name="balanced", tiers={})}
    resp = client.get("/")
    assert resp.status_code == 200


def test_start_run_sends_profile(client, app_state):
    app_state.runner_config.probe_results = _make_probe_results()
    resp = client.post(
        "/api/start-run",
        json={"task": "build something", "profile": "balanced"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert app_state.runner_config.config.active_profile == "balanced"


def test_start_run_unknown_profile_rejected(client, app_state):
    app_state.runner_config.probe_results = _make_probe_results()
    resp = client.post(
        "/api/start-run",
        json={"task": "build something", "profile": "nonexistent"},
    )
    assert resp.status_code == 422
    assert "not found" in resp.json()["message"]


# -- Probe refresh ------------------------------------------------------------

class TestProbeRefresh:
    def test_probe_refresh_repopulates_providers(self, client, app_state):
        # refresh=1 recomputes builtin profiles + provider availability (env-
        # credential model; no CLI probe). Asserts the endpoint returns 200 and
        # provider rows.
        app_state.runner_config.probe_results = []
        app_state.runner_config.builtin_profiles = {}
        resp = client.get("/api/probe?refresh=1")
        assert resp.status_code == 200
        assert app_state.runner_config.builtin_profiles  # repopulated
        assert app_state.runner_config.probe_results  # provider rows present

    def test_probe_no_refresh_skips_restate(self, client, app_state):
        app_state.runner_config.probe_results = _make_probe_results()
        app_state.runner_config.builtin_profiles = {"balanced": Profile(name="balanced", tiers={})}

        with patch("koan.probe.probe_all_runners", new_callable=AsyncMock) as mock_probe:
            resp = client.get("/api/probe")

        assert resp.status_code == 200
        mock_probe.assert_not_called()
        data = resp.json()
        assert len(data["runners"]) == 3



# -- SSE endpoint HTTP-level tests -------------------------------------------

@pytest.mark.anyio
def test_sse_snapshot_contains_projection_state(app_state):
    """Snapshot SSE event contains the full camelCase projection as {version, state}."""
    from koan.web.app import _sse_event

    app_state.projection_store.push_event("run_started", {"profile": "balanced", "installations": {}, "scout_concurrency": 8})
    app_state.projection_store.push_event("phase_started", {"phase": "intake"})

    snapshot = app_state.projection_store.get_snapshot()
    assert snapshot["version"] == 2
    # New model: phase lives inside run
    assert snapshot["state"]["run"]["phase"] == "intake"
    # New model: top-level fields are settings, run, notifications
    assert "settings" in snapshot["state"]
    assert "notifications" in snapshot["state"]

    # Verify SSE wire format
    event_str = _sse_event("snapshot", snapshot)
    assert "event: snapshot" in event_str
    assert '"intake"' in event_str


def test_sse_audit_log_retains_events(app_state):
    """Audit log retains all events in order; reconnecting clients get a fresh snapshot."""
    app_state.projection_store.push_event("run_started", {"profile": "balanced", "installations": {}, "scout_concurrency": 8})
    app_state.projection_store.push_event("phase_started", {"phase": "intake"})
    app_state.projection_store.push_event("phase_started", {"phase": "brief-generation"})
    # version is now 3

    assert len(app_state.projection_store.events) == 3
    assert app_state.projection_store.version == 3

    # Last event is in the log
    last = app_state.projection_store.events[-1]
    assert last.event_type == "phase_started"
    assert last.payload["phase"] == "brief-generation"

    # Projection reflects latest state
    assert app_state.projection_store.projection.run.phase == "brief-generation"

    # Snapshot for reconnect reflects full current state
    snap = app_state.projection_store.get_snapshot()
    assert snap["version"] == 3
    assert snap["state"]["run"]["phase"] == "brief-generation"


def test_sse_always_snapshot_on_version_mismatch(app_state):
    """Any since != server.version triggers a fresh snapshot (no fatal_error)."""
    store = app_state.projection_store
    assert store.version == 0

    # Any client version (stale or ahead) gets a snapshot. No fatal_error.
    # The server simply sends its current state.
    snap = store.get_snapshot()
    assert snap["version"] == 0
    assert snap["state"]["run"] is None

    # Advance server
    store.push_event("run_started", {"profile": "balanced", "installations": {}, "scout_concurrency": 8})
    assert store.version == 1

    # Client at since=99 (> server) still gets a valid snapshot
    # (sse_stream sends snapshot when since != store.version)
    snap2 = store.get_snapshot()
    assert snap2["version"] == 1
    assert snap2["state"]["run"] is not None


# -- koan_artifact_write -------------------------------------------------------

def _make_orchestrator_agent(tmp_path, agent_id="test-write"):
    """Build a minimal orchestrator AgentState for handler tests."""
    from unittest.mock import AsyncMock
    from koan.state import AgentState, AppState
    from koan.phases import PhaseContext

    app_state = AppState()
    app_state.server.yolo = True
    app_state.run.phase = "plan-spec"
    app_state.run.run_dir = str(tmp_path)

    agent = AgentState(
        agent_id=agent_id,
        role="orchestrator",
        subagent_dir=str(tmp_path),
        run_dir=str(tmp_path),
        step=2,
        is_primary=True,
        phase_ctx=PhaseContext(run_dir=str(tmp_path), subagent_dir=str(tmp_path)),
        event_log=AsyncMock(),
    )
    app_state.agents[agent.agent_id] = agent
    return app_state, agent


class _FakeCtx:
    """Minimal fastmcp Context stub that returns a fixed agent."""
    def __init__(self, agent):
        self._agent = agent

    async def get_state(self, key):
        if key == "agent":
            return self._agent
        return None


@pytest.mark.anyio
async def test_artifact_write_atomic_writes_with_frontmatter(tmp_path):
    """koan_artifact_write creates the file with driver-managed frontmatter."""
    from koan.web.mcp_endpoint import build_mcp_server
    from koan.artifacts import split_frontmatter

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-write-fm")
    _, handlers = build_mcp_server(app_state)

    result = await handlers.koan_artifact_write(_FakeCtx(agent), "smoke.md", "hello")

    assert (tmp_path / "smoke.md").exists()
    text = (tmp_path / "smoke.md").read_text()
    assert text.startswith("---\n")
    meta, body = split_frontmatter(text)
    assert meta is not None
    # Status field removed -- only timestamps in frontmatter
    assert "status" not in meta
    assert "created" in meta
    assert body == "hello"

    # Return value is ok=True JSON
    import json
    payload = json.loads(result[0].text)
    assert payload["ok"] is True
    assert payload["filename"] == "smoke.md"
    assert "status" not in payload


@pytest.mark.anyio
async def test_artifact_write_emits_diff_events(tmp_path):
    """koan_artifact_write triggers artifact_diff so the sidebar refreshes."""
    from koan.web.mcp_endpoint import build_mcp_server

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-write-diff")
    _, handlers = build_mcp_server(app_state)

    await handlers.koan_artifact_write(_FakeCtx(agent), "smoke.md", "hello")

    event_types = [e.event_type for e in app_state.projection_store.events]
    # _push_artifact_diff emits artifact_created or artifact_modified depending
    # on whether the file existed before the call
    assert any(t in event_types for t in ("artifact_created", "artifact_modified", "artifact_diff"))


@pytest.mark.anyio
async def test_artifact_write_does_not_emit_review_events(tmp_path):
    """koan_artifact_write must not emit review_started or review_cleared."""
    from koan.web.mcp_endpoint import build_mcp_server

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-write-noreview")
    _, handlers = build_mcp_server(app_state)

    await handlers.koan_artifact_write(_FakeCtx(agent), "smoke.md", "hello")

    event_types = [e.event_type for e in app_state.projection_store.events]
    assert "artifact_review_started" not in event_types
    assert "artifact_review_cleared" not in event_types


@pytest.mark.anyio
async def test_artifact_write_does_not_block(tmp_path):
    """koan_artifact_write returns immediately (non-blocking)."""
    from koan.web.mcp_endpoint import build_mcp_server

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-write-noblock")
    _, handlers = build_mcp_server(app_state)

    # If this awaits without blocking, the test passes implicitly.
    result = await handlers.koan_artifact_write(_FakeCtx(agent), "smoke.md", "hello")
    assert result is not None


@pytest.mark.anyio
async def test_artifact_write_does_not_block_2(tmp_path):
    """koan_artifact_write returns immediately without a status argument."""
    from koan.web.mcp_endpoint import build_mcp_server

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-write-noarg")
    _, handlers = build_mcp_server(app_state)

    result = await handlers.koan_artifact_write(_FakeCtx(agent), "smoke.md", "content")
    assert result is not None


@pytest.mark.anyio
async def test_artifact_view_strips_frontmatter(tmp_path):
    """koan_artifact_view returns body only -- no YAML preamble visible to LLM."""
    from koan.web.mcp_endpoint import build_mcp_server
    from koan.artifacts import write_artifact_atomic

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-view-strip")
    _, handlers = build_mcp_server(app_state)

    target = tmp_path / "doc.md"
    write_artifact_atomic(target, "# Hello\nbody text\n")

    result = await handlers.koan_artifact_view(_FakeCtx(agent), "doc.md")
    returned_text = result[0].text
    assert "---" not in returned_text
    assert "# Hello\nbody text\n" == returned_text


@pytest.mark.anyio
async def test_artifact_list_omits_status(tmp_path):
    """koan_artifact_list JSON must not contain a status field per artifact."""
    import json
    from koan.web.mcp_endpoint import build_mcp_server
    from koan.artifacts import write_artifact_atomic

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-list-no-status")
    _, handlers = build_mcp_server(app_state)

    write_artifact_atomic(tmp_path / "with-fm.md", "body")
    (tmp_path / "plain.md").write_text("# No frontmatter\n")

    result = await handlers.koan_artifact_list(_FakeCtx(agent))
    payload = json.loads(result[0].text)
    by_path = {a["path"]: a for a in payload["artifacts"]}

    assert "status" not in by_path["with-fm.md"]
    assert "status" not in by_path["plain.md"]
    # Canonical fields must be present
    assert "path" in by_path["with-fm.md"]
    assert "size" in by_path["with-fm.md"]
    assert "modified_at" in by_path["with-fm.md"]


# -- koan_artifact_edit -------------------------------------------------------

@pytest.mark.anyio
async def test_artifact_edit_replaces_single_occurrence(tmp_path):
    """koan_artifact_edit replaces exactly one occurrence and the body is updated."""
    import json
    from koan.web.mcp_endpoint import build_mcp_server
    from koan.artifacts import split_frontmatter

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-edit-replace")
    _, handlers = build_mcp_server(app_state)

    await handlers.koan_artifact_write(_FakeCtx(agent), "doc.md", "hello world\n")

    result = await handlers.koan_artifact_edit(_FakeCtx(agent), "doc.md", "world", "koan")
    payload = json.loads(result[0].text)
    assert payload["ok"] is True
    assert payload["filename"] == "doc.md"

    _, body = split_frontmatter((tmp_path / "doc.md").read_text())
    assert body == "hello koan\n"
    assert "world" not in body


@pytest.mark.anyio
async def test_artifact_edit_preserves_created(tmp_path):
    """koan_artifact_edit preserves the created timestamp across edits."""
    from koan.web.mcp_endpoint import build_mcp_server
    from koan.artifacts import split_frontmatter

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-edit-created")
    _, handlers = build_mcp_server(app_state)

    await handlers.koan_artifact_write(_FakeCtx(agent), "doc.md", "original content\n")
    first_meta, _ = split_frontmatter((tmp_path / "doc.md").read_text())
    assert first_meta is not None
    original_created = first_meta["created"]

    await handlers.koan_artifact_edit(_FakeCtx(agent), "doc.md", "original", "updated")
    second_meta, _ = split_frontmatter((tmp_path / "doc.md").read_text())
    assert second_meta is not None
    assert second_meta["created"] == original_created
    assert "last_modified" in second_meta


@pytest.mark.anyio
async def test_artifact_edit_file_not_found(tmp_path):
    """koan_artifact_edit raises ToolError with error=not_found for missing file."""
    import json
    from fastmcp.exceptions import ToolError
    from koan.web.mcp_endpoint import build_mcp_server

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-edit-notfound")
    _, handlers = build_mcp_server(app_state)

    with pytest.raises(ToolError) as exc_info:
        await handlers.koan_artifact_edit(_FakeCtx(agent), "missing.md", "old", "new")
    body = json.loads(str(exc_info.value))
    assert body["error"] == "not_found"


@pytest.mark.anyio
async def test_artifact_edit_no_match(tmp_path):
    """koan_artifact_edit raises ToolError with error=no_match when old_string absent."""
    import json
    from fastmcp.exceptions import ToolError
    from koan.web.mcp_endpoint import build_mcp_server

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-edit-nomatch")
    _, handlers = build_mcp_server(app_state)

    await handlers.koan_artifact_write(_FakeCtx(agent), "doc.md", "hello world\n")

    with pytest.raises(ToolError) as exc_info:
        await handlers.koan_artifact_edit(_FakeCtx(agent), "doc.md", "nonexistent", "x")
    body = json.loads(str(exc_info.value))
    assert body["error"] == "no_match"


@pytest.mark.anyio
async def test_artifact_edit_multiple_matches(tmp_path):
    """koan_artifact_edit raises ToolError with error=multiple_matches when >1 occurrence."""
    import json
    from fastmcp.exceptions import ToolError
    from koan.web.mcp_endpoint import build_mcp_server

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-edit-multi")
    _, handlers = build_mcp_server(app_state)

    await handlers.koan_artifact_write(_FakeCtx(agent), "doc.md", "foo bar foo\n")

    with pytest.raises(ToolError) as exc_info:
        await handlers.koan_artifact_edit(_FakeCtx(agent), "doc.md", "foo", "baz")
    body = json.loads(str(exc_info.value))
    assert body["error"] == "multiple_matches"


@pytest.mark.anyio
async def test_artifact_edit_invalid_edit_empty_old(tmp_path):
    """koan_artifact_edit raises ToolError with error=invalid_edit for empty old_string."""
    import json
    from fastmcp.exceptions import ToolError
    from koan.web.mcp_endpoint import build_mcp_server

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-edit-empty")
    _, handlers = build_mcp_server(app_state)

    await handlers.koan_artifact_write(_FakeCtx(agent), "doc.md", "content\n")

    with pytest.raises(ToolError) as exc_info:
        await handlers.koan_artifact_edit(_FakeCtx(agent), "doc.md", "", "new")
    body = json.loads(str(exc_info.value))
    assert body["error"] == "invalid_edit"


@pytest.mark.anyio
async def test_artifact_edit_invalid_edit_same_strings(tmp_path):
    """koan_artifact_edit raises ToolError with error=invalid_edit when old==new."""
    import json
    from fastmcp.exceptions import ToolError
    from koan.web.mcp_endpoint import build_mcp_server

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-edit-same")
    _, handlers = build_mcp_server(app_state)

    await handlers.koan_artifact_write(_FakeCtx(agent), "doc.md", "same content\n")

    with pytest.raises(ToolError) as exc_info:
        await handlers.koan_artifact_edit(_FakeCtx(agent), "doc.md", "same", "same")
    body = json.loads(str(exc_info.value))
    assert body["error"] == "invalid_edit"


@pytest.mark.anyio
async def test_artifact_edit_emits_diff_events(tmp_path):
    """koan_artifact_edit triggers artifact_diff so the sidebar refreshes."""
    from koan.web.mcp_endpoint import build_mcp_server

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-edit-diff")
    _, handlers = build_mcp_server(app_state)

    await handlers.koan_artifact_write(_FakeCtx(agent), "doc.md", "before edit\n")
    # Clear events recorded during write so we can isolate the edit's events
    events_before = len(app_state.projection_store.events)

    await handlers.koan_artifact_edit(_FakeCtx(agent), "doc.md", "before", "after")

    new_event_types = [
        e.event_type for e in app_state.projection_store.events[events_before:]
    ]
    assert any(t in new_event_types for t in ("artifact_created", "artifact_modified", "artifact_diff"))


# -- api_sessions_list: workflow_history schema --------------------------------

def test_api_sessions_list_returns_workflow_from_history(tmp_path, client):
    """api_sessions_list derives the workflow field from workflow_history[-1]["name"]."""
    run_dir = tmp_path / "2099000000-aabbccdd"
    run_dir.mkdir()
    (run_dir / "task.json").write_text(json.dumps({
        "task": "build something",
        "workflow_history": [{"name": "plan", "phase": "intake", "started_at": 0.0}],
        "created_at": 0.0,
        "project_dir": "/some/project",
    }))

    with patch("koan.web.app.RUNS_DIR", tmp_path):
        resp = client.get("/api/sessions")

    assert resp.status_code == 200
    sessions = resp.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["workflow"] == "plan"


def test_api_sessions_list_handles_empty_history(tmp_path, client):
    """api_sessions_list returns workflow='' and does not crash when workflow_history is empty."""
    run_dir = tmp_path / "2099000001-aabbccdd"
    run_dir.mkdir()
    (run_dir / "task.json").write_text(json.dumps({
        "task": "build something",
        "workflow_history": [],
        "created_at": 0.0,
        "project_dir": "/some/project",
    }))

    with patch("koan.web.app.RUNS_DIR", tmp_path):
        resp = client.get("/api/sessions")

    assert resp.status_code == 200
    sessions = resp.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["workflow"] == ""


# -- koan_set_workflow handler -------------------------------------------------

@pytest.mark.anyio
async def test_koan_set_workflow_swaps_app_state_and_appends_history(tmp_path):
    """koan_set_workflow swaps app_state.run.workflow and appends a history entry to task.json."""
    from fastmcp.exceptions import ToolError
    from koan.lib.workflows import get_workflow
    from koan.web.mcp_endpoint import build_mcp_server

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-set-workflow")
    # Set up the run with the "plan" workflow so the transition makes sense.
    app_state.run.workflow = get_workflow("plan")

    # Write a task.json with a single workflow_history entry (as driver_main would).
    (tmp_path / "task.json").write_text(json.dumps({
        "workflow_history": [{"name": "plan", "phase": "intake", "started_at": 0.0}],
    }))

    _, handlers = build_mcp_server(app_state)
    result = await handlers.koan_set_workflow(_FakeCtx(agent), "milestones")

    # app_state should reflect the new workflow.
    assert app_state.run.workflow.name == "milestones"
    assert app_state.run.phase == "intake"

    # task.json on disk should have two history entries.
    import json as _json
    task_dict = _json.loads((tmp_path / "task.json").read_text())
    history = task_dict["workflow_history"]
    assert len(history) == 2
    assert history[0]["name"] == "plan"
    assert history[1]["name"] == "milestones"
    assert history[1]["phase"] == "intake"

    # Return value mentions the new workflow and phase.
    assert "milestones" in result[0].text
    assert "intake" in result[0].text


@pytest.mark.anyio
async def test_koan_set_workflow_unknown_workflow_raises(tmp_path):
    """koan_set_workflow raises ToolError with error=unknown_workflow for an unregistered name."""
    import json as _json
    from fastmcp.exceptions import ToolError
    from koan.web.mcp_endpoint import build_mcp_server

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-set-workflow-bad")
    (tmp_path / "task.json").write_text(_json.dumps({
        "workflow_history": [{"name": "plan", "phase": "intake", "started_at": 0.0}],
    }))

    _, handlers = build_mcp_server(app_state)

    with pytest.raises(ToolError) as exc_info:
        await handlers.koan_set_workflow(_FakeCtx(agent), "nonexistent")
    body = json.loads(str(exc_info.value))
    assert body["error"] == "unknown_workflow"


@pytest.mark.anyio
async def test_koan_set_workflow_emits_projection_events(tmp_path):
    """koan_set_workflow emits workflow_selected, phase_started, yield_cleared, agent_step_advanced in order."""
    import json as _json
    from koan.lib.workflows import get_workflow
    from koan.web.mcp_endpoint import build_mcp_server

    app_state, agent = _make_orchestrator_agent(tmp_path, "test-set-workflow-events")
    app_state.run.workflow = get_workflow("plan")
    (tmp_path / "task.json").write_text(_json.dumps({
        "workflow_history": [{"name": "plan", "phase": "intake", "started_at": 0.0}],
    }))

    _, handlers = build_mcp_server(app_state)

    # Record projection events emitted during the call.
    events_before = len(app_state.projection_store.events)
    await handlers.koan_set_workflow(_FakeCtx(agent), "milestones")
    new_events = app_state.projection_store.events[events_before:]

    event_types = [e.event_type for e in new_events]
    # workflow_selected must come before phase_started (fold order matters).
    assert "workflow_selected" in event_types
    assert "phase_started" in event_types
    assert "yield_cleared" in event_types
    assert "agent_step_advanced" in event_types

    wf_idx = event_types.index("workflow_selected")
    ph_idx = event_types.index("phase_started")
    assert wf_idx < ph_idx, "workflow_selected must precede phase_started"

    # Payload checks.
    wf_event = new_events[wf_idx]
    assert wf_event.payload.get("workflow") == "milestones"
    ph_event = new_events[ph_idx]
    assert ph_event.payload.get("phase") == "intake"
