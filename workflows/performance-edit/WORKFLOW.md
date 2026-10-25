# Filmed performance editing

**Use when** a recorded comedy/sketch needs an editorial cut, with or without dialogue. Use preproduction for
an unfilmed idea and ai-video only for explicitly requested generation. This workflow edits one source performance
per item; it does not infer multi-camera synchronisation or manufacture missing setup/payoff footage.

The engine inspects periodic source contact sheets (including changes inside a shot), optionally incorporates
dialogue when analysis confirms speech,
and writes `work/edit.json`: chronological kept ranges with reasons and protected setup, development, payoff
and reaction ranges with visible/spoken evidence. Silence and reaction pauses are part of the performance.
Use source actions rather than a quota of cuts, zooms or sound effects. A contiguous kept range is appropriate
when an uninterrupted action is the joke. Keep later consequences and reactions; do not turn a near miss into
an ending that omits the actual payoff. The original frame and sound are retained at 1×, including existing text.

Plans are checked against actual source duration before rendering. Every protected beat must be fully retained;
invalid plans get one correction using the original source context. An invalid correction fails visibly. Model
claims of what a scene shows remain subject to playback review: a contact sheet is not proof of comic timing.

The native renderer makes actual trim/concat edits, then exports platform files, covers and post copy. It does
not run speech cleanup or add AI narration, a musical bed, educational cards, looping, padding or a new crop.
A separately composed vertical version needs its own framing review; do not label a landscape performance as
a YouTube Short. Ask mode exposes the story plan; Autopilot uses the same validated plan without an extra gate.

Review the opening context, full physical action, dialogue boundaries, misdirection, payoff and reaction in
motion. Check that edits preserve who knows what and when. Compare audio with the original when it has sound;
a silent source may remain silent. Keep `work/quality.json`, source ranges, and protected-beat evidence.
Flicker failures are review blockers, including source-film damage: do not loosen thresholds, silently discard
reactions or claim a red report is an accepted film. Exporting an already edited sample is integration evidence,
not proof of professional editing quality, a newly shot performance, or superiority to a competing editor.


### Audio cuts need their own review

Quality review compares 100 ms of each retained side of a cut with the original
continuous sound at both source boundaries, per channel. An edit-created level
change above 12 dB, at audible energy and more than 6 dB beyond either original
transition, requests listening before approval. These are review thresholds, not
proof of an audible defect or a LUFS measurement. Preserve intended silence,
reactions and impact sounds. Do not apply a blanket fade or crossfade: protect
words and synchronization, inspect source handles, and compare treatments by
listening. The report explicitly records that listening has not been verified.

The native renderer and review use decoded source timestamps. Short input-seek
windows can truncate packet-based audio and must not be used as review evidence.
