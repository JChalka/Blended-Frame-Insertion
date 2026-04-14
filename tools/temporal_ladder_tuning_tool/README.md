# Temporal Ladder Tuning Tool

Post-build tool for analyzing, pruning, interpolating, and combining temporal
ladder outputs. Operates on the `*_temporal_ladder.json`/`.csv` files produced
by `temporal_lut_tools.py` and on the raw `plan_capture_*.csv` measurement logs.

## Subcommands

| Command               | Purpose |
|-----------------------|---------|
| `analyze`             | Scan ladders for monotonicity violations, BFI-crossing outliers, CIE-xy drift, and emit a JSON report. |
| `apply`               | Apply prune or fix actions to ladder outputs based on the analysis report. |
| `interpolate-captures`| Synthesize missing capture states from pruned capture chunks using neighbor interpolation. |
| `combine-captures`    | Merge pruned measured captures and interpolated captures into a single sorted export. |

## Typical Workflow

```text
1. Build LUTs with temporal_lut_tools_gui or temporal_lut_tools.py
2. Analyze → identify outliers
3. Apply --action prune → remove outlier rows from captures
4. Interpolate-captures → synthesize missing states
5. Combine-captures → produce a clean unified capture set
6. Re-build LUTs from the combined captures
```

## Example Commands

All paths below are **placeholders** — substitute your actual working directories.

### Analyze

```bash
python temporal_ladder_tuning_tool.py analyze \
    --lut-dir       <LUT_OUTPUT_DIR> \
    --capture-dir   <RAW_CAPTURE_DIR> \
    --report-out    <WORK_DIR>/tuning_report.json \
    --recapture-out <WORK_DIR>/recapture_plan.csv \
    --filtered-capture-out <WORK_DIR>/plan_capture_outliers_pruned.csv
```

Key flags (all have sensible defaults):

| Flag | Default | Description |
|------|---------|-------------|
| `--monotonic-tolerance-q16` | 8 | Tolerance for monotonicity checks |
| `--bfi-tolerance-q16` | 8 | Tolerance for BFI-crossing checks |
| `--xy-drift-threshold` | 0.010 | CIE-xy drift alarm threshold |
| `--xy-spread-threshold` | 0.0035 | CIE-xy spread alarm threshold |
| `--filtered-capture-chunk-rows` | 100 000 | Max rows per pruned capture chunk |

### Apply (prune)

```bash
python temporal_ladder_tuning_tool.py apply \
    --lut-dir     <LUT_OUTPUT_DIR> \
    --capture-dir <RAW_CAPTURE_DIR> \
    --report-out  <WORK_DIR>/tuning_report.json \
    --action      prune \
    --out-dir     <PRUNED_OUTPUT_DIR>
```

`--action` accepts `report` (dry-run), `prune` (remove outliers), or `fix`
(attempt automated repair).

### Interpolate captures

```bash
python temporal_ladder_tuning_tool.py interpolate-captures \
    --capture-dir              <PRUNED_OUTPUT_DIR> \
    --target-plan-dir          <RAW_CAPTURE_DIR> \
    --interpolated-capture-out <WORK_DIR>/interpolated/plan_capture_interpolated.csv
```

### Combine captures

```bash
python temporal_ladder_tuning_tool.py combine-captures \
    --pruned-capture-dir       <PRUNED_OUTPUT_DIR> \
    --interpolated-capture-dir <WORK_DIR>/interpolated \
    --combined-capture-out     <WORK_DIR>/combined/plan_capture_combined.csv
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `TEMPORAL_LADDER_TUNING_SPILL_DIR` | Override the default spill/temp directory (default: `./temporal_ladder_tuning`) |

## Notes

- The `--spill-dir` flag is shared across subcommands and controls where temp
  files and automatic output redirection land when output paths point at a
  system drive.
- Chunk rows flags (`--filtered-capture-chunk-rows`,
  `--interpolated-capture-chunk-rows`, `--combined-capture-chunk-rows`) control
  memory pressure on large capture sets by splitting output into multiple CSVs.
- For calibration header/JSON generation, prefer **rgbw_lut_builder** which is
  the current recommended calibration path. The legacy `export-calibration-header`
  and `export-calibration-json` CLI subcommands in `temporal_lut_tools.py` remain
  available for compatibility.
