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


@pytest.fixture(autouse=True)
def _model_path_only(monkeypatch):
    monkeypatch.setenv("ENGAGENT_NO_RULES", "1")      # this module tests the language-model path


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
    out = assistant.ask("aluminium 6061 plate 80 mm, fixed at one end, 10 N down at the other", run=False)
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
                   "ea analyze last -m steel_s355 --fix xmin --force xmax 0,0,-500\n```"] * 3   # retries copy too
    out = assistant.ask("A bar 200 x 10 x 20 mm sticks out of a wall. How much does it bend?")
    assert out["kind"] == "question" and "material" in out["reply"] and "force" in out["reply"]
    assert "result" not in out                    # nothing was run


def test_cad_only_reply_to_an_analysis_question_asks_for_what_is_missing(llm):
    llm.replies = ["```bash\nea make beam length=200 width=10 height=20 --no-report\n```"]
    out = assistant.ask("A bar 200 x 10 x 20 mm is bolted to a wall at one end. How much does the free end bend?")
    assert out["kind"] == "results" and "followup" in out
    assert "material" in out["followup"] and "load" in out["followup"] and "how the part is held (for" not in out["followup"]


@pytest.mark.solver
def test_invented_values_are_corrected_from_the_users_words(llm):
    llm.replies = ["```bash\nea analyze beam length=200 width=10 height=20 -m steel_s355 --fix xmin --force xmax 0,0,-500 --quick\n```",
                   "```bash\nea analyze beam length=200 width=10 height=20 -m steel_generic --fix xmin --force xmax 0,0,-490.3 --quick\n```"]
    out = assistant.ask("A mild steel bar 200 x 10 x 20 mm is bolted to a wall at one end; "
                        "a 50 kg weight hangs from the free end. How much does it bend?")
    # corrected in code on the first attempt: no second model call needed
    assert out["kind"] == "results" and out["attempts"] == 1
    assert any("490.3 N" in c for c in out["corrections"]) and any("steel_generic" in c for c in out["corrections"])


@pytest.mark.solver
def test_needless_question_is_pushed_back_once(llm):
    llm.replies = ["What material did you mean by 'mild'?",
                   "```bash\nea analyze beam length=200 width=10 height=20 -m steel_generic --fix xmin --force xmax 0,0,-490.3 --quick\n```"]
    out = assistant.ask("A mild steel bar 200 x 10 x 20 mm is bolted to a wall at one end; a 50 kg weight hangs "
                        "from the free end. How much does it bend?")
    assert out["kind"] == "results" and out["attempts"] == 2
    assert "steel_generic" in llm.seen[1]["messages"][-1]["content"]


class FormOllama(FakeOllama):
    form: dict = {}

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.seen.append((self.path, body))
        form = FormOllama.form.pop(0) if isinstance(FormOllama.form, list) else FormOllama.form
        self._send({"message": {"role": "assistant", "content": json.dumps(form)}})


