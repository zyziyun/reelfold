"""Fact check for told pieces (a history / explainer narration): the AI drafter kept re-introducing claims nobody can
verify - the Elliott Bay film said "one of the West Coast's largest grain terminals", "Seattle's busiest rail yard",
"among the West Coast's largest" (and the same in 中文: 最大的…之一, 最繁忙的, 位列前列) although its prompt said
"only well-known, verifiable facts". A prompt is a wish; this pass is the rule.

1. One routed AI call (``complete("planner", ...)``, JSON) lists every factual claim of the cue lines: cue index,
   claim, kind (superlative | ranking | date | number | name | event | general), confidence 0-1, source_type
   (encyclopedic | official | well-known | local-knowledge | unverifiable) and the line rewritten without the
   unverifiable part (softened_en / softened_zh).
2. Deterministic rules decide - never the model alone:
   - a superlative / ranking ("largest", "busiest", "one of the …est", 最大, 最繁忙, 第一, 唯一, 前列 …) is kept only
     with confidence >= 0.9 AND an encyclopedic / official source; else softened;
   - a date / number below 0.7 (or unverifiable) is softened: the number goes;
   - any other claim below 0.5 or unverifiable: its cue is dropped when its unit keeps another cue, else softened;
   - the word scan (``scan``) runs on every cue after the model's claims too: a superlative the model did not list
     is softened as unverified.
   Softening takes the model's line when it is valid (no superlative / no number left, not longer); else a word-rule
   fallback strips the phrase (en and 中文) keeping the sentence grammatical as far as reasonable. Both languages of
   a cue pair change together.
3. No AI (provider none, an error, a reply without a claim list): the word scan alone softens superlatives, and
   facts.md says the AI check did not run.

    from vstudio import factguard as FG
    res = FG.check([("At Pier 86 stands one of the West Coast's largest grain terminals.", "…之一。")],
                   request="a history of the waterfront", complete=fake)
    new_text, res = FG.check_spec(spec_text, request, complete=fake)    # photo-story spec.py: only cue literals change
    FG.write_facts(path, res, lang="en")                                # facts.md she reviews before posting
"""
import ast
import os
import re

KINDS = ("superlative", "ranking", "date", "number", "name", "event", "general")
SOURCES = ("encyclopedic", "official", "well-known", "local-knowledge", "unverifiable")
STRONG = 0.9              # a superlative stays only this sure AND from an encyclopedic / official source
WEAK = 0.5                # below this (or unverifiable) a claim is not kept as it is
NUM_SURE = 0.7            # a date / number below this loses the number

# --------------------------------------------------------------------------- the word scan (en + 中文)
_EST = (r"(?:largest|biggest|busiest|oldest|longest|tallest|highest|greatest|deepest|widest|earliest|richest|"
        r"finest|newest|smallest|best|(?:most|least)\s+[a-z]+)")
_BASE = {"largest": "large", "biggest": "big", "busiest": "busy", "oldest": "old", "longest": "long",
         "tallest": "tall", "highest": "high", "greatest": "great", "deepest": "deep", "widest": "wide",
         "earliest": "early", "richest": "rich", "finest": "fine", "newest": "new", "smallest": "small", "best": "good"}
_FIRST_OK = r"(?!\s+(?:step|time|thing|part|half|question|idea|line|look|of all|place to start))"
SUPER_EN = re.compile(
    r"\b(?:largest|biggest|busiest|oldest|longest|tallest|highest|greatest|deepest|earliest|richest)\b|"
    r"\b(?:the|its|their|[\w.]+['’]s)\s+(?:very\s+)?(?:most|least)\s+[a-z]{3,}|"
    r"\b(?:the|its|their|[\w.]+['’]s)\s+(?:very\s+)?best\b|"
    r"\b(?:the|its|their|[\w.]+['’]s)\s+(?:very\s+)?first\b" + _FIRST_OK + r"|\bfirst[- ]ever\b|"
    r"\b(?:the|its|their|[\w.]+['’]s)\s+only\b|\bone of (?:the|its)\b[^.,;]{0,40}?\b" + _EST + r"\b|"
    r"\bamong the\b[^.,;]{0,40}?\b" + _EST + r"\b|\bleading\b|\bthe top\b(?!\s+of)|\btop[- ](?:\d+|ten|five|three)\b|"
    r"\bnumber one\b|\bunrivall?ed\b|\bunmatched\b|\bunparalleled\b|\brecord[- ]breaking\b|\bworld[- ]class\b",
    re.I)
