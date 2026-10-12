"""CI test selection (.github/scripts/select_tests.py): a change runs the tests that can see it, and nothing else."""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / ".github" / "scripts" / "select_tests.py"


def pick(suite, *changed, flags=()):
    r = subprocess.run([sys.executable, str(SCRIPT), "--suite", suite, "--changed", "-", "--repo", str(REPO), *flags],
                       input="\n".join(changed), capture_output=True, text=True, check=True,
                       env={k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")})
    out = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    return out, r.stderr


def specs(out):
    return sorted(s.rsplit("/", 1)[-1] for m in json.loads(out["e2e_matrix"])["include"] for s in m["args"].split())


def test_a_renderer_view_runs_the_specs_that_use_its_test_ids():
    out, report = pick("desk", "apps/desk/src/renderer/src/weekplan/WeekPlanCard.tsx")
    assert out["e2e"] == "some" and "weekPlan.spec.ts" in specs(out)
    assert len(specs(out)) < 10
    assert out["sidecar"] == "none" and out["unit"] == "some"
    assert "weekplan" in report                              # the summary says why


def test_an_engine_module_runs_its_own_tests():
    out, _ = pick("engine", "lib/vstudio/watermark.py")
    assert out["pytest"] == "some" and "tests/test_watermark.py" in out["pytest_files"].split()
    assert len(out["pytest_files"].split()) < 10
    desk, _ = pick("desk", "lib/vstudio/watermark.py")
    assert "watermark.spec.ts" in specs(desk) and "test_watermark" in desk["sidecar_tests"].split()


def test_a_changed_test_runs_itself():
    out, _ = pick("engine", "tests/test_watermark.py")
    assert out["pytest_files"].split() == ["tests/test_watermark.py"]
    desk, _ = pick("desk", "apps/desk/tests/e2e/weekPlan.spec.ts")
    assert specs(desk) == ["weekPlan.spec.ts"]


def test_docs_run_nothing():
    out, _ = pick("desk", "docs/CI_CD.md", "apps/desk/README.md")
    assert out["e2e"] == "none" and out["sidecar"] == "none" and out["unit"] == "none"
    out, _ = pick("engine", "docs/CI_CD.md")
    assert out["pytest"] == "none"


def test_main_process_code_runs_the_smoke_set_at_least():
    out, _ = pick("desk", "apps/desk/src/main/updater.ts")
    assert {"smoke.spec.ts", "update.spec.ts"} <= set(specs(out))


def test_lockfiles_and_the_full_tier_run_everything():
    for args, changed in (((), "package-lock.json"), (("--full",), "docs/CI_CD.md"), (("--all",), "docs/CI_CD.md")):
        out, _ = pick("desk", changed, flags=args)
        assert out["e2e"] == "all" and out["sidecar"] == "all" and out["unit"] == "all"
        assert [m["args"] for m in json.loads(out["e2e_matrix"])["include"]] == [f"--shard={i}/4" for i in range(1, 5)]
        out, _ = pick("engine", changed, flags=args)
        assert out["pytest"] == "all" and out["pytest_files"] == ""


def test_a_big_selection_is_sharded_by_estimated_time():
    spec = importlib.util.spec_from_file_location("select_tests", SCRIPT)
    st = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(st)
    shards, total = st.shard([f"s{i}.spec.ts" for i in range(40)], {"s0.spec.ts": 300}, 20, 4, 300)
    assert len(shards) == 4 and total == 300 + 39 * 20
    assert ["s0.spec.ts"] in shards                          # the long one gets a shard of its own
    assert st.shard(["a.spec.ts"], {}, 20, 4, 300)[0] == [["a.spec.ts"]]
