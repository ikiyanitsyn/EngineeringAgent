"""The plain-English loop, against a fake OpenAI-compatible server (no network, no key)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from engagent import assistant
from engagent.request import parse

BAD = "Plan: a plate.\n```bash\nea make plate length=80 --name bad\nea analyze last -m al_6061_t6 --fix plane:x=999 --force xmax 0,0,-10 --quick\n```"
GOOD = "Plan: a plate.\n```bash\nea make plate length=80 --name good\nea analyze last -m al_6061_t6 --fix xmin --force xmax 0,0,-10 --quick\n```"
QUESTION = "What material is the part made of, and where is it held?"


class Fake(BaseHTTPRequestHandler):
    replies: list = []
    seen: list = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.seen.append(body)
        reply = Fake.replies.pop(0)
        out = json.dumps({"choices": [{"message": {"role": "assistant", "content": reply}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


@pytest.fixture
def llm(monkeypatch, tmp_path):
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("ENGAGENT_LLM_URL", f"http://127.0.0.1:{srv.server_port}/v1/chat/completions")
    monkeypatch.setenv("ENGAGENT_LLM_MODEL", "fake")
    monkeypatch.setenv("ENGAGENT_ROOT", str(tmp_path))
    Fake.seen.clear()
    yield Fake
    srv.shutdown()


def test_question_is_returned_not_guessed(llm):
    llm.replies = [QUESTION]
    out = assistant.ask("analyse my bracket")
    assert out["kind"] == "question" and "material" in out["reply"]
    assert llm.seen[0]["messages"][0]["role"] == "system"
    assert "Never invent a load" in llm.seen[0]["messages"][0]["content"]


def test_dry_run_returns_request(llm):
    llm.replies = [GOOD]
    out = assistant.ask("a plate", run=False)
    assert out["kind"] == "request" and parse(out["request"])["commands"][0].startswith("make plate")


@pytest.mark.solver
def test_errors_are_fed_back_and_fixed(llm):
    llm.replies = [BAD, GOOD]
    out = assistant.ask("aluminium plate 80 mm, fixed at one end, 10 N down at the other")
    assert out["kind"] == "results" and out["attempts"] == 2
    feedback = llm.seen[1]["messages"][-1]["content"]
    assert "matched no CAD face" in feedback
    jobs = out["result"]["jobs"]
    assert [j["kind"] for j in jobs] == ["CAD", "FEA"] and jobs[1]["verdict"] in ("PASS", "REVIEW")


def test_missing_settings_are_explained(monkeypatch):
    monkeypatch.delenv("ENGAGENT_LLM_URL", raising=False)
    monkeypatch.delenv("ENGAGENT_LLM_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    with pytest.raises(assistant.LLMError, match="models: read"):
        assistant.complete([{"role": "user", "content": "hi"}])


class FakeOllama(BaseHTTPRequestHandler):
    seen: list = []

    def _send(self, obj):
        out = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        self._send({"models": [{"name": "llama3.2:3b"}, {"name": "qwen2.5-coder:7b"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.seen.append((self.path, body))
        self._send({"message": {"role": "assistant", "content": QUESTION}})

    def log_message(self, *a):
        pass


def test_local_ollama_is_used_without_any_settings(monkeypatch, tmp_path):
    try:
        srv = HTTPServer(("127.0.0.1", 11434), FakeOllama)
    except OSError:
        pytest.skip("port 11434 is in use (a real Ollama is running)")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    for v in ("ENGAGENT_LLM_URL", "ENGAGENT_LLM_KEY", "ENGAGENT_LLM_MODEL"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("ENGAGENT_ROOT", str(tmp_path))
    try:
        s = assistant.settings()
        assert s["model"] == "qwen2.5-coder:7b" and ":11434" in s["url"]   # preferred over llama3.2:3b
        out = assistant.ask("analyse my bracket")
        assert out["kind"] == "question"
        path, body = FakeOllama.seen[-1]
        assert path == "/api/chat" and body["options"]["num_ctx"] >= 8192 and body["stream"] is False
    finally:
        srv.shutdown()
        srv.server_close()


def test_model_that_copies_example_values_gets_a_question(llm):
    llm.replies = ["Plan: cantilever.\n```bash\nea make beam length=200 width=10 height=20\n"
                   "ea analyze last -m steel_s355 --fix xmin --force xmax 0,0,-500\n```"]
    out = assistant.ask("A bar 200 x 10 x 20 mm sticks out of a wall. How much does it bend?")
    assert out["kind"] == "question" and "material" in out["reply"] and "force" in out["reply"]
    assert "result" not in out                    # nothing was run
