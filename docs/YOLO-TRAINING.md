# YOLO training and evolution in N8Vision

Start with a useful detector, inspect its mistakes, and teach the next version with those corrections. Longer training can be worthwhile; the goal is a detector that works on your images, rather than the shortest possible run.

## Which operation?

| Operation | Use it for |
| --- | --- |
| Train New | A new detector or segmenter starting from Vision's bundled training choice. |
| Retrain / Enhance Existing | Improving an existing detector with additional examples and corrections. Select its current weight file. |
| Add Class to Extant | Teaching additional output classes while retaining the existing class vocabulary. Include examples of the old classes too. |
| Add Segmentation to Extant | Moving a box detector toward pixel masks. This changes the task and needs appropriate mask examples. |

For a watermark box detector, choose Retrain / Enhance Existing, the current Watermarkboy model, and its exact class name (`wtrmrk`). SAM masks are unnecessary. Give the candidate a new model name to retain the previous weight file: using the same output name replaces the installed file when training finishes.

The Classes field filters saved annotations. It does not rename or merge their classes. Existing-model evolution also retains that model's original class names. The list of training examples is assembled from matching archive annotations, not just the images currently selected in the grid. Inspect the run's dataset and receipt to understand what was included.

## Positive boxes and negative examples

Box every real instance of the trained classes in each training image. Include small, faint and unusual examples, not just easy ones. Other positive detector observations for the chosen classes can enter the dataset too; review their accuracy rather than assuming every target is manually confirmed.

Use **No, that isn't that** for a false detection. Keep its negative record; **Delete this detection** intentionally removes that evidence. Enable **Include rejected detections** in the trainer. Vision includes source images with explicit rejections for the trained classes, excludes rejected boxes from target labels, and keeps genuine positive boxes on those same images. If none remain, it writes an empty label file, meaning background. Rejections are scoped by class, not restricted to the selected detector's filename.

A negative is not a new `class-Neg` output category, or a numerical anti-weight applied to the rejected rectangle. YOLO sees the full image and its remaining positive labels. Consequently, a missed real watermark elsewhere in that image would also be treated as background. Check the entire source image before using it as a negative example. See Ultralytics' [dataset guidance](https://docs.ultralytics.com/yolov5/tutorials/tips-for-best-training-results/) for label completeness and background images (that page uses YOLOv5 examples; the dataset principles are useful here).

For Watermarkboy, chains, seams and toes that resemble corner text are useful hard negatives. Keep representative real watermark examples alongside them. A model that detects nothing has fewer false positives, but is not necessarily better.

Annotations must match the current pixels. A cleaned image is not still a positive watermark example just because its original once contained text. Vision replacement workflows invalidate old observations; avoid manually restoring stale labels onto cleaned pixels.

## Epochs, resolution and time

One epoch is a pass through the training dataset. 2,600 images over 100 epochs means roughly 260,000 image presentations; batching and augmentation affect the actual work performed.

Practical starting points, not promised optima:

| Kind of run | Initial epoch budget |
| --- | --- |
| Focused correction of an already useful detector | 20-30 |
| Substantial expansion of examples or appearances | 30-50 |
| Initial training or a larger rebuild | 100, then judge the results |

Using 100 for a refinement is not inherently wrong. Compare candidates to learn whether the extra training helps. Loading existing weights is fine-tuning; it is not the same as resuming an interrupted run with its optimizer and scheduler state. Vision's evolution starts a new training run from the selected weights.

Start with the existing image-size setting for a comparable trial. Increasing it can help retain tiny text detail, but increases memory and compute demand. More epochs cannot recover detail lost during resizing. Vision uses automatic batch sizing (`batch=-1`); avoid other heavy GPU work while measuring a training run. Available VRAM, resolution and model size affect throughput, not just image count.

The current UI exposes epochs and image size, but not learning rate, patience or a separate validation split. Do not assume all settings in upstream tutorials are already available through Vision. Read the official [training settings](https://docs.ultralytics.com/modes/train/) and [configuration reference](https://docs.ultralytics.com/usage/cfg/) for deeper control. Defaults can differ with the installed Ultralytics version.

## Judge the evolution

Vision currently points training and validation at the same generated image set. Its displayed validation score is therefore a training-set check, not an independent estimate of accuracy. It installs the run's `best.pt` after fitting; the YOLO evolver does not currently have the Subject Class trainer's independent acceptance gate. Inspect a new candidate before relying on it.

Keep two useful comparison sets:

- A familiar, corrected set for regression testing: did rejected seams and toes stop firing? For a cleaned set, remaining detections should be inspected as missed text or false positives.
- A separate, previously unseen set containing genuine targets and confusing background details: did false positives decrease without losing real detections?

Use the same inference confidence threshold when comparing models, and distinguish fresh observations from old detector overlays. Confidence is not a direct guarantee of correctness. Once you train on a test image, keep a different untouched set for the next generalization check.

Inspect the generated `dataset.yaml`, label files, training plots and `n8vision-evolution.json` under the run's learning folder. The receipt includes positive instances, images with rejected detections and background-only images. Those negative counts describe included examples, not a measured correction success rate.

## More detailed references

- [Ultralytics training guide](https://docs.ultralytics.com/modes/train/): training arguments, checkpoints and resuming.
- [Training tips](https://docs.ultralytics.com/guides/model-training-tips/): dataset quality and practical preparation.
- [Detection dataset format](https://docs.ultralytics.com/datasets/detect/): bounding-box labels and dataset structure.
- [Data preparation and split leakage](https://docs.ultralytics.com/guides/preprocessing-annotated-data/): keeping validation and test evidence independent.

These are upstream references. Vision-specific behavior above describes the current local evolution implementation, separate from Subjectifier class training.
