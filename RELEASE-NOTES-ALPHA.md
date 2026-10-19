# N8Vision alpha I.2t-l-Z2b — nightly update

Complete package through Z2b, including Z1z, Z2a and Z2b; no patch stacking.

## Nightly fixes — October 18, 2026

- Explore detects created/removed folders, including empty ones, using background
  directory checks. Tree changes do not rebuild or reposition the image grid.
- Ctrl+A and Select Shown exclude deleted/moved placeholders and queued moves.
- Settings / Ignore contents adds editable filename, full-path and wildcard rules.
  Default: log.html. Matching files stay on disk; save reloads library counts.
- Successful ComfyUI Replace recovery invalidates old masks, detections, quality
  receipts, embeddings and corrections, refreshes file stats and cached identity.
  Beside/output-only modes preserve the original. Frozen teaching examples remain.
- Replacement invalidation applies after updating, not to already completed edits.
  Wait for active batches to finish before updating. Running inference jobs are
  not cancelled by this mechanism; general external-edit monitoring is not added.

## Install / update

New: extract to an empty folder, run install.cmd, then N8Vision.cmd.
Existing: finish active jobs, stop Vision, replace application source while
preserving .venv/data/cache/models/settings, restart and refresh browsers.
Windows/Python3.14; optional heavier profiles/models retain their requirements.

Checks: Python/frontend syntax; real temporary directory-tree creation/removal
and zero unchanged enumeration; ignore matching/validation; SQLite replacement
cleanup and actual recovery replace/retry/beside branches; clean source manifest,
ZIP CRC and byte/hash checks. Live nightly fixes still need broader validation.
No personal archive, credentials, weights or runtime environment included.

https://github.com/Kokunekosan/N8Vision/issues
