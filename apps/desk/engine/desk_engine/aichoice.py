"""The AI a request / project / goal runs on (per-task AI): the composer's choice for one request, stored on the
request, written into each project it becomes (project.yaml ``ai: {provider, model}``) and read by every AI step of
that project (``vstudio.llm.project_ai``: step override > project ai > task route > default, the global fallback
order behind it).

  a request (planning)   the job's ``ai`` -> env VSTUDIO_LLM_PROJECT_AI for ``vstudio.intake plan / revise``
  a project              ``vstudio.project model --dir D --provider P [--model M] | --clear`` (the decisions log
                         records the switch; a running project uses it from its next AI step, never the step now)
  a goal                 the goal's ``ai`` -> each video's request; switching the group switches every video not yet
                         made (a request still planning, a project still making)
"""
import json
import os
import re

from .common import need

PROVIDER_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,119}$")
ENV = "VSTUDIO_LLM_PROJECT_AI"
BY = ("you", "chat", "group")


def clean(v, field="ai"):
    """{provider, model?} from the desk -> a clean dict, or None (absent / null = the app's default)."""
    if v is None:
        return None
    need(isinstance(v, dict), f"{field}: {{provider, model}}")
    p = v.get("provider")
    if p in (None, "", "default"):
        return None
    need(isinstance(p, str) and PROVIDER_RE.match(p), f"{field}.provider: a provider id")
    m = v.get("model")
    need(m is None or (isinstance(m, str) and MODEL_RE.match(m)), f"{field}.model: a model id")
    return {"provider": p, **({"model": m} if m else {})}


def env(ai):
    """The environment a request's engine call runs with (its AI), or {}."""
    return {ENV: json.dumps(ai)} if ai else {}


def label(ai):
    if not ai:
        return None
    return ai["provider"] + (f" · {ai['model']}" if ai.get("model") else "")


def set_project(runner, d, ai, by="you", live=True):
    """Write the project's AI (None: back to the app's default) -> what the engine now resolves for it."""
    need(runner is not None, "the engine is not available")
    need(by in BY, f"by: {' | '.join(BY)}")
    need(os.path.isfile(os.path.join(d, "project.yaml")), "not a recipe project")
    args = ["model", "--dir", d, "--by", by, "--json"]
    args += ["--provider", ai["provider"], *(["--model", ai["model"]] if ai.get("model") else [])] if ai else ["--clear"]
    doc = runner.sibling("vstudio.project").json(args, timeout=60)
    need(isinstance(doc, dict) and doc.get("ok"), (doc or {}).get("error") if isinstance(doc, dict) else "switch failed")
    if live:
        from .live import LIVE_NAME, emit_engine
        emit_engine(os.path.join(d, LIVE_NAME), "ai", f"AI → {label(ai) or 'default'} (from the next AI step)",
                    dict(ai=ai, by=by))
    return dict(ai=doc.get("ai"), resolved=doc.get("resolved"))


def read_project(d):
    """The project's AI from its project.yaml (cached parse), or None."""
    from .history import _project_yaml
    data = _project_yaml(d)
    a = data.get("ai") if isinstance(data, dict) else None
    if not isinstance(a, dict) or not isinstance(a.get("provider"), str):
        return None
    return {"provider": a["provider"], **({"model": a["model"]} if isinstance(a.get("model"), str) else {})}
