# Subject recognizer training review

The previous implementation trained one linear classifier over frozen CLIP image
features. It did not fine-tune CLIP, the preferred language model, BiRefNet or the
part reconstruction models. Exact custom labels competed as separate classes.

## Findings

* A single held-out source per class produced binary-looking validation: one
  difficult example meant 0%, regardless of the remaining collection.
* Accepted accuracy combined naming errors and abstentions. The global 80% gate
  prevented every update whenever one or more classes struggled.
* A class could achieve good recall by overpredicting its label. The previous
  gate did not explicitly evaluate accepted precision for that class.
* Visual support was measured against a class centroid containing the very
  training example being scored. With tiny training sets, this can give an
  unrealistically tight cutoff for a genuinely different held-out image.
* Softmax does not model overlapping semantic attributes. Labels such as `futa`
  and `futa_cyborg` remain exact alternative targets; changing validation does
  not create a hierarchy or multi-label annotations that were never supplied.

## Z1i changes

Source-group cross-validation uses 3–5 folds. Every eligible example receives
one held-out prediction; subjects from the same source image stay together.
Each fold trains from scratch and derives support cutoffs solely from its
training sources. Old active weights are never used to initialize a candidate
fold. Cross-validation is a development estimate, not an untouched final test set.

Visual support uses the closest same-class example from a different training
source, instead of a self-containing centroid. Existing score and margin gates
(0.65 / 0.15) remain. These scores are not calibrated probabilities. A source-based
minimum similarity still applies and can still abstain on unfamiliar subjects.

Each class update needs at least 80% accepted precision and 50% accepted recall.
The overall average is informational, not a veto on every class. False positives
are counted across other exact labels in the supplied teaching set, not arbitrary
unseen images; this is not a demonstrated open-world false-positive bound.

Passing classes can be admitted while weak classes remain pending. Candidate
heads still learn exact competing labels; their weak outputs are disabled at
recognition time. Existing unpromoted class heads keep their weights, gates and
precedence. Candidate admission also checks composed head routing and active-class
regression. Retained-model checks are replay checks, not independent estimates.
Final admitted heads are refit on all eligible examples after cross-validation.

Only examples belonging to admitted classes are marked trained. All remaining
examples are retained. Recognition stays a draft requiring explicit confirmation.
No inferred labels become teaching examples automatically.

## Verification and compatibility

Actual PyTorch optimization on synthetic feature fixtures admitted two distinct
classes while holding back two indistinguishable classes. Tests cover source
group isolation, all-example evaluation, false-positive rejection, prior head
retention, legacy/schema-2 checkpoint loading, partial database activation,
pending lesson states, repeat training, rollback and stale-lesson rejection.
JavaScript and Python syntax checks passed.

These tests exercise training and activation mechanics, not accuracy on the
user's collection. The full pretrained encoder/image pipeline was not rerun.
Very small evaluation sets are explicitly identified in reports. Related concepts,
style bias, pose variation and features insensitive to anatomy can still limit
recognition. A future explicit attribute/multi-label teaching design would be a
separate change; label strings are not automatically decomposed.

Legacy checkpoints remain readable. New class registries use schema 2 and need
Z1i's recognition code. The existing model rollback action retains support for
older revisions. No live archive, teaching examples or trained weights were changed.

Method references: [group-separated cross-validation](https://scikit-learn.org/stable/modules/cross_validation.html)
and [PyTorch's separate multi-label loss formulation](https://docs.pytorch.org/docs/stable/generated/torch.nn.BCEWithLogitsLoss.html).
The patch implements its own deterministic source-group fold allocator and adds
no scikit-learn dependency. It does not switch the task to multi-label training.
