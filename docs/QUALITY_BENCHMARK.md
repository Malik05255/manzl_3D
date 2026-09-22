# Quality benchmark and E2E

## Real-drawing benchmark

The repository supports two benchmark levels:

1. `python -m app.benchmark` compares two canonical FloorPlan JSON files.
2. `python -m app.aec_benchmark` runs the local production geometry path against a licensed local copy of AEC-Geometric-Bench-15 and writes predictions in the benchmark's official JSON format.

Example:

```bash
cd services/analyzer
PYTHONPATH=. python -m app.aec_benchmark \
  --dataset /path/to/aec-geometric-bench/dataset \
  --output /tmp/manzil-aec15 \
  --scorer /path/to/aec-geometric-bench/scoring/score.py \
  --report-json /tmp/manzil-aec15-report.json
```

For a quick development pass, add `--limit 1` or `--limit 3`. Limited runs now generate a filtered temporary ground-truth XML before invoking the official scorer, so unselected sheets are not incorrectly counted as missing predictions.

When `--report-json` is used, the report includes:
- aggregate object/wall/area metrics,
- per-object-class TP/FP/FN, precision, recall and F1,
- the exact selected sheet list,
- the same official metrics independently for every selected sheet.

This makes threshold tuning attributable to a specific class and drawing instead of relying on one aggregate F1.

Do not vendor the benchmark drawings into this repository. The released AEC dataset is licensed separately from its scoring code. Keep a licensed local copy outside the application source tree and use the adapter above.

The adapter currently maps:
- detected `single_swing` / unknown doors -> `Single Swing Door`
- detected `double_swing` doors -> `Double Swing Door`
- explicitly corrected `sliding` doors are excluded because the released scorer does not score Sliding Door as an object class
- detected door swing side/depth -> a door-symbol envelope instead of a thin wall-gap box
- Manzil windows -> `Window`
- rooms -> benchmark areas
- wall centerlines + thickness -> wall polygons

The analyzer now supports an optional server-side architectural symbol detector for sink, toilet, bathtub, shower, cooktop and stairs. Detected fixtures are canonical FloorPlanModel elements, rendered in the editor/export, and mapped into the official AEC object classes where applicable. If no detector is configured, those classes remain explicit recall gaps rather than being guessed. Single- versus double-swing subtype is inferred only when hinge-linked leaf evidence is present. Sliding remains a manual correction because parallel sliding geometry is too easy to confuse with window glazing.

## Core E2E

`services/analyzer/tests/test_workflow_e2e.py` generates a deterministic vector PDF, runs document analysis, asks H Engineer for a preview, canonicalizes and validates the result, serializes a saved snapshot, then restores the baseline snapshot.

It runs in the normal CI analyzer job.

The normal CI also includes a **full local black-box E2E** job. It starts a real local Cloudflare Worker with D1, R2 and Queue bindings plus the FastAPI Analyzer, applies all D1 migrations, uploads a generated PDF through the public API, waits for queue analysis, requests an H Engineer preview, applies it, verifies revision history, and restores the previous revision. This catches integration failures that unit tests cannot see.

## Staging black-box E2E

`.github/workflows/e2e-staging.yml` performs the network journey against a deployed environment:

```text
create project
 -> upload PDF
 -> queue/analyzer
 -> poll until ready
 -> H Engineer preview
 -> apply preview
 -> verify revision history
 -> restore previous revision
```

Configure repository secret:

```text
MANZIL_E2E_API_URL=https://your-staging-api.example
```

Then run **Staging E2E** through GitHub Actions workflow dispatch.

The staging workflow intentionally is not part of every push because it consumes deployed cloud resources and requires a real Worker + D1 + R2 + Queue + Analyzer environment.


## Architectural symbol provider

The optional symbol detector is configured only in the Analyzer environment:

