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

For a quick development pass, add `--limit 1` or `--limit 3`.

Do not vendor the benchmark drawings into this repository. The released AEC dataset is licensed separately from its scoring code. Keep a licensed local copy outside the application source tree and use the adapter above.

The adapter currently maps:
- Manzil doors -> `Single Swing Door`
- Manzil windows -> `Window`
- rooms -> benchmark areas
- wall centerlines + thickness -> wall polygons

The analyzer now supports an optional server-side architectural symbol detector for sink, toilet, bathtub, shower, cooktop and stairs. Detected fixtures are canonical FloorPlanModel elements, rendered in the editor/export, and mapped into the official AEC object classes where applicable. If no detector is configured, those classes remain explicit recall gaps rather than being guessed. Door subtype classification (single/double/sliding) is still not inferred.

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
