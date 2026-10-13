"""One generation outside an episode - the editor brain's "Could be generated" proposals - through the same spend
gate as an episode's finals (SPEC §1.5).

    est = oneoff.estimate(owner_dir, job)        # priced, with an 8-hex confirm code that expires; nothing is sent
    res = oneoff.run(owner_dir, job, est["id"], est["confirm_code"], est["max_cny"], on_event=print)
    # -> {state: done | failed | unknown-charge, files [...], task, cny, provider, model}

``job`` = {id, kind video | image, provider, model, seconds, resolution?, aspect, prompt, refs {name: local path}}.

The gate, as for an episode: the estimate exists, its code matches and was never used (one OK = one submission), it
has not expired, the job did not change since (the code covers the brief, the price and the rate card), ``max_cny``
covers it, the monthly cap has room, the rate is known, the service is ready and has the credits, and its own quote
(when it gives one) is not above the estimate. Then ``submit`` is called exactly once - never retried: a timeout
after the request left is ``unknown-charge`` in the ledger and she decides. ``max_cny`` = the price (one clip, no
retry allowance: a failed take is not tried again by itself).

``owner_dir`` keeps the estimates and this owner's ledger (``estimates.json``, ``spend.jsonl``); the month counter is
Create's own, so every spend counts against the one monthly cap. Providers come from the Create registry (tests stand
their fakes in there, ``providers.set_fake``); nothing here has a fake path of its own.
"""
import hashlib
import json
import os
import time

from vstudio import oscompat

from . import costs, store
from . import providers as PR
from .i18n import CreateError, msg

STAGE = "oneoff"
POLL_EVERY = float(os.environ.get("VSTUDIO_CREATE_POLL_S", "10"))
POLL_LIMIT = float(os.environ.get("VSTUDIO_CREATE_POLL_LIMIT_S", "1800"))
JOB_KEYS = ("id", "kind", "provider", "model", "seconds", "resolution", "aspect", "prompt", "refs")


def _path(owner, name):
    os.makedirs(owner, exist_ok=True)
    return os.path.join(owner, name)


def _estimates(owner):
    return store.read_json(_path(owner, "estimates.json"), {}) or {}


def _sig(job):
    """What an OK covers besides the price: the brief and its stills (a changed prompt needs a new OK)."""
    refs = {k: [os.path.basename(v), os.path.getsize(v) if os.path.exists(v) else None]
            for k, v in sorted((job.get("refs") or {}).items())}
    body = dict({k: job.get(k) for k in JOB_KEYS if k != "refs"}, refs=refs)
    return hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def _price(job):
    kind = job.get("kind") or "video"
    return costs.price_job(job["provider"], job["model"], 1 if kind == "image" else job["seconds"],
                           job.get("resolution"), kind=kind)


def build(job):
    """Pure: the estimate of ``job`` (no IO except the rate card)."""
    p = _price(job)
    e = costs.entry(job["provider"], job["model"]) or {}
    line = dict(provider=job["provider"], model=job["model"], label=p.get("label") or e.get("label") or job["model"],
                kind=job.get("kind") or "video", seconds=job.get("seconds"), seconds_billed=p.get("seconds_billed"),
                native_units=p.get("native_units"), cny=p.get("cny"), verified=bool(p.get("verified")),
                resolution=job.get("resolution") or e.get("resolution"), sig=_sig(job))
    ver = costs.load_rates().get("version")
    code = costs.confirm_code([line], ver, job["id"], STAGE)
    now = time.time()
    cny = None if p.get("unknown") else round(float(p.get("cny") or 0), 2)
    return dict(id=f"est-{hashlib.sha1(f'{code}{now}'.encode()).hexdigest()[:10]}", stage=STAGE, job=job["id"],
                lines=[line], subtotal_cny=cny or 0.0, retry_cny=0.0, max_cny=cny or 0.0, unknown=[job["id"]] if cny is None
                else [], confirm_code=code, rates_version=ver, created=now, expires_at=now + costs.CONFIRM_TTL_S)


def _month_ctx(est):
    m = costs.month()
    cap, used = m.get("cap_cny"), round(float(m.get("used_cny") or 0), 2)
    return dict(budget=dict(budget=None, spent=None, left_after=None),
                month=dict(cap=cap, used=used, left_after=None if cap is None else round(cap - used - est["max_cny"], 1)))


def check(est):
    """Every refusal reason of ``est`` now (empty = ok): month cap, unknown rate, the service ready, its credits."""
    codes = []
    m = _month_ctx(est)["month"]
    if m["cap"] is not None and m["used"] + est["max_cny"] > m["cap"] + 1e-6:
        codes.append(msg("over-cap", used=m["used"], cap=m["cap"], need=est["max_cny"]))
    if est.get("unknown"):
        codes.append(msg("unknown-rate", shots=est["unknown"]))
    ln = est["lines"][0]
    try:
        p = PR.get(ln["provider"])
        ready = bool(p.status().get("ready"))
    except CreateError:
        p, ready = None, False
    if not ready:
        codes.append(msg("provider-not-ready", provider=ln["provider"]))
    elif ln.get("native_units"):
        bal = p.balance()
        if bal is not None and bal < ln["native_units"]:
            codes.append(msg("low-credits", provider=ln["provider"], balance=bal, need=ln["native_units"]))
    return codes


def estimate(owner, job, save=True):
    """The priced estimate of ``job`` with its confirm code and every reason it would be refused now (``codes``);
    kept in ``owner`` so ``run`` can check it. Nothing is sent."""
    est = build(job)
    if save:
        with _locked(owner):
            keep = dict(sorted(_estimates(owner).items(), key=lambda kv: kv[1].get("created", 0))[-8:])
            keep[est["id"]] = est
            store.write_json(_path(owner, "estimates.json"), keep)
    return dict(est, codes=check(est), **_month_ctx(est))


