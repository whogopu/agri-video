"""Build narration_spoken (what TTS reads) from narration_display (what captions show).

    uv run python -m pipeline.text_normalize episodes/<id> [--scene N] [--force]
    uv run python -m pipeline.text_normalize --text "25 किलो DAP प्रति एकड़"

Order: pronunciation.yaml overrides → currency → ranges → percent → units → numbers.
Numbers become Hindi words in the Indian system (हज़ार, लाख, करोड़); .5/.25/.75 use the
forms farmers say (डेढ़, ढाई, साढ़े, सवा, पौने).
"""

from __future__ import annotations

import argparse
import re

from pipeline.common import (
    PRONUNCIATION_PATH, load_episode, load_yaml, resolve_episode_dir, save_episode,
    selected_scenes, setup_logging, stage_timer,
)

ONES = (
    "शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
    "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस "
    "पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस "
    "सैंतालीस अड़तालीस उनचास पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ "
    "इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर "
    "पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी "
    "अट्ठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे पंचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे"
).split()
assert len(ONES) == 100

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def int_to_words(n: int) -> str:
    if n < 0:
        return "माइनस " + int_to_words(-n)
    if n < 100:
        return ONES[n]
    parts: list[str] = []
    for value, name in ((10**7, "करोड़"), (10**5, "लाख"), (1000, "हज़ार"), (100, "सौ")):
        if n >= value:
            q, n = divmod(n, value)
            parts.append(f"{int_to_words(q)} {name}")
    if n:
        parts.append(ONES[n])
    return " ".join(parts)


def number_to_words(s: str) -> str:
    """'2500' → 'दो हज़ार पाँच सौ', '2.5' → 'ढाई', '3.5' → 'साढ़े तीन', '0.75' → 'पौन'."""
    s = s.replace(",", "")
    if "." not in s:
        return int_to_words(int(s))
    whole_s, frac_s = s.split(".", 1)
    whole = int(whole_s or "0")
    frac = frac_s.rstrip("0")
    if frac == "":
        return int_to_words(whole)
    if frac == "5":
        return {0: "आधा", 1: "डेढ़", 2: "ढाई"}.get(whole) or f"साढ़े {int_to_words(whole)}"
    if frac == "25":
        return {0: "चौथाई", 1: "सवा"}.get(whole) or f"सवा {int_to_words(whole)}"
    if frac == "75":
        return "पौन" if whole == 0 else f"पौने {int_to_words(whole + 1)}"
    return f"{int_to_words(whole)} दशमलव " + " ".join(ONES[int(d)] for d in frac)


NUM = r"\d+(?:,\d+)*(?:\.\d+)?"

# unit spellings (after a number) → spoken form. Longest first matters for the regex.
UNITS = {
    "kg": "किलो", "किग्रा": "किलो", "किलोग्राम": "किलो",
    "gm": "ग्राम", "g": "ग्राम", "ग्रा": "ग्राम",
    "ml": "एम एल", "मिली": "एम एल",
    "ltr": "लीटर", "l": "लीटर", "L": "लीटर",
    "cm": "सेंटीमीटर", "सेमी": "सेंटीमीटर",
    "mm": "मिलीमीटर", "मिमी": "मिलीमीटर",
    "m": "मीटर",
    "ha": "हेक्टेयर",
    "°C": "डिग्री सेल्सियस", "°": "डिग्री",
    "qtl": "क्विंटल", "q": "क्विंटल",
}
_unit_alt = "|".join(sorted((re.escape(u) for u in UNITS), key=len, reverse=True))
UNIT_RE = re.compile(rf"({NUM})\s?({_unit_alt})(?![A-Za-zऀ-ॿ])")
RANGE_RE = re.compile(rf"({NUM})\s?[-–—]\s?({NUM})")
CURRENCY_RE = re.compile(rf"(?:₹|रु\.?|Rs\.?)\s?({NUM})(?:\s?/-)?")
PERCENT_RE = re.compile(rf"({NUM})\s?%")
# "/" means प्रति only right after a unit (किलो/एकड़ → किलो प्रति एकड़); "लैब/योजना" is left alone
PER_UNITS = sorted(set(UNITS.values()) | {"रुपये", "रुपया", "पौधा", "पौधे", "एकड़", "बीघा", "दिन"}, key=len, reverse=True)
PER_RE = re.compile(rf"(?<![ऀ-ॿ])({'|'.join(map(re.escape, PER_UNITS))})\s?/\s?(?=[ऀ-ॿA-Za-z])")
NUM_RE = re.compile(NUM)


def apply_pronunciations(text: str, pron: dict[str, str]) -> str:
    for word in sorted(pron, key=len, reverse=True):
        text = re.sub(rf"(?<![\wऀ-ॿ]){re.escape(word)}(?![\wऀ-ॿ])", str(pron[word]), text)
    return text


def normalize(text: str, pron: dict[str, str] | None = None) -> str:
    t = text.translate(DEVANAGARI_DIGITS)
    t = apply_pronunciations(t, pron or {})
    t = CURRENCY_RE.sub(lambda m: f"{number_to_words(m[1])} रुपये", t)
    t = RANGE_RE.sub(lambda m: f"{number_to_words(m[1])} से {number_to_words(m[2])}", t)
    t = PERCENT_RE.sub(lambda m: f"{number_to_words(m[1])} प्रतिशत", t)
    t = UNIT_RE.sub(lambda m: f"{number_to_words(m[1])} {UNITS[m[2]]}", t)
    t = NUM_RE.sub(lambda m: number_to_words(m[0]), t)
    t = PER_RE.sub(lambda m: f"{m[1]} प्रति ", t)
    return re.sub(r"\s+", " ", t).strip()


def load_pronunciations() -> dict[str, str]:
    return {str(k): str(v) for k, v in (load_yaml(PRONUNCIATION_PATH) or {}).items()}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("episode", nargs="?")
    p.add_argument("--text", help="normalize this text and print it (no episode needed)")
    p.add_argument("--scene", type=int, action="append", dest="scenes")
    p.add_argument("--force", action="store_true", help="rebuild narration_spoken even if already set")
    args = p.parse_args()
    setup_logging()
    pron = load_pronunciations()
    if args.text:
        print(normalize(args.text, pron))
        return
    if not args.episode:
        p.error("give an episode folder or --text")

    ep_dir = resolve_episode_dir(args.episode)
    with stage_timer(ep_dir, "text_normalize") as run:
        ep = load_episode(ep_dir)
        changed = 0
        for s in selected_scenes(ep, args.scenes):
            if s.narration_spoken and not args.force:
                continue
            s.narration_spoken = normalize(s.narration_display, pron)
            changed += 1
            print(f"scene {s.id}: {s.narration_spoken}")
        save_episode(ep_dir, ep)
        run.note(f"narration_spoken built for {changed} scene(s)")


if __name__ == "__main__":
    main()
