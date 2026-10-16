# Face masking in finished videos

In Edit with AI, ask for a time interval, a face position (left, middle or right),
and a mask style (mosaic, blur, cat or dog). For example:

> Cover the middle face with a cat mask from 24 to 29 seconds.

The editor submits `privacy-sticker` and tracks the video locally before exporting.
Cat and dog masks are built in; a web sticker link is not required. Face positions
refer to the clear seed frame, not identity or gender recognition.

Tracking runs on the edited timeline after trims and speed changes, before camera
zooms, overlays and caption layout. The mask therefore follows those transforms.
The optional Face masking model must be installed through the app's asset setup.

Use a continuous shot with visible faces. Tiny faces, occlusions, dissolves and
shot changes can prevent reliable tracking. In that case export stops and reports
the uncertain time ranges on the edited timeline. No partially masked export is
reported as successful. Split at shot boundaries or select a clearer interval;
a static sticker is not a substitute for a verified track.
