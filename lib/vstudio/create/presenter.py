"""AI presenter: a talking-head video of the creator (Hedra Character-3) from HER portrait + a finished narration.

Behind the Create spend gate (never relaxed): an estimate with an 8-hex confirm code (15 min, one use), the monthly
cap, ``--max-cny`` covering the estimate, one ``submit`` ever per confirmed estimate (a timeout after the request
left = an ``unknown-charge`` ledger row, never a resubmit), every submit in the ledger before polling.

    python -m vstudio.create presenter estimate --image ME.jpg --audio narration.wav [--resolution 540p|720p]
                                                [--aspect 16:9|9:16|1:1] [--prompt TEXT] [--out DIR]
        -> {id, confirm_code, seconds, credits, cny, max_cny, checks {ok, codes}, month, ...}   (no network)
    python -m vstudio.create presenter run --estimate ID --confirm CODE --max-cny N      PAID (HEDRA_API_KEY)
    python -m vstudio.create presenter show [--estimate ID]                             estimates + ledger

The portrait is only ever the file she passes for this purpose (consent is hers); nothing is uploaded until ``run``.
Store: ``$VSTUDIO_HOME/create/presenter/<id>.json`` (estimates + run state), ``.../spend.jsonl`` (ledger).
"""
import hashlib
import os
import time
from types import SimpleNamespace

from . import costs, store
from .i18n import CreateError, msg

PROVIDER, MODEL = "hedra", "character-3"
POLL_S, POLL_MAX_S = 10.0, 3600.0


def root():
    return os.path.join(store.create_dir(), "presenter")


def _path(eid):
    if not eid or not all(c.isalnum() or c == "-" for c in str(eid)):
        raise CreateError("bad-input", field="estimate")
    return os.path.join(root(), f"{eid}.json")


def _ledger():
    return os.path.join(root(), "spend.jsonl")


def _lines(image, audio, seconds, resolution, aspect, prompt):
    p = costs.price_job(PROVIDER, MODEL, seconds, resolution)
    return p, [dict(provider=PROVIDER, model=MODEL, resolution=resolution, aspect=aspect, seconds=round(seconds, 2),
                    seconds_billed=p["seconds_billed"], credits=p["native_units"], cny=p["cny"],
                    image=os.path.abspath(image), audio=os.path.abspath(audio), prompt=prompt or "",
                    audio_sha=_sha(audio), image_sha=_sha(image), verified=p.get("verified", False))]