class _locked:
    def __init__(self, owner):
        self.path = _path(owner, ".gate.lock")

    def __enter__(self):
        self.f = open(self.path, "a")
        oscompat.lock(self.f)
        return self

    def __exit__(self, *exc):
        oscompat.unlock(self.f)
        self.f.close()


def gate(owner, job, estimate_id, confirm_code, max_cny):
    """All of the gate or a CreateError - no side effects. -> the stored estimate."""
    est = costs.verify(dict(estimates=_estimates(owner)), estimate_id, confirm_code, max_cny, build(job))
    if est.get("job") != job["id"]:
        raise CreateError("plan-changed", status=409)
    codes = check(est)
    if codes:
        raise CreateError(codes[0]["code"], status=409, codes=codes, **codes[0]["params"])
    ln = est["lines"][0]
    q = PR.get(ln["provider"]).quote(_job_obj(job))
    if q is not None and q > float(est["max_cny"]) * 1.05 + 1e-6:
        raise CreateError("price-changed", status=409, provider=ln["provider"], quoted=q, estimated=est["max_cny"],
                          shots=[job["id"]])
    return est


def _job_obj(job):
    from .providers.aivideo import make_job
    e = costs.entry(job["provider"], job["model"]) or {}
    kind = job.get("kind") or "video"
    res = job.get("resolution") or e.get("resolution") or ("2k" if kind == "image" else "720p")
    model = job["model"]
    if e.get("api_model"):
        model = os.environ.get(e.get("api_model_env") or "", "") or e["api_model"]
    j = make_job(unit=job["id"], kind=kind, model=model, prompt=job.get("prompt") or "",
                 duration=None if kind == "image" else costs.snap(e, job["seconds"], res) if e else job["seconds"],
                 aspect=job.get("aspect") or "16:9", resolution=res, refs=dict(job.get("refs") or {}), audio=False,
                 extra=dict(rationale=f"One shot ({job['id']}) the user approved for her own edit."))
    return j


def run(owner, job, estimate_id, confirm_code, max_cny, on_event=None, out_dir=None):
    """The gate, then ``submit`` exactly once, poll, download into ``out_dir`` (default ``owner``)."""
    emit = on_event or (lambda ev: None)
    with _locked(owner):              # gate + "this OK is used" in one step: a double click submits once
        est = gate(owner, job, estimate_id, confirm_code, max_cny)
        all_ = _estimates(owner)
        all_[est["id"]]["used"] = store.stamp()
        store.write_json(_path(owner, "estimates.json"), all_)
    ln = est["lines"][0]
    cny = float(est["max_cny"])
    p = PR.get(ln["provider"])
    jo = _job_obj(job)
    base = dict(job=job["id"], provider=ln["provider"], model=ln["model"], est_cny=cny, credits=ln.get("native_units"),
                estimate=est["id"])
    ledger = _path(owner, "spend.jsonl")
    emit(dict(event="create.progress", job=job["id"], state="submitting", cny=cny))
    try:
        tid = p.submit(jo)                                    # PAID - exactly once
    except PR.SubmitTimeout as e:
        costs.ledger_append(None, dict(base, task_id=None, status="unknown-charge", error=str(e)[:200]), path=ledger)
        emit(dict(event="create.progress", job=job["id"], state="unknown-charge"))
        return dict(state="unknown-charge", files=[], task=None, cny=cny, provider=ln["provider"], model=ln["model"],
                    code="create.unknown-charge")
    except CreateError:
        raise
    except Exception as e:  # noqa: BLE001  (rejected before acceptance: not charged)
        costs.ledger_append(None, dict(base, est_cny=0, task_id=None, status="rejected", error=str(e)[:200]),
                            path=ledger)
        emit(dict(event="create.progress", job=job["id"], state="failed"))
        return dict(state="failed", files=[], task=None, cny=0.0, provider=ln["provider"], model=ln["model"],
                    code="create.shot-failed", error=str(e)[:200])
    costs.ledger_append(None, dict(base, task_id=tid, status="submitted"), path=ledger)
    emit(dict(event="create.progress", job=job["id"], state="running", task=tid))
    t0 = time.time()
    while True:
        try:
            r = p.poll(tid)
        except Exception as e:  # noqa: BLE001  (poll errors after retries: charged, the take can still be collected)
            return dict(state="unknown-charge", files=[], task=tid, cny=cny, provider=ln["provider"],
                        model=ln["model"], code="create.poll-failed", error=str(e)[:200])
        if r["status"] in ("done", "failed") or time.time() - t0 > POLL_LIMIT:
            break
        time.sleep(getattr(p, "poll_every", POLL_EVERY))
    if r["status"] != "done":
        emit(dict(event="create.progress", job=job["id"], state="failed", task=tid))
        return dict(state="failed", files=[], task=tid, cny=cny, provider=ln["provider"], model=ln["model"],
                    code="create.shot-failed", error=str(r.get("raw"))[:200])
    d = out_dir or owner
    os.makedirs(d, exist_ok=True)
    ext = ".jpg" if (job.get("kind") or "video") == "image" else ".mp4"
    files = []
    for k, url in enumerate(r.get("urls") or []):
        path = os.path.join(d, f"{job['id']}_v{k + 1}{ext}")
        try:
            p.download(url, path)
            files.append(path)
        except Exception:  # noqa: BLE001  (a failed download: the take stays at the service, said below)
            continue
    emit(dict(event="create.progress", job=job["id"], state="done" if files else "failed", task=tid))
    return dict(state="done" if files else "failed", files=files, task=tid, cny=cny, provider=ln["provider"],
                model=ln["model"], code=None if files else "create.shot-failed")
