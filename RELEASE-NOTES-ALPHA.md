# N8Vision alpha I.2t-l-Z3s

Complete package through Z3s; no patch stacking.

## October 26, 2026

- Large-library browsing streams ordered discovery chunks without waiting for a whole-tree inventory. Root clicks coalesce; optional startup work waits for browsing. A pending scroll step completes when its row is ready.
- New detections update badges, boxes, masks and filters across loaded and cached cards. Inspector corrections preserve box selection and reuse unchanged mask overlays.
- Inspector and mask-studio batch counters show your position. Studio controls stay visible while detections scroll; correction labels are preloaded and deduplicated.
- YOLO training accepts box-only examples and explicit rejected detections as background evidence. Manual and automatic evolution share a single FIFO training queue, with epoch progress.
- Automatic maintenance has its own saved epoch limit, default 20, instead of inheriting a model's earlier training run. Existing running jobs keep their original limits.
- Active jobs stay above completed history; polling preserves wake-up requests and avoids waiting for a full observation refresh.
- Forget shown updates affected cards instead of rebuilding the library. Configuration writes use unique atomic temporary files with bounded sharing-violation retries. Shutdown archive requests receive a retryable response.
- Replaced Comfy outputs invalidate old pixels and show an In-Process banner. Optional workflow-pack processing preserves original PNG generation text.
- Check-for-Updates.cmd checks official GitHub releases and downloads a complete ZIP on request, checking size, ZIP integrity and the release checksum when supplied. It never applies an update automatically.
- Includes YOLO training guidance in docs/YOLO-TRAINING.md and the optional workflow-pack infrastructure. Model weights and the Watermarkboy expansion remain separate.

## Install / update

New: extract to an empty folder, run install.cmd, then N8Vision.cmd.
Existing: finish active jobs and stop Vision. Replace application source while preserving .venv, data, cache, models and settings; restart and refresh browsers.

Regression checks cover discovery streaming, observation/card synchronization, correction selection, training FIFO and cancellation, maintenance epochs, atomic writes, shutdown retries, updater download integrity and package reconstruction. Full-library timing and GPU training behavior vary by system; these checks do not establish model accuracy.

The intermittent Beside donor-removal report remains unconfirmed. See KNOWN-ISSUES.md and https://github.com/Kokunekosan/N8Vision/issues/1 for reporting details.