def _sha(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()[:12]


def estimate(image, audio, resolution="540p", aspect="16:9", prompt=None, out=None):
    """The quote for one presenter video (no network, nothing uploaded)."""
    from vstudio import media
    for f, field in ((image, "image"), (audio, "audio")):
        if not f or not os.path.isfile(f):
            raise CreateError("bad-input", field=field)
    if resolution not in ("540p", "720p"):
        raise CreateError("bad-input", field="resolution")
    if aspect not in ("16:9", "9:16", "1:1"):
        raise CreateError("bad-input", field="aspect")
    seconds = float(media.duration(audio) or 0)
    e = costs.entry(PROVIDER, MODEL) or {}
    if not seconds or seconds > float(e.get("max_clip_s") or 600):
        raise CreateError("bad-input", field="audio", seconds=round(seconds, 1), max_s=e.get("max_clip_s") or 600)
    p, lines = _lines(image, audio, seconds, resolution, aspect, prompt)
    sub = float(p["cny"] or 0)
    retry = round(sub * costs.DEFAULT_RETRY, 2)
    ver = costs.load_rates().get("version")
    code = costs.confirm_code(lines, ver, "presenter", "finals")
    now = time.time()
    est = dict(id=f"pres-{hashlib.sha1(f'{code}{now}'.encode()).hexdigest()[:10]}", kind="presenter",
               provider=PROVIDER, model=MODEL, lines=lines, seconds=lines[0]["seconds"],
               seconds_billed=p["seconds_billed"], credits=p["native_units"], subtotal_cny=round(sub, 2),
               retry_pct=costs.DEFAULT_RETRY, retry_cny=retry, max_cny=round(sub + retry, 2),
               unknown=bool(p["unknown"]), verified=bool(p.get("verified")), confirm_code=code, rates_version=ver,
               created=now, expires_at=now + costs.CONFIRM_TTL_S,
               out=os.path.abspath(out or os.path.dirname(os.path.abspath(audio))))
    est["checks"] = _checks(est)
    store.write_json(_path(est["id"]), est)
    return est


def _checks(est, allow_unknown=False):
    from . import providers as PR
    codes = []
    m = costs.month()
    used = round(float(m.get("used_cny") or 0), 2)
    if m.get("cap_cny") is not None and used + est["max_cny"] > m["cap_cny"] + 1e-6:
        codes.append(msg("over-cap", used=used, cap=m["cap_cny"], need=est["max_cny"]))
    if est.get("unknown") and not allow_unknown:
        codes.append(msg("unknown-rate", shots=["presenter"]))
    try:
        ready = PR.get(PROVIDER).status().get("ready")
    except CreateError:
        ready = False
    if not ready:
        codes.append(msg("provider-not-ready", provider=PROVIDER))
    return dict(ok=not codes, codes=codes, month=dict(cap=m.get("cap_cny"), used=used))


def verify(estimate_id, code, max_cny):
    """The stored estimate if the code matches, it was never used, it has not expired, its files did not change
    since and ``max_cny`` covers it; else CreateError (same contract as costs.verify)."""
    if not estimate_id or not code:
        raise CreateError("confirm-required", status=409)
    est = store.read_json(_path(estimate_id), None)
    if not est:
        raise CreateError("confirm-required", status=409, estimate=estimate_id)
    if est.get("confirm_code") != code:
        raise CreateError("confirm-mismatch", status=409)
    if est.get("used"):
        raise CreateError("confirm-used", status=409)
    if time.time() > float(est.get("expires_at") or 0):
        raise CreateError("confirm-expired", status=409)
    ln = est["lines"][0]
    try:
        _, fresh = _lines(ln["image"], ln["audio"], ln["seconds"], ln["resolution"], ln["aspect"], ln["prompt"])
    except OSError:
        raise CreateError("plan-changed", status=409) from None
    if costs.confirm_code(fresh, costs.load_rates().get("version"), "presenter", "finals") != code:
        raise CreateError("plan-changed", status=409)
    if max_cny is None or float(max_cny) + 1e-6 < float(est["max_cny"]):
        raise CreateError("max-too-low", status=409, max_cny=max_cny, need=est["max_cny"])
    return est


def run(estimate_id, code, max_cny, allow_unknown=False, on_event=None, sleep=time.sleep):
    """PAID. Gate -> mark the estimate used -> ledger row -> ONE submit -> poll -> download."""
    from vstudio import media
    from . import providers as PR
    from .providers.base import SubmitTimeout
    emit = on_event or (lambda ev: None)
    est = verify(estimate_id, code, max_cny)
    chk = _checks(est, allow_unknown)
    if not chk["ok"]:
        raise CreateError(chk["codes"][0]["code"], status=409, **chk["codes"][0]["params"])
    est["used"] = time.time()                       # one confirmed estimate = one submission, whatever happens
    store.write_json(_path(est["id"]), est)
    ln = est["lines"][0]
    job = SimpleNamespace(prompt=ln["prompt"], refs={"first_frame": ln["image"]}, extra={"audio": ln["audio"]},
                          resolution=ln["resolution"], aspect=ln["aspect"], duration=ln["seconds"], model=MODEL)
    prov = PR.get(PROVIDER)
    row = dict(kind="presenter", estimate=est["id"], provider=PROVIDER, model=MODEL, seconds=ln["seconds"],
               credits=est["credits"], est_cny=est["subtotal_cny"])
    emit(dict(event="stage", stage="submit", provider=PROVIDER))
    try:
        task = prov.submit(job)
    except SubmitTimeout as e:
        costs.ledger_append(None, dict(row, status="unknown-charge", error=str(e)[:200]), path=_ledger())
        raise CreateError("unknown-charge", status=502, provider=PROVIDER) from e
    costs.ledger_append(None, dict(row, status="submitted", task=task), path=_ledger())
    est["task"] = task
    store.write_json(_path(est["id"]), est)
    waited, res = 0.0, None
    while waited < POLL_MAX_S:
        res = prov.poll(task)
        emit(dict(event="progress", stage="generate", status=res["status"],
                  progress=(res.get("raw") or {}).get("progress")))
        if res["status"] != "pending":
            break
        sleep(POLL_S)
        waited += POLL_S
    if not res or res["status"] != "done":
        est["result"] = dict(status=(res or {}).get("status") or "timeout")
        store.write_json(_path(est["id"]), est)
        raise CreateError("shot-failed", status=502, shot="presenter", task=task)
    dst = os.path.join(est["out"], f"presenter-{est['id']}.mp4")
    prov.download(res["urls"][0], dst)
    est["result"] = dict(status="done", file=dst, duration=media.duration(dst))
    store.write_json(_path(est["id"]), est)
    return dict(ok=True, file=dst, estimate=est["id"], task=task, credits=est["credits"], est_cny=est["subtotal_cny"])


def show(estimate_id=None):
    if estimate_id:
        est = store.read_json(_path(estimate_id), None)
        if not est:
            raise CreateError("not-found", status=404, what="estimate", id=estimate_id)
        return est
    rows = []
    if os.path.isdir(root()):
        for f in sorted(os.listdir(root())):
            if f.endswith(".json"):
                e = store.read_json(os.path.join(root(), f), {}) or {}
                rows.append({k: e.get(k) for k in ("id", "seconds", "credits", "max_cny", "used", "result")})
    return dict(estimates=rows, ledger=store.read_jsonl(_ledger()) if os.path.exists(_ledger()) else [],
                month=costs.summary())