SUPER_ZH = re.compile(r"最(?![后终近初好先])[\u4e00-\u9fff]|第一(?![次步天眼章节段])|首(?:个|座|家|条|位|批|所)|唯一|前列|前茅|之最|"
                      r"首屈一指|数一数二|龙头|领先")
_YEAR = re.compile(r"\d{3,4}")


def scan(text):
    """The superlative / ranking words in a line (en + 中文) -> [matched text]; markdown ``**`` ignored."""
    t = str(text or "").replace("**", "")
    return [m.group(0) for m in SUPER_EN.finditer(t)] + [m.group(0) for m in SUPER_ZH.finditer(t)]


def is_told(text):
    """A told piece - history, an explainer, a documentary - by the words that make vstudio.narration narrate it
    (``_TOLD``) or the brain's "history-explainer" template words."""
    from vstudio import narration as N
    from vstudio.brain import template as T
    t = str(text or "")
    return bool(N._TOLD.search(t) or re.search(T.WORDS["history-explainer"][0], t.lower()))


# --------------------------------------------------------------------------- word-rule softening
def _article(word):
    return "an" if re.match(r"[aeiouAEIOU]", word or "") else "a"


def _singular(noun):
    w = noun.split()
    if w and len(w[-1]) > 3 and w[-1].endswith("s") and not w[-1].endswith("ss"):
        w[-1] = w[-1][:-3] + "y" if w[-1].endswith("ies") else w[-1][:-1]
    return " ".join(w)


def _base(est):
    e = re.sub(r"\s+", " ", est.lower())
    if e.startswith(("most ", "least ")):
        return e.split(" ", 1)[1]
    return _BASE.get(e, "")


def _tidy_en(s):
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\s+([.,;:!?])", r"\1", s)
    s = re.sub(r",\s*([.;])", r"\1", s)
    return s.strip()


_OWNER = (r"(?:(?:the\s+)?(?:[A-Z][\w.]*\s+){0,3}[A-Z][\w.]*['’]s|(?:the\s+)?(?:world|nation|country|city|region|"
          r"state)['’]s|the|its|their)")


def soften_en(s):
    """An English line without its superlatives / rankings (word rules; the model's own line is preferred):
    "one of the West Coast's largest grain terminals" -> "a large grain terminal", "Seattle's busiest rail yard" ->
    "a busy rail yard", "is among the West Coast's largest" -> "is large", "the first" -> "an early"."""
    t = str(s or "")
    noun = r"((?:\*\*)?[a-z][\w-]*(?:\s+(?!and\b|in\b|on\b|of\b|with\b|at\b)[a-z][\w-]*){0,2}(?:\*\*)?)"

    def one_of(m):
        b, n = _base(m.group(1)), m.group(2)
        if n:
            phrase = f"{b} {_singular(n)}".strip()
            return f"{_article(phrase)} {phrase}"
        return b
    t = re.sub(r"\b(?:one of|among|some of)\s+(?:" + _OWNER + r"\s+)?(?:very\s+)?(" + _EST + r")\b(?:\s+" + noun
               + r")?", one_of, t, flags=re.I)

    def owner_est(m):
        b = _base(m.group(1))
        if m.group(2):                     # a word follows: "Seattle's busiest rail yard" -> "a busy rail yard"
            return f"{_article(b)} {b} " if b else "a "
        return b
    t = re.sub(r"\b" + _OWNER + r"\s+(?:very\s+)?(" + _EST + r")\b(\s+(?=[A-Za-z*]))?", owner_est, t)
    t = re.sub(r"\b" + _OWNER + r"\s+(?:very\s+)?first\b" + _FIRST_OK + r"\s*", "an early ", t)
    t = re.sub(r"\bfirst[- ]ever\s+", "", t, flags=re.I)
    t = re.sub(r"\b" + _OWNER + r"\s+only\s+", "a ", t)
    t = re.sub(r"\b(?:leading|top|number one|unrivall?ed|unmatched|unparalleled|record[- ]breaking|world[- ]class)"
               r"\s+", "", t, flags=re.I)
    t = re.sub(r"\b(largest|biggest|busiest|oldest|longest|tallest|highest|greatest|deepest|earliest|richest)\b",
               lambda m: _base(m.group(1)), t, flags=re.I)
    t = re.sub(r"\ba(?= [aeiouAEIOU])", "an", t)
    t = re.sub(r"\ban(?= [^aeiouAEIOU\s*])", "a", t)
    return _tidy_en(t)


