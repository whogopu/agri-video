"""Compare local inspection models on the labelled set, as one self-contained HTML page.

    uv run python -m pipeline.vlm_compare [RUN_DIR ...] [--out samples/vlm-eval/compare.html]

RUN_DIR is a folder under samples/vlm-eval/ holding a results.jsonl (default: every such folder).
The page shows a scoreboard per model, then every labelled shot: the image, Claude's verdict and note,
the user's marks from samples/vlm-eval/user-marks-*.txt, and each model's verdict with its MAJOR and
minor reasons, so you can see whether a model names the real problem, not just whether it said "fail".
Advisory tooling for the trial in pipeline/vlm_inspect.py; it never touches an episode.
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
from pathlib import Path

from pipeline import vlm_inspect as v

EVAL_DIR = v.EVAL_DIR


def load_results(run: Path) -> dict[str, dict]:
    res: dict[str, dict] = {}
    for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if not r.get("error"):
            res[r["id"]] = r
    return res


def load_user_marks() -> dict[str, list[tuple[str, str]]]:
    marks: dict[str, list[tuple[str, str]]] = {}
    for f in sorted(EVAL_DIR.glob("user-marks-*.txt")):
        for line in f.read_text(encoding="utf-8").splitlines():
            parts = [p.strip() for p in line.split("|", 2)]
            if len(parts) == 3 and not line.startswith("#"):
                marks.setdefault(parts[1], []).append((parts[0].upper(), parts[2]))
    return marks


def score(data: list[dict], shots: dict[str, dict], kinds: list[str] | None) -> dict | None:
    tp = fn = fp = tn = 0
    for d in data:
        s = shots.get(d["key"])
        if not s or not s["by_pass"]:
            continue
        bp = {k: f for k, f in s["by_pass"].items()
              if kinds is None or k in kinds or (k.startswith("identity") and "identity" in kinds)}
        if not bp:
            continue
        failed = any(bp.values())
        if d["label"] == "fail":
            tp += failed; fn += not failed
        else:
            fp += failed; tn += not failed
    if not tp + fn + fp + tn:
        return None
    return {"caught": tp, "fails": tp + fn, "wrong": fp, "goods": fp + tn}


def thumb(path: str, width: int = 720) -> str:
    from PIL import Image   # main env
    im = Image.open(path).convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=78)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def model_label(run: Path) -> str:
    n = run.name
    if n.endswith("-sev2"):
        return n[:-5] + " · major/minor"
    if "-sev" not in n:
        return n + " · v1 strict"
    return n


def reason_html(r: str) -> str:
    kind, _, rest = r.partition(": ")
    if rest.startswith("MAJOR: "):
        cls, text = "major", rest[7:]
    elif rest.startswith("minor: "):
        cls, text = "minor", rest[7:]
    else:   # v1 answers: every reason failed the shot
        cls, text = "v1", rest
    where = kind.replace("crop-", "zoom ").replace("identity-", "identity vs ")
    return f'<li class="{cls}"><span class="tag">{html.escape(where)}</span>{html.escape(text)}</li>'


def build(runs: list[Path], out: Path) -> Path:
    data = v.labelled_set()
    marks = load_user_marks()
    models = []
    for run in runs:
        res = load_results(run)
        shots = v.aggregate(res)
        done = [d for d in data if d["key"] in shots]
        models.append({"label": model_label(run), "shots": shots, "n": len(done),
                       "full": score(data, shots, ["full"]), "identity": score(data, shots, ["identity"]),
                       "all": score(data, shots, None)})

    def cell(sc):
        if not sc:
            return "<td>–</td><td>–</td>"
        good = sc["caught"] / max(sc["fails"], 1) >= 0.9
        ok_fp = sc["wrong"] / max(sc["goods"], 1) <= 0.25
        return (f'<td class="{"ok" if good else "bad"}">{sc["caught"]}/{sc["fails"]}</td>'
                f'<td class="{"ok" if ok_fp else "bad"}">{sc["wrong"]}/{sc["goods"]} '
                f'({100 * sc["wrong"] / max(sc["goods"], 1):.0f}%)</td>')

    rows = "".join(f'<tr><th>{html.escape(m["label"])}<div class="sub">{m["n"]} of {len(data)} shots done</div></th>'
                   f'{cell(m["all"])}{cell(m["full"])}{cell(m["identity"])}</tr>' for m in models)

    def card(d: dict) -> str:
        cols = []
        for m in models:
            s = m["shots"].get(d["key"])
            if not s:
                cols.append(f'<div class="mcol"><h4>{html.escape(m["label"])}</h4><p class="sub">not run yet</p></div>')
                continue
            verdict = "FAIL" if s["failed"] else "PASS"
            right = verdict.lower() == d["label"]
            reasons = sorted(s["reasons"], key=lambda r: (": MAJOR: " not in r, r))
            cols.append(f'<div class="mcol"><h4>{html.escape(m["label"])}</h4>'
                        f'<span class="v {verdict.lower()}">{verdict}</span> '
                        f'<span class="sub">{"matches Claude" if right else "differs from Claude"}</span>'
                        f'<ul class="reasons">{"".join(reason_html(r) for r in reasons) or "<li class=none>no issues</li>"}</ul></div>')
        um = marks.get(d["key"], [])
        um_html = ""
        if um:
            um_html = ('<details class="marks"><summary>Your marks on the v1 flaws (' +
                       ", ".join(f"{sum(1 for k, _ in um if k == t)} {t.lower()}" for t in ["MAJOR", "MINOR", "WRONG"]) +
                       ')</summary><ul>' + "".join(f'<li><b>{k.lower()}</b> {html.escape(t)}</li>' for k, t in um) +
                       "</ul></details>")
        lab = d["label"].upper()
        src = thumb(d["image"])
        return (f'<section class="card" data-label="{d["label"]}" '
                f'data-wrong="{" ".join(str(i) for i, m in enumerate(models) if m["shots"].get(d["key"]) and m["shots"][d["key"]]["failed"] != (d["label"] == "fail"))}">'
                f'<h3>{html.escape(d["key"])}</h3>'
                f'<div class="grid"><div><a href="#" class="zoom" data-src="{src}"><img src="{src}" alt="{html.escape(d["key"])}"></a>'
                f'<p><span class="v {lab.lower()}">Claude: {lab}</span></p>'
                f'<p class="note">{html.escape(d["notes"])}</p>{um_html}</div>'
                f'<div class="models">{"".join(cols)}</div></div></section>')

    fails = [d for d in data if d["label"] == "fail"]
    goods = [d for d in data if d["label"] == "pass"]
    opts = "".join(f'<option value="{i}">{html.escape(m["label"])}</option>' for i, m in enumerate(models))
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Local inspection models compared</title>
<style>
:root{{--bg:#f6f7f5;--card:#fff;--ink:#1d2420;--mut:#5d6862;--line:#dfe4e0;--ok:#0a6132;--okbg:#e3f4e8;--bad:#9b2c1f;--badbg:#fbe7e3;--minor:#7a5600;--minorbg:#fff3d6}}
@media (prefers-color-scheme:dark){{:root{{--bg:#121614;--card:#1b211e;--ink:#e6ece8;--mut:#9aa7a0;--line:#2c3530;--ok:#7fd99a;--okbg:#173322;--bad:#f2a091;--badbg:#3a1f1a;--minor:#f0c869;--minorbg:#3a3015}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:1280px;margin:0 auto;padding:16px}}h1{{font-size:22px;margin:8px 0}}h2{{font-size:18px;margin:28px 0 8px}}
.intro,.sub,.note{{color:var(--mut)}}.sub{{font-size:12px;font-weight:400}}
table{{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}}
th,td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;font-variant-numeric:tabular-nums}}thead th{{font-size:13px;color:var(--mut)}}
td.ok{{color:var(--ok);font-weight:600}}td.bad{{color:var(--bad);font-weight:600}}.tablewrap{{overflow-x:auto}}
.filters{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:12px 0}}select,label{{font:inherit}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:14px 0}}
.card h3{{font-size:14px;margin:0 0 8px;word-break:break-all}}.grid{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.3fr);gap:14px}}
.grid img{{width:100%;border-radius:6px;display:block;cursor:zoom-in}}.models{{display:grid;gap:10px}}
.mcol{{border:1px solid var(--line);border-radius:8px;padding:8px 10px}}.mcol h4{{margin:0 0 4px;font-size:13px}}
.v{{display:inline-block;padding:1px 9px;border-radius:99px;font-weight:600;font-size:12px}}.v.pass{{background:var(--okbg);color:var(--ok)}}.v.fail{{background:var(--badbg);color:var(--bad)}}
.reasons{{list-style:none;padding:0;margin:6px 0 0;font-size:13px}}.reasons li{{padding:3px 0 3px 8px;border-left:3px solid var(--line);margin:3px 0}}
.reasons li.major,.reasons li.v1{{border-color:var(--bad)}}.reasons li.minor{{border-color:var(--minor);color:var(--mut)}}
.tag{{font-size:11px;background:var(--line);padding:0 6px;border-radius:4px;margin-right:5px}}
.marks{{font-size:13px;color:var(--mut)}}.marks ul{{padding-left:18px}}
#lb{{position:fixed;inset:0;background:#000d;display:none;align-items:center;justify-content:center;z-index:9;cursor:zoom-out}}#lb img{{max-width:98vw;max-height:98vh}}
.hide{{display:none}}
@media (max-width:760px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>Local inspection models compared</h1>
<p class="intro">Each model judged the same {len(data)} shots ({len(fails)} that Claude failed, {len(goods)} that Claude passed). Green = meets the bar (catches ≥90% of failures; wrongly fails ≤25% of good shots).
In "major/minor" runs only <span style="color:var(--bad)">MAJOR</span> issues fail a shot; <span style="color:var(--minor)">minor</span> ones are listed only. In v1 runs every listed issue failed the shot. Click an image to enlarge.</p>
<div class="tablewrap"><table><thead><tr><th>Model</th><th>Fails caught (all questions)</th><th>Good shots wrongly failed (all)</th>
<th>Fails caught (full image only)</th><th>Wrongly failed (full only)</th><th>Fails caught (identity only)</th><th>Wrongly failed (identity only)</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<div class="filters"><label>Show only shots where <select id="m"><option value="">any model</option>{opts}</select> disagrees with Claude</label>
<label><input type="checkbox" id="only"> only disagreements</label></div>
<h2>Shots Claude failed ({len(fails)}): did each model name the real problem?</h2>
{"".join(card(d) for d in sorted(fails, key=lambda d: d["key"]))}
<h2>Shots Claude passed ({len(goods)})</h2>
{"".join(card(d) for d in sorted(goods, key=lambda d: d["key"]))}
</main><div id="lb"><img alt=""></div>
<script>
const lb=document.getElementById('lb');document.querySelectorAll('.zoom').forEach(a=>a.onclick=e=>{{e.preventDefault();lb.querySelector('img').src=a.dataset.src;lb.style.display='flex'}});lb.onclick=()=>lb.style.display='none';
const sel=document.getElementById('m'),only=document.getElementById('only');
function f(){{document.querySelectorAll('.card').forEach(c=>{{const w=c.dataset.wrong.split(' ').filter(Boolean);
const hit=sel.value===''?w.length>0:w.includes(sel.value);c.classList.toggle('hide',only.checked&&!hit)}})}}
sel.onchange=f;only.onchange=f;
</script></body></html>"""
    out.write_text(page, encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("runs", nargs="*", help="run folders under samples/vlm-eval/ (default: all with results.jsonl)")
    p.add_argument("--out", default=str(EVAL_DIR / "compare.html"))
    a = p.parse_args(argv)
    runs = [Path(r) for r in a.runs] or sorted(d for d in EVAL_DIR.iterdir() if (d / "results.jsonl").exists())
    out = build(runs, Path(a.out))
    print(f"{out} ({out.stat().st_size / 1e6:.1f} MB), models: {', '.join(r.name for r in runs)}")


if __name__ == "__main__":
    main()
