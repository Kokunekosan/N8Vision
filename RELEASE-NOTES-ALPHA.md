# N8Vision alpha I.2t-l-Z1y

Update over Z1w, including both Z1x and Z1y. Complete download; no patch stacking.

## Latest fixes

- Inclusive selection follows the browsed direction across the desktop ring origin.
- Move destination folders appear immediately from a visited-folder cache, with
  validation in the background. The picker remembers the last destination.
- The server reuses folder listings until their directory signature changes;
  first visits still enumerate. Directory timestamps can also change on file actions.
- Move batches release selection immediately and execute sequentially, letting you
  gather the next batch. Completed moves receive hand-truck markers; failures are
  reported. The queue lives in the browser session: keep the tab open until done.

## Install or update

Windows/Python 3.14. New users: extract to an empty folder, run install.cmd and
N8Vision.cmd. Existing users: stop Vision and replace application source while
preserving .venv, data, cache, models and settings; restart and refresh browsers.

Checks: frontend/Python syntax, controlled ring direction tests, directory cache
reuse/change detection using real temporary folders, browser queue/coalescing/
failure recovery simulations, ZIP entry/CRC/manifest checks. Maintainer reports
improved destination-picker responsiveness in live use. Broader device testing
remains welcome. No model weights, credentials or personal archive included.

Bug reports: https://github.com/Kokunekosan/N8Vision/issues