_ZH_ADJ = {"大": "大型", "早": "早期的", "老": "古老的", "古老": "古老的", "繁忙": "繁忙的", "忙碌": "忙碌的",
           "高": "高大的", "长": "很长的"}


def soften_zh(s):
    """A 中文 line without its superlatives / rankings (word rules; the model's own line is preferred)."""
    t = str(s or "")
    t = re.sub(r"[，,]?\s*(?:位列|跻身|名列|进入|位居)[^，。；,;!?！？]{0,12}?(?:前列|前茅|之列)", "", t)

    def zui_de(m):
        adj = m.group(1)
        return _ZH_ADJ.get(adj, "很" + adj + "的")
    before = t
    t = re.sub(r"(?:(?<=[，,。：:是为着在、\s*])|^)(?:[\u4e00-\u9fff]{2,4})?最([\u4e00-\u9fff]{1,2}?)的", zui_de, t)
    if t != before:
        t = re.sub(r"之一(?=[。，；！？,.;!?*]|$)", "", t)
    t = re.sub(r"最(?![后终近初好先])(?=[\u4e00-\u9fff])", "很", t)
    t = re.sub(r"(?:第一|首)(?:座|个|家|条|位|批|所)", "早期的", t)
    t = re.sub(r"唯一的?|之最|首屈一指的?|数一数二的?|龙头|领先的?", "", t)
    t = re.sub(r"[，,]{2,}", "，", t)
    t = re.sub(r"[，,]+(?=[。；！？.!?])", "", t)
    return t.strip()


def strip_numbers_en(s):
    t = str(s or "")
    t = re.sub(r"\s*,?\s*\b(?:in|since|by|around|from|until|circa|c\.)\s+(?:the\s+)?(?:early\s+|late\s+|mid-?)?"
               r"\**\d{3,4}s?\**", "", t, flags=re.I)
    t = re.sub(r"\b(?:over|about|nearly|almost|more than|some|around|roughly)?\s*\**\d[\d,.]*\**(?=\s+[a-z])",
               "many", t, flags=re.I)
    return _tidy_en(t)


def strip_numbers_zh(s):
    t = str(s or "")
    t = re.sub(r"(?:自|从|在|于)?\**(?:\d{1,2}世纪)?\d{2,4}年代?(?:末|初|中期)?\**(?:起|以来|时|间)?[，,]?", "", t)
    t = re.sub(r"(?:逾|超过|约|近|大约)?\d[\d,.]*多?(?=[个座条家艘名位万千百])", "多", t)
    return t.strip()


# --------------------------------------------------------------------------- the AI pass
SYSTEM = (
    "You fact-check the narration of a history / explainer video. List every factual claim in the numbered lines: "
    "superlatives and rankings (largest, busiest, oldest, first, only, one of the ...est, 最大, 最繁忙, 第一, 唯一, "
    "之一, 前列), dates, numbers, names and events. For each: how sure you are it is true (confidence 0-1) and where "
    "it would be confirmed (source_type: encyclopedic = in a general encyclopedia; official = the operator's / a "
    "government's own records; well-known; local-knowledge; unverifiable). Also rewrite the line without the "
    "unverifiable part: same meaning otherwise, same length or shorter, no new facts (softened_en, softened_zh; "
    "leave one empty when the line has no such language). Be strict: a ranking you cannot name a source for is "
    "unverifiable. Reply with JSON only: {\"claims\": [{\"cue\": <line number>, \"claim\": \"...\", \"kind\": "
    "\"superlative|ranking|date|number|name|event|general\", \"confidence\": 0.0, \"source_type\": \"...\", "
    "\"softened_en\": \"...\", \"softened_zh\": \"...\"}]}.")


