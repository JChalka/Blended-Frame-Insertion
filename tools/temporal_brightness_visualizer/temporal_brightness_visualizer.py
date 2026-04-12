#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Dict
import math
import matplotlib.pyplot as plt

CHANNELS = ["R", "G", "B", "W"]

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def effective_bits(n_states: int) -> float:
    if n_states <= 1:
        return 0.0
    return math.log2(n_states)

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def load_channel_data(lut_dir: Path) -> Dict[str, dict]:
    data = {}
    for ch in CHANNELS:
        mono_path = lut_dir / f"{ch.lower()}_monotonic_ladder.json"
        ladder_path = lut_dir / f"{ch.lower()}_temporal_ladder.json"
        mono = load_json(mono_path) if mono_path.exists() else []
        ladder = load_json(ladder_path) if ladder_path.exists() else []
        data[ch] = {"monotonic": mono, "ladder": ladder}
    return data

def plot_monotonic_rank(data: Dict[str, dict], out_dir: Path):
    for ch in CHANNELS:
        mono = data[ch]["monotonic"]
        if not mono:
            continue
        xs = [int(e["rank"]) for e in mono]
        ys = [float(e["normalized_output"]) for e in mono]
        bfi = [int(e["bfi"]) for e in mono]

        plt.figure(figsize=(10, 6))
        sc = plt.scatter(xs, ys, c=bfi, cmap="plasma", s=18)
        plt.xlabel("Monotonic ladder rank")
        plt.ylabel("Normalized output")
        plt.title(f"{ch} monotonic ladder")
        plt.grid(True, alpha=0.3)
        cbar = plt.colorbar(sc)
        cbar.set_label("BFI")
        plt.tight_layout()
        plt.savefig(out_dir / f"{ch.lower()}_monotonic_rank.png", dpi=150)
        plt.close()

def plot_delta_stairs(data: Dict[str, dict], out_dir: Path):
    for ch in CHANNELS:
        mono = data[ch]["monotonic"]
        if not mono:
            continue
        xs = [int(e["rank"]) for e in mono]
        ys = [int(e["delta_q16_from_prev"]) for e in mono]

        plt.figure(figsize=(10, 6))
        plt.plot(xs, ys)
        plt.xlabel("Monotonic ladder rank")
        plt.ylabel("Delta q16 from previous")
        plt.title(f"{ch} step-size distribution")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(out_dir / f"{ch.lower()}_delta_steps.png", dpi=150)
        plt.close()

def plot_full_distribution(data: Dict[str, dict], out_dir: Path):
    for ch in CHANNELS:
        mono = data[ch]["monotonic"]
        if not mono:
            continue
        xs = [int(e["output_q16"]) for e in mono]
        ys = list(range(len(mono)))
        cs = [int(e["bfi"]) for e in mono]

        plt.figure(figsize=(10, 6))
        plt.scatter(xs, ys, c=cs, cmap="plasma", s=20)
        plt.xlabel("Output q16")
        plt.ylabel("State index")
        plt.title(f"{ch} full 16-bit brightness distribution")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(out_dir / f"{ch.lower()}_full_distribution.png", dpi=150)
        plt.close()

def plot_combined_overlay(data: Dict[str, dict], out_dir: Path):
    plt.figure(figsize=(11, 7))
    plotted = False
    for ch in CHANNELS:
        mono = data[ch]["monotonic"]
        if not mono:
            continue
        xs = [int(e["rank"]) for e in mono]
        ys = [float(e["normalized_output"]) for e in mono]
        plt.plot(xs, ys, label=f"{ch} ({len(mono)} states)", linewidth=1.5)
        plotted = True
    if plotted:
        plt.xlabel("Monotonic ladder rank")
        plt.ylabel("Normalized output")
        plt.title("All-channel monotonic ladder overlay")
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.tight_layout()
        plt.savefig(out_dir / "all_channels_monotonic_overlay.png", dpi=150)
    plt.close()

