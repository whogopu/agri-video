"""dashboard/usage.py: Claude step attribution, pricing, transcript parsing, ps parsing."""

import json

from dashboard import usage

COSTS = {"claude_usd_per_mtok": {"claude-opus-5-5": {"input": 4.0, "output": 20.0, "cache_read": 0.20,
                                                      "cache_write_5m": 5.0, "cache_write_1h": 8.0}},
         "claude_web_search_usd_per_1k": 10.0}


def test_classify_tools():
    c = usage.classify_tool
    assert c("Read", {"file_path": "/r/episodes/2026-11-20-x/images/scene-03-s1.png"}) == "image_inspection"
    assert c("Read", {"file_path": "/r/episodes/2026-11-20-x/images/inspect/scene-03-s1-tl.png"}) == "image_inspection"
    assert c("Write", {"file_path": "/r/episodes/2026-11-20-x/script.md"}) == "script"
    assert c("Edit", {"file_path": "/r/episodes/2026-11-20-x/episode.json"}) is None   # inherits
    assert c("Edit", {"file_path": "/r/pipeline/images.py"}) == "dev"
    assert c("Bash", {"command": "uv run python -m pipeline.images episodes/x --scene 3 --inspect 1 --pass"}) == "image_inspection"
    assert c("Bash", {"command": "uv run python -m pipeline.render episodes/x --draft"}) == "render"
    assert c("Bash", {"command": "uv run pytest -q"}) == "dev"
    assert c("Bash", {"command": "ls episodes"}) is None
    assert c("Skill", {"skill": "hindi-script"}) == "script"
    assert c("Skill", {"skill": "make-episode"}) is None


def test_message_cost_matches_list_prices():
    u = {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000,
         "cache_creation_input_tokens": 2_000_000,
         "cache_creation": {"ephemeral_1h_input_tokens": 1_000_000, "ephemeral_5m_input_tokens": 1_000_000},
         "server_tool_use": {"web_search_requests": 1000}}
    assert abs(usage.message_cost("claude-opus-5-5", u, COSTS) - (4 + 20 + 0.2 + 8 + 5 + 10)) < 1e-9
    # unknown model falls back to the default model's prices
    assert usage.message_cost("claude-future-9", {"output_tokens": 1_000_000}, COSTS) == 20.0


def _assistant(mid, tools, usage_, ts="2026-11-20T10:00:00Z"):
    content = [{"type": "tool_use", "id": f"t{mid}{i}", "name": n, "input": inp} for i, (n, inp) in enumerate(tools)]
    return json.dumps({"type": "assistant", "timestamp": ts, "isSidechain": False,
                       "message": {"id": mid, "model": "claude-opus-5-5", "content": content, "usage": usage_}})


def test_transcript_attribution_and_incremental_read(tmp_path):
    eps = tmp_path / "episodes"
    (eps / "2026-11-20-demo").mkdir(parents=True)
    (eps / "2026-11-20-demo" / "episode.json").write_text("{}")
    tdir = tmp_path / "transcripts"
    tdir.mkdir()
    f = tdir / "s1.jsonl"
    u = {"output_tokens": 1_000_000}
    img = "/repo/episodes/2026-11-20-demo/images/scene-01-s1.png"
    f.write_text("\n".join([
        _assistant("m1", [("Read", {"file_path": img})], u),
        _assistant("m1", [], u),                    # same message streamed again: counted once
        _assistant("m2", [], u),                    # text only: inherits image_inspection + episode
        _assistant("m3", [("Edit", {"file_path": "/repo/pipeline/x.py"})], u),   # dev: no episode
        json.dumps({"type": "user", "message": {"content": "hi"}}),
    ]) + "\n")
    cu = usage.ClaudeUsage(tdir, eps)
    cu.costs = COSTS
    cu.refresh(0)
    recs = {r["ts"] + str(i): r for i, r in enumerate(cu.records())}
    assert len(recs) == 3
    by = {}
    for r in cu.records():
        by.setdefault((r["step"], r["episode"]), 0)
        by[(r["step"], r["episode"])] += r["usd"]
    assert by == {("image_inspection", "2026-11-20-demo"): 40.0, ("dev", None): 20.0}
    # append a new line → only the new bytes are read
    with open(f, "a") as fh:
        fh.write(_assistant("m4", [("Bash", {"command": "uv run python -m pipeline.narration episodes/2026-11-20-demo"})], u) + "\n")
    cu.refresh(0)
    assert sum(1 for r in cu.records() if r["step"] == "narration") == 1


def test_ps_time_and_components():
    assert usage._cpu_seconds("0:01.50") == 1.5
    assert usage._cpu_seconds("2:03.00") == 123.0
    assert usage._cpu_seconds("1:00:00.00") == 3600.0
    assert usage._cpu_seconds("1-00:00:01") == 86401.0
    assert usage.component("/x/mflux-generate-flux2 --prompt a") == "FLUX image model"
    assert usage.component("python /r/asr/asr_worker.py") == "Whisper scoring"
    assert usage.component("python /r/tts-mlx/snac_lm_worker.py") == "TTS voice model"
    assert usage.component("/x/chrome-headless-shell --type=renderer") == "Remotion browser (frames)"
    assert usage.SHELL_RE.match("/bin/zsh -c uv run python -m pipeline.images")
    assert not usage.SHELL_RE.match("uv run python -m pipeline.images")
    stage, ep, _ = usage.describe_cmd("uv run python -m pipeline.render episodes/2026-11-20-demo --draft")
    assert (stage, ep) == ("render_draft", "2026-11-20-demo")