def _norm_cues(cues, units=None):
    out = []
    for i, c in enumerate(cues or []):
        if isinstance(c, dict):
            en, zh, u = c.get("en"), c.get("zh"), c.get("unit", i)
        elif isinstance(c, (list, tuple)):
            en, zh, u = (c[0] if len(c) > 0 else None), (c[1] if len(c) > 1 else None), i
        else:
            en, zh, u = str(c), None, i
        if units is not None and i < len(units):
            u = units[i]
        out.append(dict(i=i, unit=u, en=en, zh=zh, single=not isinstance(c, (list, tuple, dict))))
    return out


def _ask(cues, request, complete):
    """-> (claims, provider, note): note says why the AI check did not run (None when it ran)."""
    if complete is None:
        from vstudio import llm
        complete = llm.complete
    lines = []
    for c in cues:
        bits = [f"EN: {c['en']}" if c["en"] else "", f"中文: {c['zh']}" if c["zh"] else ""]
        lines.append(f"[{c['i']}] " + " | ".join(b for b in bits if b))
    body = (f"Topic / request: {request or '(none)'}\n\nLines:\n" + "\n".join(lines))
    try:
        r = complete("planner", SYSTEM, body, schema=True, max_tokens=6000, timeout=300, cli_timeout=300,
                     retries=1, effort="low")
    except Exception as e:  # noqa: BLE001  (no model / a failed call: the word rules still run)
        return None, None, f"the AI call failed ({type(e).__name__})"
    if not isinstance(r, dict) or r.get("provider") == "none":
        return None, None, "no AI model is set up"
    js = r.get("json") if isinstance(r.get("json"), dict) else {}
    if not isinstance(js.get("claims"), list):
        return None, r.get("provider"), "the AI reply had no list of claims"
    return [c for c in js["claims"] if isinstance(c, dict)], r.get("provider"), None


def _num(v, default=0.0):
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return default


def _valid(new, old, kind):
    """The model's softened line is used only when it is a real line, not longer, and free of what it had to lose."""
    if not isinstance(new, str) or not new.strip() or not old:
        return False
    if len(new) > len(old) * 1.1 + 6 or new.strip() == old.strip():
        return False
    if scan(new):
        return False
    if kind in ("date", "number") and _YEAR.search(new.replace("**", "")) and \
            set(_YEAR.findall(new)) & set(_YEAR.findall(old)):
        return False
    return True


def _fallback(text, kind, lang):
    if not text:
        return text
    if kind in ("date", "number"):
        return strip_numbers_zh(text) if lang == "zh" else strip_numbers_en(text)
    return soften_zh(text) if lang == "zh" else soften_en(text)


def _lang_of(text):
    return "zh" if re.search(r"[\u4e00-\u9fff]", str(text or "")) else "en"


def _soften(cue, kind, soft_en=None, soft_zh=None):
    """(en, zh) of the cue softened: the model's line when valid, else the word rules. Both languages together."""
    out = {}
    for key, soft in (("en", soft_en), ("zh", soft_zh)):
        cur = cue[key]
        if not cur:
            out[key] = cur
            continue
        lang = "zh" if key == "zh" else _lang_of(cur) if cue["single"] else "en"
        if cue["single"] and lang == "zh" and not _valid(soft, cur, kind):
            soft = soft_zh
        out[key] = soft.strip() if _valid(soft, cur, kind) else _fallback(cur, kind, lang)
    return out["en"], out["zh"]


