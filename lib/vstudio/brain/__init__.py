"""vstudio.brain - the editor's judgement: which template, what each shot gets, where generation would help.

    python -m vstudio.brain classify --inputs clips/ --prompt "a calm 60 s film" --json
    python -m vstudio.brain treat --inputs clips/ --template travel-calm --target 60 --aspect 9:16 --json
    python -m vstudio.brain gen --inputs clips/ --template travel-calm --target 60 --json     (proposals, no spend)
    python -m vstudio.brain show --dir <project> [--refresh] --json
    python -m vstudio.brain template --dir <project> --id beat-short --json
    python -m vstudio.brain shot --dir <project> --id C2.S1 --set transition=cut --json
    python -m vstudio.brain decide --dir <project> --id g1a2b3c4 --approve --code 9f3e1a --json
    python -m vstudio.brain estimate --dir <project> --id g1a2b3c4 --json      (the spend gate's sheet, no spend)
    python -m vstudio.brain generate --dir <project> --id g1a2b3c4 --estimate est-.. --confirm 8hex --max-cny 6.7
    python -m vstudio.brain place --dir <project> --id g1a2b3c4 [--undo] --json
    python -m vstudio.brain shots --dir <project> --output <output id> --json  (a clip's shots + the plan)

Modules: presets (the templates and their shot policies), template (signals + the classifier), tiles (shot tiles
with metrics, from ``vstudio.shots`` when present), treat (per-shot treatment planner), genplan (generation
proposals with prices), store (a project's brain: her choices in project.yaml, the computed plan in state/brain/),
steer (the plan as each builder's edit decisions), generate (an approved proposal through the Create spend gate,
placed in the edit), edl (a clip's per-shot edit list joined with the plan), cli. Docs: references/INTAKE.md section 9.
"""