```text
SYMBOL_DETECTOR_URL=https://internal-or-managed-detector.example/infer
SYMBOL_DETECTOR_TOKEN=server-only-secret
SYMBOL_MIN_CONFIDENCE=0.78
```

The endpoint receives `image/png` bytes and returns JSON such as:

```json
{"symbols":[{"kind":"toilet","bbox":[100,120,180,220],"confidence":0.94}]}
```

Supported kinds are `sink`, `toilet`, `bathtub`, `shower`, `cooktop`, and `stairs`. Unknown classes, invalid boxes and detections below the threshold are discarded; same-class duplicates are suppressed by IoU NMS. The token never reaches the web client.


## GitHub Actions real benchmark

Run the manual workflow **AEC Real Drawing Benchmark**, confirm that the dataset licence permits the run, and choose a limit from 1 to 15. It records both the Manzil H and dataset commit SHAs, checks out the released benchmark into the ephemeral GitHub runner, runs Manzil H, executes the official scorer, writes the score into the workflow summary, and uploads predictions plus both `score.txt` and machine-readable `report.json` as artifacts.

If the repository secrets `SYMBOL_DETECTOR_URL` and `SYMBOL_DETECTOR_TOKEN` are configured, fixture classes are evaluated through the same server-side symbol detector. If they are absent, the workflow intentionally measures the geometry/opening baseline without inventing fixture detections.


### Local ONNX symbol inference

The Analyzer can run a YOLO-style ONNX model in-process through OpenCV DNN, so floor-plan images do not have to leave the Analyzer. Configure:

```text
SYMBOL_ONNX_MODEL=/models/floorplan-symbols.onnx
SYMBOL_ONNX_CLASSES=["sink","toilet","bathtub","shower","cooktop","stairs"]
SYMBOL_ONNX_INPUT_SIZE=640
SYMBOL_ONNX_NMS_IOU=0.45
SYMBOL_MIN_CONFIDENCE=0.78
```

The decoder accepts common YOLOv8/YOLO11 outputs (`4 + class_count`) and YOLOv5-style outputs (`5 + class_count`, including objectness), applies letterboxing, maps boxes back to original page coordinates, applies NMS, then passes the result through the same canonical class/box validation used by the HTTP detector. If local ONNX returns no accepted detections, the configured HTTP detector remains available as fallback.

Weights are deliberately not stored in this repository. Use only a model and training data whose licence permits your intended deployment.


## Internal benchmark semantics

The internal `app.benchmark` report is class-aware for doors, windows and
architectural symbols. Its `macroF1` is an **active-category macro**: a category
is included only when either prediction or ground truth contains at least one
item in that category. Empty-on-both-sides categories do not contribute an
artificial F1 of 1.0. The report exposes the included names in
`macroCategories`.

Door and window matches are scored separately before producing the aggregate
`openings` metric, so a window can never satisfy a ground-truth door merely
because the segments overlap. Symbol boxes are likewise matched only within the
same fixture class at IoU 0.50.

## AEC diagnostic artifacts

Each licensed AEC workflow run retains, per selected sheet:

- the official AEC prediction JSON,
- the full Manzil H canonical extraction under `predictions/_canonical/`,
- a source-space visual overlay under `predictions/_debug/`,
- aggregate and per-class metrics,
- per-sheet official metrics.

The canonical JSON and overlay are diagnostic artifacts only; they do not alter
the official scoring input.


## Parallel AEC-15 execution

The `Stages 2-5 Validation` workflow exports the licensed test ONNX model once,
then runs AEC-Geometric-Bench-15 as five parallel shards of three sheets each.
The shard artifacts are merged and scored once with the official scorer, so the
aggregate and per-sheet metrics still represent the complete 15-sheet set.

The analyzer also prefers embedded PDF text when it contains enough useful room
or dimension labels. In that case Tesseract is limited to numeric and rotated
dimension passes. Set `PDF_NATIVE_TEXT_FASTPATH=0` to force the full OCR path
for troubleshooting.
