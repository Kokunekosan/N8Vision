# Subject separation S1

Apply over I.2t-l-E1b. Stop Vision, extract the patch into the application folder,
run install-Full.cmd to extend the SAME .venv, then N8Vision-Full.cmd and refresh.
Lite and Blurred retain their current tools. Source ZIPs contain no weights,
environments, archive state or credentials. First subject use downloads the
pinned BiRefNet snapshot plus YOLO-World/text-encoder weights if not present.

Selected images only: Full > Subject separation > Separate selected subjects.
Work uses the existing cancellable jobs queue; no automatic archive-wide sweep.
Observations are saved in the existing archive, so inspector masks, SAM tools
and preparation tools can consume the same geometry. No database migration.

BiRefNet foreground proposals are localized and named by YOLO-World. Spatial
box IoU >= .70 plus exact normalized label matching (Woman/Female, Man/Male)
is required to inherit a box. Existing masks additionally require pixel IoU
>= .70 and valid geometry/source dimensions. Valid masks take priority over
unmasked boxes; each existing annotation is inherited at most once per image.
Existing masks remain byte-for-byte unchanged. Unmasked matching boxes receive
BiRefNet pixels while retaining their label, confidence, provider, model and
box coordinates. New instances are separate draft mask observations. Negative
or whole-image observations are not inherited. Malformed masks are not reused.

Disconnected foreground components remain separate. Multiple detector boxes
can propose individuals within a connected region. Overlapping duplicate
proposals are suppressed; uncertain targets get a lower-threshold single-target
crop pass. Unnamed regions remain unidentified, rather than being forced into
a guessed name. All new masks are marked for review. This is the first stage,
not the complete future relationship/subject hierarchy or aesthetic classifier.

Verified:
- Real pinned BiRefNet CPU inference at 1024x1024, restored to original size,
  with current Torch/Transformers and isolated Full dependencies. Fixed FP16
  checkpoint/FP32 CPU input mismatch; CPU uses float32, CUDA uses float16.
- Real YOLO-World initial and focused single-target CPU naming passes using
  a synthetic icon/foreground fixture. This verifies compatibility, not accuracy.
- Archive persistence: existing Female box enriched, second Woman created,
  repeat run inherited both without changing saved records or detector identity.
- Label, spatial, pixel, duplicate-instance, malformed-mask and source-size
  tests; disconnected subject proposals and unidentified fallback.
- Real ASGI Lite/Blurred/Full archive checks and Full-only subject API gating.
- Full UI action dispatches selected paths only; complete JavaScript parsing.
- Installer plans preserve one cumulative .venv. Full adds pinned einops,
  Kornia/Kornia-RS and Ultralytics CLIP; lower-profile receipts reused after Full.
- Python compilation; source-only ZIP inventory, CRC and SHA256 verified.

Limits:
- GPU inference, quality on user generations and physical UI use not validated.
- BiRefNet is foreground segmentation, not a semantic/instance classifier.
  Touching subjects and overlapping boxes can share pixels. These are draft
  masks, not guaranteed individual silhouettes; existing SAM remains available.
- YOLO-World requires candidate vocabulary; configured vocabulary or default
  classes are used. The focused pass is single-target, not unlimited naming.
- Repeat runs still compute proposals before deciding identity/inheritance;
  they avoid rebuilding matching saved masks, not all inference.
- No live installation or GitHub files changed. This supersedes E1's statement
  that Full and Blurred have identical capabilities.

Official model/code pinned:
https://huggingface.co/ZhengPeng7/BiRefNet/tree/e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4