def check(cues, request="", complete=None, units=None, use_ai=True):
    """The fact check of cue lines (module doc) -> {ai, ai_note, provider, claims [...], cues [(en, zh) | None
    (dropped)], checked, softened, dropped, kept}. ``cues``: (en, zh) pairs, single lines or {en, zh, unit} dicts;
    ``units``: the unit (section) of each cue - a cue is dropped only when its unit keeps another one."""
    cs = _norm_cues(cues, units)
    claims, provider, note = (_ask(cs, request, complete) if use_ai and cs else (None, None, "not asked"))
    ai = claims is not None
    alive = {}
    for c in cs:
        alive[c["unit"]] = alive.get(c["unit"], 0) + 1
    out, kept_strong = [], set()
    by_cue = {}
    for cl in claims or []:
        try:
            i = int(cl.get("cue"))
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(cs):
            by_cue.setdefault(i, []).append(cl)
    for c in cs:
        for cl in by_cue.get(c["i"], []):
            kind = str(cl.get("kind") or "general").lower()
            kind = kind if kind in KINDS else "general"
            conf = _num(cl.get("confidence"))
            src = str(cl.get("source_type") or "unverifiable").lower()
            src = src if src in SOURCES else "unverifiable"
            text = str(cl.get("claim") or "")[:300]
            sup = kind in ("superlative", "ranking") or bool(scan(text))
            strong = conf >= STRONG and src in ("encyclopedic", "official")
            weak = conf < WEAK or src == "unverifiable"
            before = (c["en"], c["zh"])
            rec = dict(cue=c["i"], unit=c["unit"], claim=text, kind="superlative" if sup and kind not in (
                "superlative", "ranking") else kind, confidence=conf, source_type=src, by="ai", before=before)
            if c.get("dropped"):
                rec.update(decision="dropped", after=None, why="its line was dropped for another claim")
                out.append(rec)
                continue
            if sup:
                decision = "kept" if strong else "softened"
                if strong:
                    kept_strong.add(c["i"])
            elif kind in ("date", "number"):
                decision = "softened" if (conf < NUM_SURE or src == "unverifiable") else "kept"
            elif weak:
                decision = "dropped" if alive[c["unit"]] > 1 else "softened"
            else:
                decision = "kept"
            if decision == "dropped":
                c["dropped"] = True
                alive[c["unit"]] -= 1
                rec.update(decision="dropped", after=None)
            elif decision == "softened":
                en, zh = _soften(c, "superlative" if sup else kind, cl.get("softened_en"), cl.get("softened_zh"))
                if (en, zh) == before:
                    rec.update(decision="flagged", after=None,
                               why="could not be softened safely: check it yourself")
                else:
                    c["en"], c["zh"] = en, zh
                    rec.update(decision="softened", after=(en, zh))
            else:
                rec.update(decision="kept", after=None)
            out.append(rec)
    for c in cs:                         # the word scan, after the model: a superlative it did not list still goes
        if c.get("dropped") or c["i"] in kept_strong:
            continue
        hits = scan(c["en"]) + scan(c["zh"])
        if not hits:
            continue
        before = (c["en"], c["zh"])
        en, zh = _soften(c, "superlative")
        rec = dict(cue=c["i"], unit=c["unit"], claim=", ".join(dict.fromkeys(hits)), kind="superlative",
                   confidence=None, source_type="unverifiable", by="words", before=before)
        if (en, zh) == before:
            rec.update(decision="flagged", after=None, why="could not be softened safely: check it yourself")
        else:
            c["en"], c["zh"] = en, zh
            rec.update(decision="softened", after=(en, zh))
        out.append(rec)
    res_cues = [None if c.get("dropped") else (c["en"] if c["single"] else (c["en"], c["zh"])) for c in cs]
    n = {k: sum(1 for r in out if r["decision"] == k) for k in ("kept", "softened", "dropped", "flagged")}
    return dict(ai=ai, ai_note=note if not ai else None, provider=provider, claims=out, cues=res_cues,
                checked=len(cs), **n)


