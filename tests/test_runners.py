# Unit tests for koan.runners -- parse_stream_event and build_command.

import json

import pytest

from koan.runners import ClaudeRunner, CodexRunner, GeminiRunner, RunnerError, StreamEvent


# -- ClaudeRunner: parse_stream_event ------------------------------------------

class TestClaudeRunnerParseStreamEvent:
    def setup_method(self):
        self.runner = ClaudeRunner(subagent_dir="/tmp/test-claude")

    def test_text_delta(self):
        line = json.dumps({"type": "assistant", "content": [{"type": "text", "text": "hello"}]})
        evts = self.runner.parse_stream_event(line)
        assert evts == [StreamEvent(type="token_delta", content="hello")]

    def test_tool_call(self):
        line = json.dumps({
            "type": "assistant",
            "content": [{"type": "tool_use", "name": "bash", "input": {"cmd": "ls"}}],
        })
        evts = self.runner.parse_stream_event(line)
        assert evts == [StreamEvent(type="tool_call", tool_name="bash", tool_args={"cmd": "ls"})]

    def test_thinking_block(self):
        line = json.dumps({"type": "assistant", "content": [{"type": "thinking", "text": "hmm"}]})
        evts = self.runner.parse_stream_event(line)
        assert evts == [StreamEvent(type="thinking", is_thinking=True)]

    def test_result_success(self):
        line = json.dumps({"type": "result", "subtype": "success", "result": "done"})
        evts = self.runner.parse_stream_event(line)
        assert evts == [StreamEvent(type="turn_complete", content="done")]

    def test_system_event_skipped(self):
        line = json.dumps({"type": "system", "subtype": "init"})
        assert self.runner.parse_stream_event(line) == []

    def test_invalid_json(self):
        assert self.runner.parse_stream_event("not json{") == []

    def test_multi_block_text_and_tool(self):
        line = json.dumps({
            "type": "assistant",
            "content": [
                {"type": "text", "text": "calling tool"},
                {"type": "tool_use", "name": "read", "input": {"path": "/a"}},
            ],
        })
        evts = self.runner.parse_stream_event(line)
        assert len(evts) == 2
        assert evts[0] == StreamEvent(type="token_delta", content="calling tool")
        assert evts[1] == StreamEvent(type="tool_call", tool_name="read", tool_args={"path": "/a"})

    def test_multi_block_thinking_and_text(self):
        line = json.dumps({
            "type": "assistant",
            "content": [
                {"type": "thinking", "text": "reasoning"},
                {"type": "text", "text": "answer"},
            ],
        })
        evts = self.runner.parse_stream_event(line)
        assert len(evts) == 2
        assert evts[0] == StreamEvent(type="thinking", is_thinking=True)
        assert evts[1] == StreamEvent(type="token_delta", content="answer")

    def test_multi_block_with_unknown_type_skipped(self):
        line = json.dumps({
            "type": "assistant",
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "unknown_block"},
                {"type": "tool_use", "name": "bash", "input": {}},
            ],
        })
        evts = self.runner.parse_stream_event(line)
        assert len(evts) == 2
        assert evts[0].type == "token_delta"
        assert evts[1].type == "tool_call"

    def test_multi_block_non_dict_block_skipped(self):
        line = json.dumps({
            "type": "assistant",
            "content": [
                "not a dict",
                {"type": "text", "text": "valid"},
            ],
        })
        evts = self.runner.parse_stream_event(line)
        assert evts == [StreamEvent(type="token_delta", content="valid")]


# -- CodexRunner: parse_stream_event -------------------------------------------

class TestCodexRunnerParseStreamEvent:
    def setup_method(self):
        self.runner = CodexRunner()

    def test_turn_started(self):
        line = json.dumps({"type": "turn.started"})
        evts = self.runner.parse_stream_event(line)
        assert evts == [StreamEvent(type="thinking", is_thinking=True)]

    def test_turn_completed(self):
        line = json.dumps({"type": "turn.completed"})
        evts = self.runner.parse_stream_event(line)
        assert evts == [StreamEvent(type="turn_complete", is_thinking=True)]

    def test_turn_failed(self):
        line = json.dumps({"type": "turn.failed"})
        evts = self.runner.parse_stream_event(line)
        assert evts == [StreamEvent(type="turn_complete", is_thinking=True)]

    def test_item_event_skipped(self):
        line = json.dumps({"type": "item.created"})
        assert self.runner.parse_stream_event(line) == []

    def test_invalid_json(self):
        assert self.runner.parse_stream_event("<<<not json>>>") == []


# -- GeminiRunner: parse_stream_event ------------------------------------------

class TestGeminiRunnerParseStreamEvent:
    def setup_method(self):
        self.runner = GeminiRunner(subagent_dir="/tmp/test-gemini")

    def test_message_delta(self):
        line = json.dumps({"type": "message", "content": "hello"})
        evts = self.runner.parse_stream_event(line)
        assert evts == [StreamEvent(type="token_delta", content="hello")]

    def test_tool_use(self):
        line = json.dumps({"type": "tool_use", "name": "read", "input": {"path": "/a"}})
        evts = self.runner.parse_stream_event(line)
        assert evts == [StreamEvent(type="tool_call", tool_name="read", tool_args={"path": "/a"})]

    def test_result_event(self):
        line = json.dumps({"type": "result"})
        evts = self.runner.parse_stream_event(line)
        assert evts == [StreamEvent(type="turn_complete")]

    def test_init_skipped(self):
        line = json.dumps({"type": "init"})
        assert self.runner.parse_stream_event(line) == []

    def test_invalid_json(self):
        assert self.runner.parse_stream_event("nope") == []


