#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

SCRIPT_DIR = Path(__file__).resolve().parent
CLI_PATH = SCRIPT_DIR / "temporal_ladder_tuning_tool.py"
DEFAULT_LUT_DIR = SCRIPT_DIR / "temporal_lut_outputs"
DEFAULT_CAPTURE_DIR = SCRIPT_DIR / "captures"
DEFAULT_SPILL_DIR = Path("./temporal_ladder_tuning_spill")


class TemporalLadderTuningApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Temporal Ladder Tuning Tool")
        self.root.geometry("1540x960")

        self.lut_dir_var = tk.StringVar(value=str(DEFAULT_LUT_DIR))
        self.capture_dir_var = tk.StringVar(value=str(DEFAULT_CAPTURE_DIR))
        self.measurement_xy_var = tk.StringVar(value=str(DEFAULT_LUT_DIR / "all_measurement_xy_points.csv"))
        self.report_out_var = tk.StringVar(value=str(DEFAULT_SPILL_DIR / "reports" / "temporal_ladder_tuning_report.json"))
        self.recapture_out_var = tk.StringVar(value=str(DEFAULT_SPILL_DIR / "plans" / "temporal_ladder_blend8_recapture_plan.csv"))
        self.filtered_capture_out_var = tk.StringVar(value=str(DEFAULT_SPILL_DIR / "captures" / "plan_capture_outliers_pruned.csv"))
        self.out_dir_var = tk.StringVar(value=str(DEFAULT_SPILL_DIR / "ladders" / "tuned_ladders"))
        self.spill_dir_var = tk.StringVar(value=str(DEFAULT_SPILL_DIR))
        self.action_var = tk.StringVar(value="fix")
        self.monotonic_tolerance_var = tk.StringVar(value="8")
        self.bfi_tolerance_var = tk.StringVar(value="8")
        self.lower_floor_tolerance_var = tk.StringVar(value="8")
        self.upper_residual_floor_var = tk.StringVar(value="96")
        self.upper_residual_ratio_var = tk.StringVar(value="0.015")
        self.xy_drift_var = tk.StringVar(value="0.010")
        self.xy_spread_var = tk.StringVar(value="0.0035")
        self.min_xy_samples_var = tk.StringVar(value="2")
        self.filtered_capture_chunk_rows_var = tk.StringVar(value="100000")
        self.default_recapture_repeats_var = tk.StringVar(value="4")
        self.channel_vars = {channel: tk.BooleanVar(value=True) for channel in ["R", "G", "B", "W"]}

        self.report_data: dict | None = None
        self.report_rows: list[dict] = []

        self._build_ui()

    def _build_ui(self) -> None:
        controls = ttk.Frame(self.root, padding=10)
        controls.pack(side=tk.TOP, fill=tk.X)

        self._add_path_row(controls, 0, "LUT dir", self.lut_dir_var, self._pick_directory)
        self._add_path_row(controls, 1, "Capture dir", self.capture_dir_var, self._pick_directory)
        self._add_path_row(controls, 2, "Measurement XY", self.measurement_xy_var, self._pick_file)
        self._add_path_row(controls, 3, "Spill dir", self.spill_dir_var, self._pick_directory)
        self._add_path_row(controls, 4, "Report out", self.report_out_var, self._pick_save_json)
        self._add_path_row(controls, 5, "Recapture plan", self.recapture_out_var, self._pick_save_csv)
        self._add_path_row(controls, 6, "Filtered capture", self.filtered_capture_out_var, self._pick_save_csv)
        self._add_path_row(controls, 7, "Apply out dir", self.out_dir_var, self._pick_directory)

        settings = ttk.Frame(controls)
        settings.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        for column in range(12):
            settings.columnconfigure(column, weight=1)

        self._add_entry(settings, 0, 0, "Upper tol q16", self.monotonic_tolerance_var)
        self._add_entry(settings, 0, 2, "BFI tol q16", self.bfi_tolerance_var)
        self._add_entry(settings, 0, 4, "Lower-floor tol q16", self.lower_floor_tolerance_var)
        self._add_entry(settings, 0, 6, "XY drift", self.xy_drift_var)
        self._add_entry(settings, 0, 8, "XY spread", self.xy_spread_var)
        self._add_entry(settings, 0, 10, "Min XY samples", self.min_xy_samples_var)
        self._add_entry(settings, 1, 0, "Upper residual q16", self.upper_residual_floor_var)
        self._add_entry(settings, 1, 2, "Upper residual ratio", self.upper_residual_ratio_var)
        self._add_entry(settings, 1, 4, "Filtered chunk rows", self.filtered_capture_chunk_rows_var)
        self._add_entry(settings, 1, 6, "Default recapture repeats", self.default_recapture_repeats_var)

        channel_frame = ttk.LabelFrame(controls, text="Channels", padding=8)
        channel_frame.grid(row=9, column=0, sticky="w", pady=(10, 0))
        for idx, channel in enumerate(self.channel_vars):
            ttk.Checkbutton(channel_frame, text=channel, variable=self.channel_vars[channel]).grid(row=0, column=idx, padx=(0, 12))

        action_frame = ttk.LabelFrame(controls, text="Action", padding=8)
        action_frame.grid(row=9, column=1, sticky="w", pady=(10, 0))
        ttk.Combobox(action_frame, textvariable=self.action_var, values=["fix", "prune", "report"], state="readonly", width=10).grid(row=0, column=0)

        buttons = ttk.Frame(controls)
        buttons.grid(row=9, column=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Analyze", command=self.run_analyze).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Apply", command=self.run_apply).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Reload Report", command=self.load_existing_report).pack(side=tk.LEFT)

        content = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        content.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        left = ttk.Frame(content, padding=10)
        right = ttk.Frame(content, padding=10)
        content.add(left, weight=3)
        content.add(right, weight=2)

        summary_frame = ttk.LabelFrame(left, text="Summary", padding=8)
        summary_frame.pack(fill=tk.X)
        self.summary_text = tk.Text(summary_frame, height=7, wrap="word")
        self.summary_text.pack(fill=tk.BOTH, expand=True)

        table_frame = ttk.LabelFrame(left, text="Flagged States", padding=8)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        columns = ("channel", "mode", "lower", "upper", "bfi", "output_q16", "pass", "severity", "action")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=24)
        for name, width in {
            "channel": 60,
            "mode": 90,
            "lower": 70,
            "upper": 70,
            "bfi": 70,
            "output_q16": 100,
            "pass": 160,
            "severity": 90,
            "action": 90,
        }.items():
            self.tree.heading(name, text=name)
            self.tree.column(name, width=width, stretch=(name == "pass"))
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        tree_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        plot_frame = ttk.LabelFrame(right, text="Quick Plot", padding=8)
        plot_frame.pack(fill=tk.BOTH, expand=True)
        self.figure = Figure(figsize=(7.5, 6.0), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_xlabel("Rank")
        self.ax.set_ylabel("output_q16")
        self.ax.grid(True, alpha=0.25)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        detail_frame = ttk.LabelFrame(right, text="Finding Detail", padding=8)
        detail_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.detail_text = tk.Text(detail_frame, wrap="word")
        self.detail_text.pack(fill=tk.BOTH, expand=True)

    def _add_path_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, picker) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable, width=140).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(parent, text="Browse", command=lambda var=variable, fn=picker: fn(var)).grid(row=row, column=2, sticky="e", pady=4)
        parent.columnconfigure(1, weight=1)

    def _add_entry(self, parent: ttk.Frame, row: int, column: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=(0, 6))
        ttk.Entry(parent, textvariable=variable, width=10).grid(row=row, column=column + 1, sticky="w", padx=(0, 16))

    def _pick_directory(self, variable: tk.StringVar) -> None:
        chosen = filedialog.askdirectory(initialdir=Path(variable.get()).parent if variable.get() else SCRIPT_DIR)
        if chosen:
            variable.set(chosen)

    def _pick_file(self, variable: tk.StringVar) -> None:
        chosen = filedialog.askopenfilename(initialdir=Path(variable.get()).parent if variable.get() else SCRIPT_DIR, filetypes=[("CSV files", "*.csv"), ("All files", "*")])
        if chosen:
            variable.set(chosen)

    def _pick_save_json(self, variable: tk.StringVar) -> None:
        chosen = filedialog.asksaveasfilename(initialdir=Path(variable.get()).parent if variable.get() else SCRIPT_DIR, defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if chosen:
            variable.set(chosen)

    def _pick_save_csv(self, variable: tk.StringVar) -> None:
        chosen = filedialog.asksaveasfilename(initialdir=Path(variable.get()).parent if variable.get() else SCRIPT_DIR, defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if chosen:
            variable.set(chosen)

    def _selected_channels(self) -> list[str]:
        selected = [channel for channel, enabled in self.channel_vars.items() if enabled.get()]
        return selected or ["ALL"]

    def _base_command(self) -> list[str]:
        cmd = [
            sys.executable,
            str(CLI_PATH),
            "--lut-dir",
            self.lut_dir_var.get().strip(),
            "--capture-dir",
            self.capture_dir_var.get().strip(),
            "--spill-dir",
            self.spill_dir_var.get().strip(),
            "--channels",
            *self._selected_channels(),
            "--monotonic-tolerance-q16",
            self.monotonic_tolerance_var.get().strip(),
            "--bfi-tolerance-q16",
            self.bfi_tolerance_var.get().strip(),
            "--lower-floor-tolerance-q16",
            self.lower_floor_tolerance_var.get().strip(),
            "--upper-residual-floor-q16",
            self.upper_residual_floor_var.get().strip(),
            "--upper-residual-ratio",
            self.upper_residual_ratio_var.get().strip(),
            "--xy-drift-threshold",
            self.xy_drift_var.get().strip(),
            "--xy-spread-threshold",
            self.xy_spread_var.get().strip(),
            "--min-xy-samples",
            self.min_xy_samples_var.get().strip(),
            "--report-out",
            self.report_out_var.get().strip(),
            "--default-recapture-repeats",
            self.default_recapture_repeats_var.get().strip(),
        ]
        measurement_xy = self.measurement_xy_var.get().strip()
        if measurement_xy:
            cmd.extend(["--measurement-xy", measurement_xy])
        recapture_out = self.recapture_out_var.get().strip()
        if recapture_out:
            cmd.extend(["--recapture-out", recapture_out])
        filtered_capture_out = self.filtered_capture_out_var.get().strip()
        if filtered_capture_out:
            cmd.extend(["--filtered-capture-out", filtered_capture_out])
            cmd.extend(["--filtered-capture-chunk-rows", self.filtered_capture_chunk_rows_var.get().strip()])
        return cmd

    def run_analyze(self) -> None:
        cmd = [sys.executable, str(CLI_PATH), "analyze", *self._base_command()[2:]]
        self._run_subprocess(cmd)

    def run_apply(self) -> None:
        cmd = [
            sys.executable,
            str(CLI_PATH),
            "apply",
            *self._base_command()[2:],
            "--action",
            self.action_var.get().strip(),
            "--out-dir",
            self.out_dir_var.get().strip(),
        ]
        self._run_subprocess(cmd)

    def _run_subprocess(self, cmd: list[str]) -> None:
        env = dict(os.environ)
        spill_dir = self.spill_dir_var.get().strip()
        if spill_dir:
            env["TMP"] = spill_dir
            env["TEMP"] = spill_dir
            env["TMPDIR"] = spill_dir
            env["TEMPORAL_LADDER_TUNING_SPILL_DIR"] = spill_dir
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() or exc.stdout.strip() or "Unknown failure"
            messagebox.showerror("Temporal Ladder Tuning", stderr)
            return
        stdout = completed.stdout.strip()
        if stdout:
            self._set_text(self.detail_text, stdout)
        self.load_existing_report()

    def load_existing_report(self) -> None:
        report_path = Path(self.report_out_var.get().strip())
        if not report_path.exists():
            messagebox.showwarning("Temporal Ladder Tuning", f"Report does not exist yet:\n{report_path}")
            return
        self.report_data = json.loads(report_path.read_text(encoding="utf-8"))
        self.report_rows = list(self.report_data.get("findings", []))
        self._populate_summary()
        self._populate_table()
        self._draw_plot()

    def _populate_summary(self) -> None:
        if not self.report_data:
            return
        summary = self.report_data.get("summary", {})
        lines = [
            f"Action: {self.report_data.get('action', 'analyze')}",
            f"Total findings: {summary.get('total_findings', 0)}",
            "Findings by pass:",
        ]
        for name, count in sorted(summary.get("findings_by_pass", {}).items()):
            lines.append(f"  {name}: {count}")
        lines.append("Findings by channel:")
        for name, count in sorted(summary.get("findings_by_channel", {}).items()):
            lines.append(f"  {name}: {count}")
        self._set_text(self.summary_text, "\n".join(lines))

    def _populate_table(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for idx, row in enumerate(self.report_rows):
            self.tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(
                    row.get("channel", ""),
                    row.get("mode", ""),
                    row.get("lower_value", ""),
                    row.get("upper_value", ""),
                    row.get("bfi", ""),
                    row.get("output_q16", ""),
                    row.get("pass", ""),
                    f"{row.get('severity', 0):.4f}",
                    row.get("recommended_action", ""),
                ),
            )

    def _draw_plot(self, selected_row: dict | None = None) -> None:
        self.ax.clear()
        self.ax.set_xlabel("Rank")
        self.ax.set_ylabel("output_q16")
        self.ax.grid(True, alpha=0.25)
        if not self.report_rows:
            self.canvas.draw_idle()
            return

        rows = sorted(
            self.report_rows,
            key=lambda row: (
                row.get("channel", ""),
                int(row.get("lower_value", 0)),
                int(row.get("upper_value", 0)),
                int(row.get("bfi", 0)),
            ),
        )
        x_values = list(range(len(rows)))
        y_values = [float(row.get("output_q16", 0)) for row in rows]
        colors = ["tab:red" if row.get("recommended_action") == "recapture" else "tab:orange" for row in rows]
        self.ax.scatter(x_values, y_values, c=colors, alpha=0.85, s=42)
        if selected_row is not None:
            for idx, row in enumerate(rows):
                if self._same_state(row, selected_row):
                    self.ax.scatter([idx], [float(row.get("output_q16", 0))], c="tab:blue", s=120, edgecolors="black", linewidths=1.0)
                    break
        self.canvas.draw_idle()

    def _on_tree_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        row = self.report_rows[int(selection[0])]
        self._set_text(
            self.detail_text,
            "\n".join(
                [
                    f"Channel: {row.get('channel', '')}",
                    f"Mode: {row.get('mode', '')}",
                    f"State: lower={row.get('lower_value', '')}, upper={row.get('upper_value', '')}, bfi={row.get('bfi', '')}",
                    f"Output q16: {row.get('output_q16', '')}",
                    f"Estimated output: {row.get('estimated_output', '')}",
                    f"Pass: {row.get('pass', '')}",
                    f"Severity: {row.get('severity', 0):.6f}",
                    f"Recommended action: {row.get('recommended_action', '')}",
                    "",
                    str(row.get("detail", "")),
                ]
            ),
        )
        self._draw_plot(selected_row=row)

    def _same_state(self, left: dict, right: dict) -> bool:
        return (
            left.get("channel") == right.get("channel")
            and int(left.get("lower_value", 0)) == int(right.get("lower_value", 0))
            and int(left.get("upper_value", 0)) == int(right.get("upper_value", 0))
            and int(left.get("bfi", 0)) == int(right.get("bfi", 0))
        )

    def _set_text(self, widget: tk.Text, value: str) -> None:
        widget.delete("1.0", tk.END)
        widget.insert("1.0", value)


def main() -> None:
    root = tk.Tk()
    app = TemporalLadderTuningApp(root)
    _ = app
    root.mainloop()


if __name__ == "__main__":
    main()