def plot_bfi_state_usage(data: Dict[str, dict], out_dir: Path):
    for ch in CHANNELS:
        mono = data[ch]["monotonic"]
        if not mono:
            continue
        counts = {}
        for e in mono:
            counts[int(e["bfi"])] = counts.get(int(e["bfi"]), 0) + 1
        xs = sorted(counts)
        ys = [counts[x] for x in xs]
        plt.figure(figsize=(8, 5))
        plt.bar(xs, ys)
        plt.xlabel("BFI")
        plt.ylabel("Monotonic states")
        plt.title(f"{ch} BFI usage in monotonic ladder")
        plt.grid(True, axis="y", alpha=0.3)
        plt.tight_layout()
        plt.savefig(out_dir / f"{ch.lower()}_bfi_usage.png", dpi=150)
        plt.close()

def write_html_summary(data: Dict[str, dict], out_dir: Path):
    rows = []
    for ch in CHANNELS:
        mono = data[ch]["monotonic"]
        ladder = data[ch]["ladder"]
        states = len(mono)
        bits = effective_bits(states)
        q16_min = mono[0]["output_q16"] if mono else 0
        q16_max = mono[-1]["output_q16"] if mono else 0
        rows.append(
            f"<tr><td>{ch}</td><td>{len(ladder)}</td><td>{states}</td><td>{bits:.2f}</td><td>{q16_min}</td><td>{q16_max}</td></tr>"
        )

    sections = []
    for ch in CHANNELS:
        if not data[ch]["monotonic"]:
            continue
        sections.append(
            f'''
<h2>{ch} channel</h2>
<img src="{ch.lower()}_monotonic_rank.png" alt="{ch} monotonic rank">
<img src="{ch.lower()}_full_distribution.png" alt="{ch} full distribution">
<img src="{ch.lower()}_delta_steps.png" alt="{ch} delta steps">
<img src="{ch.lower()}_bfi_usage.png" alt="{ch} bfi usage">
'''
        )

    html = f'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Temporal Brightness Visualizer Summary</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; }}
table {{ border-collapse: collapse; margin-bottom: 24px; }}
th, td {{ border: 1px solid #ccc; padding: 8px 12px; }}
img {{ max-width: 100%; height: auto; margin: 10px 0 28px 0; border: 1px solid #ddd; }}
h2 {{ margin-top: 36px; }}
</style>
</head>
<body>
<h1>Temporal Brightness Visualizer</h1>
<p>This report summarizes the monotonic temporal ladders and full 16-bit brightness distributions.</p>

<table>
<tr><th>Channel</th><th>Raw ladder states</th><th>Monotonic states</th><th>Effective bits</th><th>Min q16</th><th>Max q16</th></tr>
{''.join(rows)}
</table>

<h2>Combined overlay</h2>
<img src="all_channels_monotonic_overlay.png" alt="Combined monotonic overlay">

{''.join(sections)}
</body>
</html>
'''
    (out_dir / "brightness_visualizer_report.html").write_text(html, encoding="utf-8")

def main():
    ap = argparse.ArgumentParser(description="Temporal brightness distribution visualizer")
    ap.add_argument("--lut-dir", required=True, help="Directory containing *_temporal_ladder.json and *_monotonic_ladder.json")
    ap.add_argument("--out-dir", required=True, help="Directory for plots/report")
    args = ap.parse_args()

    lut_dir = Path(args.lut_dir)
    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)

    data = load_channel_data(lut_dir)
    plot_monotonic_rank(data, out_dir)
    plot_delta_stairs(data, out_dir)
    plot_full_distribution(data, out_dir)
    plot_combined_overlay(data, out_dir)
    plot_bfi_state_usage(data, out_dir)
    write_html_summary(data, out_dir)

    summary = {
        ch: {
            "raw_ladder_states": len(data[ch]["ladder"]),
            "monotonic_states": len(data[ch]["monotonic"]),
            "effective_bits": round(effective_bits(len(data[ch]["monotonic"])), 4),
        }
        for ch in CHANNELS
    }
    (out_dir / "brightness_visualizer_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "out_dir": str(out_dir), "summary": summary}, indent=2))

if __name__ == "__main__":
    main()
