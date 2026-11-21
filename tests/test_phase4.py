"""Phase 4: B-roll indexing and image-stage helpers (no model needed)."""

import json
import subprocess
import sys
from pathlib import Path

from pipeline.broll import entry_problems
from pipeline.images import default_seed, full_prompt

REPO = Path(__file__).parent.parent


def make_clip(path: Path, size: str = "640x360", secs: int = 3) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s={size}:r=25:d={secs}",
                    "-pix_fmt", "yuv420p", str(path)], check=True)


def broll(lib: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "pipeline.broll", *args, "--library", str(lib)],
                          cwd=REPO, capture_output=True, text=True)


def test_index_check_list(tmp_path: Path):
    lib = tmp_path / "broll"
    (lib / "clips").mkdir(parents=True)
    make_clip(lib / "clips" / "Wheat Field 01.mp4")
    make_clip(lib / "clips" / "tractor.mov", size="360x640")
    r = broll(lib, "index")
    assert r.returncode == 0, r.stderr
    idx = json.loads((lib / "index.json").read_text())
    ids = {c["id"]: c for c in idx["clips"]}
    assert set(ids) == {"wheat-field-01", "tractor"}
    assert ids["tractor"]["orientation"] == "portrait" and ids["wheat-field-01"]["duration_sec"] == 3.0
    assert (lib / "frames" / "wheat-field-01.jpg").exists()

    # stubs are incomplete → check fails, list marks them unusable
    assert broll(lib, "check").returncode == 1
    assert "INCOMPLETE" in broll(lib, "list").stdout

    # re-index is idempotent
    broll(lib, "index")
    assert len(json.loads((lib / "index.json").read_text())["clips"]) == 2

    # once filled in, the entry is usable
    c = ids["wheat-field-01"]
    c.update(description_en="wheat", description_hi="गेहूं", source="own footage", license="own",
             people_visible=False, tags={"crop": ["wheat"]})
    assert entry_problems(c, lib) == []


def test_image_helpers():
    cfg = {"style_suffix": "photorealistic"}
    assert full_prompt("A farmer in a field.", cfg) == "A farmer in a field, photorealistic"
    assert default_seed("ep", 1, 1) == default_seed("ep", 1, 1)
    assert default_seed("ep", 1, 1) != default_seed("ep", 1, 2)


def test_inspection_gate(tmp_path):
    """visuals_ready needs a passing inspection of the CURRENT image file."""
    import hashlib
    import shutil
    from PIL import Image
    from pipeline.schema import Status
    from pipeline.validate import validate

    fixture = Path(__file__).parent / "fixtures" / "sample-episode"
    ep = tmp_path / "ep"
    shutil.copytree(fixture, ep)
    (ep / "images").mkdir()
    img = ep / "images" / "scene-01.png"
    Image.new("RGB", (64, 36), "green").save(img)
    data = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
    data["scenes"][0]["image_file"] = "images/scene-01.png"

    def errors():
        (ep / "episode.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        rep, _ = validate(ep, Status.visuals_ready)
        return [e for e in rep.errors if e.startswith("scene 1 ")]

    assert any("not inspected" in e for e in errors())
    sha = hashlib.sha1(img.read_bytes()).hexdigest()
    data["scenes"][0]["visual"]["inspection"] = {"file_sha1": sha, "passed": False, "notes": "3 hands"}
    assert any("FAILED inspection" in e for e in errors())
    data["scenes"][0]["visual"]["inspection"]["passed"] = True
    assert not any("inspect" in e for e in errors())
    Image.new("RGB", (64, 36), "red").save(img)  # regenerated → old inspection no longer valid
    assert any("changed after its inspection" in e for e in errors())


def test_crops(tmp_path):
    from PIL import Image
    from pipeline.images import write_crops
    img = tmp_path / "scene-01.png"
    Image.new("RGB", (1344, 768), "white").save(img)
    crops = write_crops(img, tmp_path / "inspect")
    assert len(crops) == 4 and Image.open(crops[0]).size == (1612, 920)