# --------------------------------------------------------------------------- the photo-story spec
def spec_cues(text):
    """The cue literals of a spec's SCRIPT -> [{unit, en, zh, node, en_node, zh_node, elts}] (ast nodes, so only
    those literals are rewritten), or [] when the spec has no SCRIPT of the usual shape."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    for st in tree.body:
        if not (isinstance(st, ast.Assign) and isinstance(st.targets[0], ast.Name) and st.targets[0].id == "SCRIPT"
                and isinstance(st.value, (ast.List, ast.Tuple))):
            continue
        out = []
        for u, unit in enumerate(st.value.elts):
            if not (isinstance(unit, (ast.Tuple, ast.List)) and len(unit.elts) > 1 and
                    isinstance(unit.elts[1], (ast.List, ast.Tuple))):
                continue
            elts = unit.elts[1].elts
            for k, e in enumerate(elts):
                if isinstance(e, ast.Tuple) and e.elts and all(
                        isinstance(x, ast.Constant) and isinstance(x.value, str) for x in e.elts[:2]):
                    out.append(dict(unit=u, en=e.elts[0].value, zh=e.elts[1].value if len(e.elts) > 1 else None,
                                    node=e, en_node=e.elts[0], zh_node=e.elts[1] if len(e.elts) > 1 else None,
                                    elts=elts, k=k, pair=True))
                elif isinstance(e, ast.Constant) and isinstance(e.value, str):
                    out.append(dict(unit=u, en=e.value, zh=None, node=e, en_node=e, zh_node=None, elts=elts, k=k,
                                    pair=False))
        return out
    return []


def _lit(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def apply_spec(text, found, new_cues):
    """``text`` with the cue literals in ``found`` (spec_cues) replaced by ``new_cues`` ((en, zh) / str / None =
    drop the cue); every other byte unchanged. ast columns are UTF-8 byte offsets: the edit is done on bytes."""
    raw = text.encode("utf-8")
    starts, pos = [], 0
    for ln in raw.split(b"\n"):
        starts.append(pos)
        pos += len(ln) + 1

    def off(line, col):
        return starts[line - 1] + col
    edits = []
    for f, new in zip(found, new_cues):
        old = (f["en"], f["zh"]) if f["pair"] else f["en"]
        if new == old:
            continue
        if new is None:
            node, elts, k = f["node"], f["elts"], f["k"]
            if k + 1 < len(elts):
                a, b = off(node.lineno, node.col_offset), off(elts[k + 1].lineno, elts[k + 1].col_offset)
            elif k > 0:
                a, b = off(elts[k - 1].end_lineno, elts[k - 1].end_col_offset), \
                    off(node.end_lineno, node.end_col_offset)
            else:
                continue                      # never empty a unit
            edits.append((a, b, b""))
            continue
        en, zh = (new if f["pair"] else (new, None))
        for nd, val, was in ((f["en_node"], en, f["en"]), (f["zh_node"], zh, f["zh"])):
            if nd is not None and val is not None and val != was:
                edits.append((off(nd.lineno, nd.col_offset), off(nd.end_lineno, nd.end_col_offset),
                              _lit(val).encode("utf-8")))
    for a, b, rep in sorted(edits, key=lambda e: e[0], reverse=True):
        raw = raw[:a] + rep + raw[b:]
    return raw.decode("utf-8")


def check_spec(text, request="", complete=None, use_ai=True):
    """A photo-story spec's SCRIPT fact-checked -> (new text, check result). Only the cue literals change; a result
    that would not stay a plain-data module keeps the original text (``res["error"]``)."""
    found = spec_cues(text)
    if not found:
        return text, dict(ai=False, ai_note="no SCRIPT cues found", provider=None, claims=[], cues=[], checked=0,
                          kept=0, softened=0, dropped=0, flagged=0)
    res = check([dict(en=f["en"], zh=f["zh"], unit=f["unit"]) if f["pair"] else f["en"] for f in found],
                request, complete, units=[f["unit"] for f in found], use_ai=use_ai)
    new = apply_spec(text, found, res["cues"])
    from vstudio.project.drafts import data_module_ok
    if not data_module_ok(new):
        res["error"] = "the checked spec did not stay plain data; the draft was kept unchanged"
        return text, res
    return new, res


# --------------------------------------------------------------------------- the explainer's SCRIPT.md
_LINE_HEAD = re.compile(r"^## Line \d+")


def script_cues(text):
    """An explainer SCRIPT.md -> [{line, en (the indented narration), zh (its ZH: line), spans}] - one cue per
    '## Line N' block (its own unit: never dropped, only softened)."""
    rows, cur = [], None
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        if _LINE_HEAD.match(ln):
            cur = dict(head=i, narr=[], zh=None)
            rows.append(cur)
        elif cur is not None:
            if ln.startswith("    ") and ln.strip() and cur["zh"] is None:
                if cur["narr"] and cur["narr"][-1] != i - 1:
                    continue                      # a second indented block after a gap: not narration
                cur["narr"].append(i)
            elif ln.startswith("ZH:") and cur["zh"] is None:
                cur["zh"] = i
    out = []
    for r in rows:
        if not r["narr"]:
            continue
        en = " ".join(lines[i].strip() for i in r["narr"])
        zh = lines[r["zh"]][3:].strip() if r["zh"] is not None else None
        out.append(dict(narr=r["narr"], zh_line=r["zh"], en=en, zh=zh))
    return out


def check_script(text, request="", complete=None, use_ai=True):
    """An explainer SCRIPT.md fact-checked -> (new text, result): a Line's narration block becomes one line, its
    ZH: line is rewritten; every other line unchanged. Each Line is its own unit, so nothing is dropped."""
    found = script_cues(text)
    if not found:
        return text, dict(ai=False, ai_note="no script lines found", provider=None, claims=[], cues=[], checked=0,
                          kept=0, softened=0, dropped=0, flagged=0)
    res = check([(f["en"], f["zh"]) if f["zh"] is not None else f["en"] for f in found], request, complete,
                units=list(range(len(found))), use_ai=use_ai)
    lines = text.split("\n")
    drop = set()
    for f, new in zip(found, res["cues"]):
        if new is None:
            continue
        en, zh = new if isinstance(new, tuple) else (new, None)
        if en != f["en"]:
            lines[f["narr"][0]] = "    " + en
            drop.update(f["narr"][1:])
        if zh is not None and f["zh_line"] is not None and zh != f["zh"]:
            lines[f["zh_line"]] = "ZH: " + zh
    return "\n".join(ln for i, ln in enumerate(lines) if i not in drop), res


# --------------------------------------------------------------------------- facts.md
def _fmt(pair):
    if pair is None:
        return "-"
    if isinstance(pair, (list, tuple)):
        return " / ".join(str(x) for x in pair if x)
    return str(pair)


_WORDS = {
    "en": dict(title="Fact check", intro="Claims in the narration and what the fact check did with them. Review "
               "this before posting: a softened or dropped line can be put back if you have a source.",
               ai="Checked by the AI ({p}) and the word rules.", noai="The AI check did not run ({why}): only "
               "the word rules softened rankings like 'largest' or 'busiest'. Check the dates and numbers yourself.",
               none="No claims found.", line="Line", claim="Claim", kind="Kind", conf="Confidence",
               src="Source type", dec="Decision", before="Before", after="After", words="word rule",
               where="Written to: {w}", d=dict(kept="kept", softened="softened", dropped="dropped",
                                                flagged="needs your check")),
    "zh": dict(title="事实核查", intro="旁白里的事实说法，以及核查的处理结果。发布前请过一遍：如果你有可靠来源，"
               "被弱化或删掉的句子可以改回来。", ai="由 AI（{p}）和词语规则共同核查。",
               noai="AI 核查没有运行（{why}）：只用词语规则弱化了「最大」「最繁忙」这类排名说法。日期和数字请自己核对。",
               none="没有发现事实说法。", line="句", claim="说法", kind="类型", conf="把握", src="来源类型",
               dec="处理", before="原句", after="改后", words="词语规则", where="位置：{w}",
               d=dict(kept="保留", softened="已弱化", dropped="已删除", flagged="需要你核对")),
}


def facts_markdown(res, lang="en", title="", where=""):
    w = _WORDS.get(lang) or _WORDS["en"]
    out = [f"# {w['title']}" + (f" - {title}" if title else ""), "", w["intro"], ""]
    out.append(w["ai"].format(p=res.get("provider") or "AI") if res.get("ai") else
               w["noai"].format(why=res.get("ai_note") or "-"))
    out.append("")
    if where:
        out += [w["where"].format(w=where), ""]
    if not res.get("claims"):
        out.append(w["none"])
    for k, c in enumerate(res.get("claims") or [], 1):
        conf = "-" if c.get("confidence") is None else f"{c['confidence']:.2f}"
        out += [f"## {k}. {c.get('claim') or '-'}", "",
                f"- {w['line']}: {c['cue'] + 1}",
                f"- {w['kind']}: {c['kind']}" + (f" ({w['words']})" if c.get("by") == "words" else ""),
                f"- {w['conf']}: {conf}", f"- {w['src']}: {c['source_type']}",
                f"- {w['dec']}: **{w['d'].get(c['decision'], c['decision'])}**"
                + (f" ({c['why']})" if c.get("why") else ""),
                f"- {w['before']}: {_fmt(c.get('before'))}"]
        if c["decision"] in ("softened", "dropped"):
            out.append(f"- {w['after']}: {_fmt(c.get('after'))}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def write_facts(path, res, lang="en", title="", where=""):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(facts_markdown(res, lang, title, where))
    return path


def facts_path(project_dir, item_dir, work_dir):
    """Where facts.md goes -> (path, "project" | "item"): the project's root next to project.yaml when the project
    holds this one item (she opens the project folder and sees it); else the item's work folder, so two versions in
    one project never overwrite each other's record."""
    try:
        if project_dir and os.path.isfile(os.path.join(project_dir, "project.yaml")):
            items = os.path.join(project_dir, "items")
            others = [d for d in (os.listdir(items) if os.path.isdir(items) else [])
                      if not d.startswith(".") and os.path.realpath(os.path.join(items, d)) !=
                      os.path.realpath(item_dir or "")]
            inside = os.path.realpath(item_dir or "").startswith(os.path.realpath(project_dir) + os.sep)
            if inside and not others:
                return os.path.join(project_dir, "facts.md"), "project"
    except OSError:
        pass
    return os.path.join(work_dir, "facts.md"), "item"


