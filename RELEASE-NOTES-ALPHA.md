# N8Vision alpha I.2t-l-Z1w

Complete source release, consolidating the tested patch stack since Z1a.

- Faster library startup and optional configurable desktop browsing windows.
- Completed rows appear without waiting for offscreen buffer rows. Redraw reuses
  valid thumbnails, then performs browser cache/folder bookkeeping in background.
- Responsive selection and filesystem actions; all successful moves leave
  hand-truck markers and release moved selections. Rename remains in place.
- Stable inclusive selection with deleted/moved placeholders excluded, including
  path-only selection across unloaded windows in unfiltered Filesystem order.
- Filesystem ordering, collapsible menu sections, and training diagnostics drawer.
- Split subject separation/naming, guided subject splitting, improved class
  training/validation diagnostics, independent class admission and recognition refresh.
- Mobile Back closes the topmost menu, inspector, mask editor or dialog first.

One download; Lite, Blurred and Full share one environment. Install only the
capacity you need. Optional models retain their upstream licenses/access rules.

Windows: Python 3.14 with py launcher; Git for heavier profiles. Extract to an
empty folder, run install.cmd, then N8Vision.cmd. Existing users: stop Vision,
replace source while preserving .venv/data/cache/models/settings, restart and
refresh browsers. Do not run the application from this publishing checkout.

Verification: source syntax, controlled archive-window/range regression tests,
frontend VM checks from individual patches, clean-package manifest/CRC checks.
Developer confirmed instant redraw in live use. Latest mobile Back behavior and
fresh installation across hardware combinations need broader testing. No claim
of universal model accuracy or measured startup timing.

Report bugs: https://github.com/Kokunekosan/N8Vision/issues