def _form_server(monkeypatch, tmp_path):
    try:
        srv = HTTPServer(("127.0.0.1", 11434), FormOllama)
    except OSError:
        pytest.skip("port 11434 is in use")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    for v in ("ENGAGENT_LLM_URL", "ENGAGENT_LLM_KEY", "ENGAGENT_LLM_MODEL"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("ENGAGENT_ROOT", str(tmp_path))
    monkeypatch.setenv("ENGAGENT_NO_RULES", "1")      # these tests exercise the model path
    return srv


@pytest.mark.solver
def test_local_model_fills_a_form_and_the_code_writes_the_request(monkeypatch, tmp_path):
    srv = _form_server(monkeypatch, tmp_path)
    try:
        FormOllama.form = {"action": "analyze", "template": "beam", "params": {"length": 200, "width": 10, "height": 20},
                           "material_words": "mild steel", "fixed_faces": ["xmin"],
                           "loads": [{"face": "xmax", "kind": "force", "direction": "-z", "magnitude": 50, "unit": "kg"}]}
        out = assistant.ask("Mild steel bar 200 x 10 x 20 mm bolted to a wall at one end; a 50 kg weight hangs from "
                            "the free end. How much does it bend?")
        assert out["kind"] == "results", out
        assert "--force xmax 0,0,-490.332" in out["request"] and "-m steel_generic" in out["request"]
        fea = out["result"]["jobs"][1]
        assert any("Hand calc" in l and "PASS" in l for l in fea["summary"])    # automatic beam check
        assert FakeOllama.seen[-1][1]["format"]["properties"]["action"]["enum"] == ["make", "analyze", "question"]
        # an invented magnitude is refused before anything runs
        FormOllama.form["loads"][0].update(magnitude=500, unit="N")
        out = assistant.ask("Mild steel bar 200 x 10 x 20 mm bolted to a wall at one end. How much does it bend?")
        assert out["kind"] == "question" and "500" in out["reply"]
    finally:
        srv.shutdown()
        srv.server_close()


def test_form_builds_thermal_and_thermal_stress_requests():
    from engagent import structured
    text = "Steel bar 100 mm long, one end held at 100 C, the other end in air at 20 C with h = 25. How hot is the middle?"
    form = {"action": "analyze", "template": "beam", "params": {"length": 100}, "analysis": "thermal",
            "material_words": "steel", "temperatures": [{"face": "xmin", "value": 100, "unit": "C"}],
            "convection": [{"face": "xmax", "h": 25, "ambient": 20, "unit": "C"}]}
    assert structured.magnitudes_from_user(form, text) == []
    req, q = structured.build_request(form, text)
    assert q is None and "-a thermal --temp xmin 100 --convect xmax 25 20" in req and "-m steel_generic" in req
    # Fahrenheit converted; an invented h refused
    textf = "aluminium plate, bottom at 212 F, top cooled by air at 68 F with h = 10"
    form = {"action": "analyze", "template": "plate", "analysis": "thermal", "material_words": "aluminium",
            "temperatures": [{"face": "zmin", "value": 212, "unit": "F"}],
            "convection": [{"face": "zmax", "h": 10, "ambient": 68, "unit": "F"}]}
    req, q = structured.build_request(form, textf)
    assert "--temp zmin 100 " in req and "--convect zmax 10 20" in req
    form["convection"][0]["h"] = 50
    assert any("50" in b for b in structured.magnitudes_from_user(form, textf))
    # nothing says how heat leaves -> a question, not a guess
    form.pop("convection")
    form["temperatures"] = []
    form["heat"] = [{"face": "zmin", "watts": 5}]
    req, q = structured.build_request(form, "aluminium plate with 5 W into the bottom")
    assert req is None and "heat leaves" in q
    # thermal stress
    texts = "PEEK plate clamped on both ends, cooled from 200 C to 20 C. Stress?"
    form = {"action": "analyze", "template": "plate", "analysis": "thermal_stress", "material_words": "peek",
            "fixed_faces": ["xmin", "xmax"], "temperature_change": {"start": 200, "end": 20, "unit": "C"}}
    req, q = structured.build_request(form, texts)
    assert q is None and "-a thermal_stress --fix xmin --fix xmax --t0 200 --dT 20" in req


@pytest.mark.solver
def test_local_model_thermal_end_to_end(monkeypatch, tmp_path):
    srv = _form_server(monkeypatch, tmp_path)
    try:
        FormOllama.form = {"action": "analyze", "template": "beam", "analysis": "thermal", "material_words": "steel",
                           "temperatures": [{"face": "xmin", "value": 100, "unit": "C"}],
                           "convection": [{"face": "xmax", "h": 25, "ambient": 20, "unit": "C"}]}
        out = assistant.ask("Steel bar, one end held at 100 C, the other end cooled by air at 20 C with h = 25. "
                            "How hot does the cooled end get?")
        assert out["kind"] == "results", out
        fea = out["result"]["jobs"][1]
        assert fea["verdict"] == "PASS", fea               # automatic 1-D checks: end temperature + heat flow
        assert sum("Hand calc" in l and "PASS" in l for l in fea["summary"]) == 2
    finally:
        srv.shutdown()


def test_needless_question_is_retried_with_a_forced_form(monkeypatch, tmp_path):
    srv = _form_server(monkeypatch, tmp_path)
    try:
        FormOllama.form = [
            {"action": "question", "question": "What temperature should the cooled end be held at?"},
            {"action": "analyze", "template": "beam", "analysis": "thermal", "material_words": "steel",
             "temperatures": [{"face": "xmin", "value": 100, "unit": "C"}],
             "convection": [{"face": "xmax", "h": 25, "ambient": 20, "unit": "C"}]}]
        text = ("Steel bar 100 mm long. One end is held at 100 C, the other end is cooled by air at 20 C with "
                "h = 25. How hot does the cooled end get?")
        out = assistant.ask(text, run=False)
        assert out["kind"] == "request" and out["attempts"] == 2, out
        assert "--temp xmin 100 --convect xmax 25 20" in out["request"]
        assert FakeOllama.seen[-1][1]["format"]["properties"]["action"]["enum"] == ["analyze"]
        # a real gap is still asked about, without a second model call
        FormOllama.form = [{"action": "question", "question": "Which material?"}]
        n = len(FakeOllama.seen)
        out = assistant.ask("A bar, one end at 100 C, air at 20 C. How hot is the other end?", run=False)
        assert out["kind"] == "question" and len(FakeOllama.seen) == n + 1
    finally:
        srv.shutdown()


def test_a_temperature_is_never_read_as_a_load():
    """Live issue #5: the model turned '100 C' into a 100 kg force; the numbers must match by kind."""
    from engagent import structured
    text = ("Steel bar 100 mm long. One end is held at 100 C, the other end is cooled by air at 20 C with "
            "h = 25. How hot does the cooled end get?")
    form = {"action": "analyze", "template": "beam", "params": {"length": 100}, "material_words": "steel",
            "fixed_faces": ["xmin"], "loads": [{"face": "xmax", "kind": "force", "direction": "-z",
                                                "magnitude": 100, "unit": "kg"}]}
    bad = structured.magnitudes_from_user(form, text)
    assert bad and "100 kg" in bad[0]
    assert structured.magnitudes_from_user(
        {"loads": [{"kind": "force", "magnitude": 50, "unit": "kg"}]}, "a 50 kg weight") == []
    assert structured.magnitudes_from_user(
        {"loads": [{"kind": "force", "magnitude": 2, "unit": "kN"}]}, "pulled with 2kN") == []
    assert structured.magnitudes_from_user(
        {"temperatures": [{"value": 212, "unit": "F"}]}, "held at 212°F") == []
    assert structured.magnitudes_from_user(
        {"temperatures": [{"value": 100, "unit": "C"}]}, "a 100 mm bar") != []      # a length is not a temperature


def test_time_budget_stops_model_calls(monkeypatch):
    """The issue bot gives each request a deadline: no model call starts after it (no silent 30-minute runs)."""
    import time as _t
    monkeypatch.setenv("ENGAGENT_LLM_URL", "http://127.0.0.1:9/never")
    monkeypatch.setenv("ENGAGENT_LLM_MODEL", "x")
    monkeypatch.setenv("ENGAGENT_DEADLINE", str(_t.time() + 5))
    t0 = _t.time()
    with pytest.raises(assistant.LLMError, match="in time"):
        assistant.complete([{"role": "user", "content": "hi"}])
    assert _t.time() - t0 < 5


def test_geometry_script_time_limit(monkeypatch, tmp_path):
    from engagent.cad.build import run_script
    script = tmp_path / "geometry.py"
    script.write_text("import time\ntime.sleep(30)\n")
    monkeypatch.setenv("ENGAGENT_SCRIPT_TIMEOUT", "1")
    with pytest.raises(RuntimeError, match="took longer than 1 s"):
        run_script(script)


class Busy(BaseHTTPRequestHandler):
    calls = 0
    fail_first = 0

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        Busy.calls += 1
        if Busy.calls <= Busy.fail_first:
            body = b'{"error": {"code": 503, "message": "high demand"}}'
            self.send_response(503)
        else:
            body = json.dumps({"choices": [{"message": {"role": "assistant", "content": "OK"}}]}).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_a_busy_provider_is_waited_out_within_the_budget(monkeypatch):
    """Live issue #18: Gemini answered 503 'high demand' for minutes; the bot must keep trying, not guess."""
    import time as _t
    srv = HTTPServer(("127.0.0.1", 0), Busy)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        Busy.calls, Busy.fail_first = 0, 7                      # more than one full round of tries
        monkeypatch.setenv("ENGAGENT_LLM_URL", f"http://127.0.0.1:{srv.server_port}/v1/chat/completions")
        monkeypatch.setenv("ENGAGENT_LLM_MODEL", "m1")
        monkeypatch.setenv("ENGAGENT_LLM_KEY", "k")
        monkeypatch.setenv("ENGAGENT_LLM_FALLBACK_MODELS", "m2")
        monkeypatch.setenv("ENGAGENT_DEADLINE", str(_t.time() + 3600))
        monkeypatch.setattr(assistant.time, "sleep", lambda s: None)
        assert assistant.complete([{"role": "user", "content": "hi"}]) == "OK"
        assert Busy.calls == 8
        # without a deadline (command line) there is one round only
        Busy.calls = 0
        monkeypatch.delenv("ENGAGENT_DEADLINE")
        with pytest.raises(assistant.LLMError):
            assistant.complete([{"role": "user", "content": "hi"}])
    finally:
        srv.shutdown()


def test_a_design_request_question_is_pushed_back(llm):
    """Benchmark 010: Gemini asked for a load on a pure 3D-print request; it gets one push to just design it."""
    llm.replies = ["What load should be applied to the clip?",
                   "Plan: a clip.\n```bash\nea make standoff --print petg --name clip\n```"]
    out = assistant.ask("A 3D-printable cable organizer clip in PETG for three 6 mm cables", run=False)
    assert out["kind"] == "request" and out["attempts"] == 2
    assert "no analysis was asked for" in llm.seen[-1]["messages"][-1]["content"]
