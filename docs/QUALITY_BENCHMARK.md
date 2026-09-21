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
  --scorer /path/to/aec-geometric-bench/scoring/score.py
```

For a quick development pass, add `--limit 1` or `--limit 3`.

Do not vendor the benchmark drawings into this repository. The released AEC dataset is licensed separately from its scoring code. Keep a licensed local copy outside the application source tree and use the adapter above.

The adapter currently maps:
- Manzil doors -> `Single Swing Door`
- Manzil windows -> `Window`
- rooms -> benchmark areas
- wall centerlines + thickness -> wall polygons

This deliberately exposes a current limitation: Manzil does not yet classify sanitary/kitchen symbols or distinguish single/double/sliding doors. Those categories therefore remain visible as recall gaps instead of being guessed.

## Core E2E

`services/analyzer/tests/test_workflow_e2e.py` generates a deterministic vector PDF, runs document analysis, asks H Engineer for a preview, canonicalizes and validates the result, serializes a saved snapshot, then restores the baseline snapshot.

It runs in the normal CI analyzer job.

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
