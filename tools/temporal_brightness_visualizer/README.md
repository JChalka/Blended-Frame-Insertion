Temporal Brightness Visualizer

Purpose:
- visualize monotonic ladders
- visualize full 16-bit brightness distribution
- inspect step-size spacing and BFI usage
- generate an HTML report with charts

Usage:
python temporal_brightness_visualizer.py --lut-dir <lut_output_dir> --out-dir <report_dir>

Expected inputs:
- r_temporal_ladder.json / g_temporal_ladder.json / b_temporal_ladder.json / w_temporal_ladder.json
- r_monotonic_ladder.json / g_monotonic_ladder.json / b_monotonic_ladder.json / w_monotonic_ladder.json

Outputs:
- per-channel PNG charts
- all_channels_monotonic_overlay.png
- brightness_visualizer_report.html
- brightness_visualizer_summary.json