def summary_note(res, lang="en"):
    """One plain-words line for the draft's review summary."""
    s, d, f = res.get("softened", 0), res.get("dropped", 0), res.get("flagged", 0)
    if lang == "zh":
        bits = [f"弱化了 {s} 处无法核实的说法" if s else "", f"删去 {d} 句" if d else "", f"{f} 处需要你核对" if f else ""]
        body = "，".join(b for b in bits if b) or "没有需要改的"
        tail = "" if res.get("ai") else "（AI 核查没有运行，只用了词语规则）"
        return f"事实核查：{body}{tail}；详见 facts.md。"
    bits = [f"{s} unverifiable claim{'s' if s != 1 else ''} softened" if s else "",
            f"{d} line{'s' if d != 1 else ''} dropped" if d else "", f"{f} to check yourself" if f else ""]
    body = ", ".join(b for b in bits if b) or "nothing to change"
    tail = "" if res.get("ai") else " (the AI check did not run; word rules only)"
    return f"Fact check: {body}{tail}; see facts.md."


def run(ctx, kind, text, work_dir, complete=None):
    """The hook the drafters call: check ``text`` (``kind`` "spec" | "script"), write facts.md (facts_path) ->
    (new text, record {checked, softened, dropped, flagged, kept, ai, file, where}, summary note)."""
    request = ctx.request()
    fn = check_spec if kind == "spec" else check_script
    try:
        new, res = fn(text, request, complete)
    except Exception as e:  # noqa: BLE001  (a check that breaks never costs her the draft)
        new, res = text, dict(ai=False, ai_note=f"the check failed ({type(e).__name__})", provider=None, claims=[],
                              cues=[], checked=0, kept=0, softened=0, dropped=0, flagged=0)
    path, where = facts_path(getattr(ctx, "project_dir", None), getattr(ctx, "item_dir", None), work_dir)
    lang = ctx.lang() if hasattr(ctx, "lang") else "en"
    lang = lang if lang in _WORDS else "en"
    write_facts(path, res, lang, str((getattr(ctx, "params", None) or {}).get("title") or ""),
                "project folder" if where == "project" and lang == "en" else
                "项目文件夹" if where == "project" else "this version's work folder" if lang == "en" else "本版本的 work 文件夹")
    rec = dict(checked=res["checked"], softened=res["softened"], dropped=res["dropped"], flagged=res["flagged"],
               kept=res["kept"], ai=res["ai"], file=path, where=where)
    if res.get("error"):
        rec["error"] = res["error"]
    return new, rec, summary_note(res, lang)