# -- ClaudeRunner: build_command -----------------------------------------------

class TestClaudeRunnerBuildCommand:
    def test_writes_mcp_config_and_returns_command(self, tmp_path):
        runner = ClaudeRunner(subagent_dir=str(tmp_path))
        cmd = runner.build_command("do stuff", "http://localhost:9000/mcp", None)

        config_path = tmp_path / "mcp-config.json"
        assert config_path.exists()
        written = json.loads(config_path.read_text("utf-8"))
        assert written["mcpServers"]["koan"]["url"] == "http://localhost:9000/mcp"
        assert written["mcpServers"]["koan"]["type"] == "http"

        assert "--mcp-config" in cmd
        assert "--output-format" in cmd
        assert "stream-json" in cmd
        assert "--model" not in cmd

    def test_model_appended_when_provided(self, tmp_path):
        runner = ClaudeRunner(subagent_dir=str(tmp_path))
        cmd = runner.build_command("do stuff", "http://localhost:9000/mcp", "claude-sonnet-4-5")
        assert cmd[-2:] == ["--model", "claude-sonnet-4-5"]


# -- CodexRunner: build_command ------------------------------------------------

class TestCodexRunnerBuildCommand:
    def test_command_contains_mcp_override(self):
        runner = CodexRunner()
        cmd = runner.build_command("do stuff", "http://localhost:9000/mcp", None)
        assert "-c" in cmd
        idx = cmd.index("-c")
        assert cmd[idx + 1] == "mcp_servers.koan.url=http://localhost:9000/mcp"


# -- GeminiRunner: build_command -----------------------------------------------

class TestGeminiRunnerBuildCommand:
    def test_writes_settings_json(self, tmp_path):
        runner = GeminiRunner(subagent_dir=str(tmp_path))
        cmd = runner.build_command("do stuff", "http://localhost:9000/mcp", None)

        settings = tmp_path / ".gemini" / "settings.json"
        assert settings.exists()
        written = json.loads(settings.read_text("utf-8"))
        assert written["mcpServers"]["koan"]["httpUrl"] == "http://localhost:9000/mcp"

        assert "--output-format" in cmd
        assert "stream-json" in cmd

    def test_merge_conflict_raises_runner_error(self, tmp_path):
        gemini_dir = tmp_path / ".gemini"
        gemini_dir.mkdir()
        settings = gemini_dir / "settings.json"
        settings.write_text(json.dumps({
            "mcpServers": {"koan": {"httpUrl": "http://other:1234/mcp"}},
        }))

        runner = GeminiRunner(subagent_dir=str(tmp_path))
        with pytest.raises(RunnerError) as exc_info:
            runner.build_command("do stuff", "http://localhost:9000/mcp", None)
        assert exc_info.value.diagnostic.code == "mcp_inject_failed"

    def test_non_object_toplevel_raises_runner_error(self, tmp_path):
        gemini_dir = tmp_path / ".gemini"
        gemini_dir.mkdir()
        settings = gemini_dir / "settings.json"
        settings.write_text(json.dumps([1, 2, 3]))

        runner = GeminiRunner(subagent_dir=str(tmp_path))
        with pytest.raises(RunnerError) as exc_info:
            runner.build_command("do stuff", "http://localhost:9000/mcp", None)
        diag = exc_info.value.diagnostic
        assert diag.code == "mcp_inject_failed"
        assert diag.runner == "gemini"
        assert "list" in diag.message

    def test_non_dict_mcp_servers_raises_runner_error(self, tmp_path):
        gemini_dir = tmp_path / ".gemini"
        gemini_dir.mkdir()
        settings = gemini_dir / "settings.json"
        settings.write_text(json.dumps({"mcpServers": "not-a-dict"}))

        runner = GeminiRunner(subagent_dir=str(tmp_path))
        with pytest.raises(RunnerError) as exc_info:
            runner.build_command("do stuff", "http://localhost:9000/mcp", None)
        diag = exc_info.value.diagnostic
        assert diag.code == "mcp_inject_failed"
        assert "mcpServers" in diag.message

    def test_non_dict_koan_entry_raises_runner_error(self, tmp_path):
        gemini_dir = tmp_path / ".gemini"
        gemini_dir.mkdir()
        settings = gemini_dir / "settings.json"
        settings.write_text(json.dumps({"mcpServers": {"koan": "a-string"}}))

        runner = GeminiRunner(subagent_dir=str(tmp_path))
        with pytest.raises(RunnerError) as exc_info:
            runner.build_command("do stuff", "http://localhost:9000/mcp", None)
        diag = exc_info.value.diagnostic
        assert diag.code == "mcp_inject_failed"
        assert "mcpServers.koan" in diag.message
