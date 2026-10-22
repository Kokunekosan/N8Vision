# N8Vision alpha I.2t-l-Z2v

Complete package through Z2v; no patch stacking.

## Latest update - October 22, 2026

- Ultimate SD Upscale now has a dedicated action with editable scale, denoise,
  tiling and seam controls, an expandable LoRA chain and the connected checkpoint VAE.
- Refine and Upscale keep settings independently, including their opt-in checkbox.
  Destination is a compact chooser: select Replace, Beside or Output before sending.
- Workshop node pickers no longer stop at 30 matches. Clearly video/audio-specific
  tools are excluded; shared image-processing tools remain available.
- Comfy recovery timeout follows batch inactivity, with each returned result
  extending the window. Batch status shows the number complete.
- New and regenerated same-name outputs clear stale placeholders. Automatic grid
  refresh prepares visible cards first and retries deferred batch refreshes.
- The move picker reuses the folder architecture already discovered by the library.
- Diagnostic badges refresh on changed assets. Idle Vision models are released
  after two minutes; Comfy handoff also releases idle models.
- Atomic active-job journals preserve more useful interruption diagnostics.

An isolated report of Beside removing its original remains unconfirmed. See
[known issues and reporting details](KNOWN-ISSUES.md) if it happens again.

## Install / update

New: extract to an empty folder, run install.cmd, then N8Vision.cmd.
Existing: finish active jobs, stop Vision, replace application source while
preserving .venv/data/cache/models/settings, restart and refresh browsers.

Ultimate SD Upscale requires its Comfy node, ImpactWildcardEncode and an installed
upscale model. Refresh the Tool Shelf if installed dependencies are missing.
Comfy installations, models and workflows are not modified by this release.

Validation includes installed-node schema and graph/socket checks for 0/1/3 LoRAs,
VAE wiring, browser JSON revision regression, settings isolation and migration,
model residency, journal, file intake/recovery, and package integrity checks.
The user confirmed the upscale workflow functions. Output quality depends on the
chosen model and settings; broader hardware/browser testing remains welcome.

Report bugs: https://github.com/Kokunekosan/N8Vision/issues
