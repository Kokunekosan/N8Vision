# N8Vision — Alpha

<img src="static/N8_256.png" width="128" height="128" alt="N8Vision icon">

A free, open-source image library for browsing generated images, pruning files,
inspecting metadata and preparing selected subjects for editing.

**Official alpha: I.2t-l-Z1a.** [Download the complete package](https://github.com/Kokunekosan/N8Vision/releases/tag/vI.2t-l-Z1a).
No patch stacking is needed. Bug reports are welcome in [Issues](https://github.com/Kokunekosan/N8Vision/issues).

## Install and launch

Windows prerequisites: Python **3.14** with the `py` launcher. Blurred/Full also
need Git for their pinned image-quality dependency.

1. Extract the complete ZIP into an empty application folder.
2. Run **install.cmd** and choose the capacity you need.
3. Run **N8Vision.cmd**, or an explicit Lite/Blurred/Full launcher.

All profiles share one installed `.venv`. Add capacity later by running
install.cmd again in that same folder. Launching Lite from a Full installation
keeps the heavier functions disabled. Downloads occur during installation or
when an optional feature is prepared; source packages contain no model weights.
The browser opens after the server becomes ready.

| Profile | Tools |
| --- | --- |
| Lite | Archive maintenance, thumbnails, browsing, selection, filesystem actions, stored filters and manual annotations. |
| Blurred | Lite plus detectors, quality inspection, embeddings, similarity/uniqueness, SAM and existing ComfyUI/refinement/training tools. |
| Full | Blurred plus selected-image subject assembly, preferred-language-model inspection and learned composite classes. |

## Updating an existing installation

Stop N8Vision, back up your existing installation, and replace application source
files from the complete ZIP. Preserve your `.venv`, `data`, `cache`, models,
training projects and settings. Restart using the desired profile and refresh
all browsers. The download contains no personal archive or machine configuration.
Do not initialize or run a GitHub publishing checkout; use a separate live copy.

## Browsing and mobile

- Directory-change discovery and automatic archive inspections retain the browsing position.
- Equivalent feature names merge into badges and filters while detector attribution stays available in the inspector.
- Settings provides an explicit preview/cleanup of observations from missing local detectors. Reviewed/owned observations require an additional opt-in for removal.
- Phones/tablets load a bounded image window and remember desired column counts separately by orientation. Search, sorting and Shown actions operate on that loaded window.
- Mobile Menu and Filters switch cards. **Clear Selected** is directly below the hamburger.
- Inspector and mask studio support **+/− zoom**, **Fit**, **WASD** panning and a touch stick. Framing moves image/mask/box layers together.

## Subject tools: selected images, on demand

These are specialist tools for images you plan to work on. Select the intended
images before assembly or language-model inspection; they are not whole-library
background jobs. Fast YOLO-based inspection remains available separately.

Full includes BiRefNet-based separation. For the optional **PartGLEE** or
**LangHOPS** object/part backends, run **Install-SubjectParts.cmd**, choose a
backend, and use **Assemble selected subjects**. These reconstruction backends
currently require NVIDIA CUDA. PartGLEE weights are about 0.8GB plus shared
resources; the LangHOPS checkpoint is about 16GB plus shared resources.

For language-model interrogation, select an image-capable model in Prompt
Translator settings and connect the existing ComfyUI environment. Inspection
sends the assembled subject pixels on gray; draft names/features appear in the
inspector. The preferred LM is configurable. LangHOPS's internal PaliGemma model
is a separate parser dependency and requires the user's own approved Hugging
Face access. Never put access tokens in issue reports or source files.

Parts and ownership begin as drafts. Explicitly choose owners for manual masks.
Use **Use language-model class** (or correct the Subject label), then **Learn
Subject**, to save a confirmed composite lesson.

## Composite class training

A shared visual recognizer learns new classes from confirmed masked composites.
It trains a supervised class head on frozen pretrained visual features; it does
not fine-tune your preferred LM or the anatomy/ownership parser. Ownership and
mask corrections remain valuable teaching records for future parser work.

At least **two classes**, each with **three different source images**, are needed
for an initial run. This minimum creates a source-separated training/validation
split; it is not an accuracy guarantee. Build varied examples and review masks.
Automatic inference never teaches itself. Training after manual Learn commits
can be switched off. Extra requests during training coalesce into one follow-up.

The training-button light and text distinguish queued, running, activated,
validation-rejected and failed states. A completed training job may still fail
validation: the prior active model then remains in use. Per-class held-out
results explain the rejection. Learned recognition stays a draft until confirmed.
A previous validated model can be restored. See the verification reports for
exact acceptance checks and current limits.

## Alpha status and testing

Source/API checks, controlled real encoder/class-training tests, archive checks
and simulated mobile/framing control tests passed. The developer has exercised
mobile browsing, remote inspection and subject identification in live use.
Recent mobile drawer and zoom controls still need broader device testing.
A clean Internet installation and every GPU/Comfy combination have not been
end-to-end tested. Report edition/version, device and reproduction steps with
bugs; remove tokens, personal paths and private image content from shared logs.

Feature work is frozen through **Friday, October 16, 2026**; changes during this
period are limited to polishing, fixes, compatibility and documentation.

## License and model terms

N8Vision source is [MIT licensed](LICENSE): free to use, modify and redistribute.
Dependencies and downloaded models retain their own terms. In particular,
[LangHOPS](https://github.com/y9miao/LangHOPS-release) is an optional
**CC BY-NC-SA 4.0** research backend; N8Vision's MIT license does not relicense it.
[PartGLEE](https://github.com/ProvenceStar/PartGLEE) and gated PaliGemma resources
are downloaded separately. Review their upstream terms for your intended use.
