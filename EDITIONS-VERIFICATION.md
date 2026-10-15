# I.2t-l-E1b edition verification

User scope: Lite keeps archive/filesystem work; Blurred includes everything
currently implemented; Full adds future Subject Intelligence. This explicitly
supersedes the earlier proposal to make current SAM/Comfy Full-only.

Implemented shared feature profiles, one cumulative .venv for all editions,
pinned dependency snapshots, edition installers and
launchers, backend/UI capability gates, Windows global instance exclusion,
Okay/Find dialog and local-only attention, edition-preserving Restart Server.
Archive/data/config/model-cache formats are not migrated or replaced.

Passed:
- Fresh Lite installation of 23 pinned runtime packages plus build tooling,
  using the actual installer in an isolated workspace. Installed environment
  measured 55.5 MiB including tooling/bytecode. No Torch, NumPy, Ultralytics or
  model weights installed. A repeated installation reused its verified receipt.
- Fresh Lite interpreter, with inference imports additionally blocked: actual
  ASGI health, archive page, file, thumbnail and manual-box persistence routes.
  Inference/processing routes return 403 before importing providers. Startup
  retains archive/cache/New Noticer services and omits BRISQUE/Comfy services.
- Blurred/Full actual profile/API/startup checks with the existing proven heavy
  interpreter: both expose current capabilities; missing input reaches normal
  validation rather than an edition block. Subject Intelligence unavailable.
- Existing 500-record mobile protocol retained; confirmed M34 code included.
- Real Windows cross-process mutex test: second process denied while first
  holds it; new process succeeds after release. Tests used an isolated mutex
  name and never locked/restarted the live installation.
- Exact dialog text and Okay/Find callbacks tested with a mocked Tk window.
  Find sends attention to the existing local URL and reopens the UI.
- Actual local attention API allowed loopback and rejected a paired remote
  client. Browser attention polling is restricted to loopback hostnames.
- Complete frontend in an isolated synthetic browser fixture: Lite hides
  inference/ordering controls, hides SAM but keeps manual Paint Mask; Blurred
  retains current vision and ordering controls.
- Complete Python compilation and JavaScript parsing; package defaults and
  install plans checked; all distributions share identical application code.
- Source-only ZIP inventory, CRC and manifest SHA256 verified.

Installer details:
requirements-lite.lock pins the tested lightweight dependency graph.
requirements-blurred.lock pins the current heavy graph; image-quality-fusion
is pinned to Git commit 78873ad6b847d4e14363312d0e831ddaf667b6f7.
requirements-full.lock currently includes the same graph. Windows CPU builds
were checked against the official indexes:
https://download.pytorch.org/whl/cpu/torch/
https://download.pytorch.org/whl/cpu/torchvision/
CUDA selections match the installed proven 2.14.0+cu130 / 0.29.1+cu130 stack.
No heavy environment was freshly downloaded/installed for this task.

Limits:
- Fresh heavy installation, GPU/SAM inference, Comfy integrations and actual
  OS browser focus behavior were not re-run end to end. Current heavy features
  were retained; live profile/launcher confirmation is still needed.
- Find uses the operating-system browser reopen/reuse mechanism; it cannot
  guarantee that every browser selects the original tab instead of another tab.
- Legacy running installs are recognized at their known/default local port.
  Upgraded installs use the machine-wide mutex and recorded local URL even
  across editions/folders. Other operating systems are not validated.
- Full currently adds no additional implemented features or extra model weight.
- The upgrade sequence requires stopping Vision before
  changing its installed environment. Installers never delete existing envs.
- No Subject Intelligence, new model-training system, SimulFlow, idle unloading
  or new workflow families were implemented. No live install files or public
  GitHub repository/release were changed.

E1a correction: every installer and launcher targets the same .venv.
Installation extends the stack; Lite never uninstalls heavy packages. Tests
checked all launcher paths and Blurred -> Lite -> Full receipt reuse without
duplicate pip steps (mocked install operations). The earlier fresh Lite test
used an isolated test environment; no new heavy download was performed.
