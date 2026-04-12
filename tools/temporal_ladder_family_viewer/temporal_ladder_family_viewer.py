#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import tkinter as tk
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = Path("./temporal_lut_outputs")
APP_STATE_PATH = SCRIPT_DIR / "temporal_ladder_family_viewer_state.json"
CHANNELS = ["R", "G", "B", "W"]
LADDER_KINDS = {
    "temporal": "temporal_ladder",
    "monotonic": "monotonic_ladder",
}
RELATION_LABELS = {
    "selected": "selected floor",
    "prev": "previous floor",
    "next": "next floor",
}
LINE_STYLES = {
    "selected": "-",
    "prev": "--",
    "next": ":",
}
LINE_ALPHAS = {
    "selected": 1.0,
    "prev": 0.72,
    "next": 0.72,
}
BFI_COLORS = [
    "#1f4b99",
    "#c24e00",
    "#2d7d46",
    "#9c2f7f",
    "#7a5500",
    "#007a78",
    "#b00020",
    "#5c4b8a",
]


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _bfi_color(bfi_value: int) -> str:
    return BFI_COLORS[bfi_value % len(BFI_COLORS)]


def _relation_for_floor(selected_floor: int, floor_value: int, previous_floor: int | None, next_floor: int | None) -> str:
    if floor_value == selected_floor:
        return "selected"
    if previous_floor is not None and floor_value == previous_floor:
        return "prev"
    if next_floor is not None and floor_value == next_floor:
        return "next"
    return "selected"


def _linear_fit(x_values: list[int], y_values: list[float]) -> tuple[float, float] | None:
    if len(x_values) < 2 or len(x_values) != len(y_values):
        return None
    n = float(len(x_values))
    sum_x = sum(float(value) for value in x_values)
    sum_y = sum(float(value) for value in y_values)
    sum_xx = sum(float(value) * float(value) for value in x_values)
    sum_xy = sum(float(x_values[idx]) * float(y_values[idx]) for idx in range(len(x_values)))
    denominator = n * sum_xx - sum_x * sum_x
    if abs(denominator) <= 1e-12:
        return None
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n
    return slope, intercept


def _family_mode(mode_name: object) -> str:
    mode_text = str(mode_name or "").strip()
    if mode_text == "fill8":
        return "blend8"
    return mode_text


def _effective_bfi(mode_name: object, bfi_value: object) -> int:
    if str(mode_name or "").strip() == "fill8":
        return 0
    return _safe_int(bfi_value, 0)


def _is_fill8_bfi0(mode_name: object, family_mode: object) -> bool:
    return str(mode_name or "").strip() == "fill8" and str(family_mode or "").strip() == "blend8"


class TemporalLadderFamilyViewerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Temporal Ladder Family Viewer")
        self._app_state = self._load_app_state()
        self.root.geometry(str(self._app_state.get("window_geometry", "1680x1020")))

        self.output_dir_var = tk.StringVar(value=self._app_state.get("last_output_dir", str(DEFAULT_OUTPUT_DIR)))
        self.channel_var = tk.StringVar(value=str(self._app_state.get("channel", "W")))
        self.ladder_kind_var = tk.StringVar(value=str(self._app_state.get("ladder_kind", "temporal")))
        self.mode_var = tk.StringVar(value=str(self._app_state.get("mode", "blend8")))
        self.lower_var = tk.StringVar(value=str(self._app_state.get("lower_value", "0")))
        self.bfi_var = tk.StringVar(value=str(self._app_state.get("bfi", "0")))
        self.show_all_bfis_var = tk.BooleanVar(value=bool(self._app_state.get("show_all_bfis", True)))
        self.show_prev_floor_var = tk.BooleanVar(value=bool(self._app_state.get("show_prev_floor", False)))
        self.show_next_floor_var = tk.BooleanVar(value=bool(self._app_state.get("show_next_floor", False)))
        self.show_slope_lines_var = tk.BooleanVar(value=bool(self._app_state.get("show_slope_lines", False)))
        self.prev_floor_label_var = tk.StringVar(value="Overlay previous floor")
        self.next_floor_label_var = tk.StringVar(value="Overlay next floor")
        self.manual_outlier_csv_var = tk.StringVar(
            value=str(self._app_state.get("manual_outlier_csv", Path("./reports/manual_ladder_outliers.csv")))
        )
        self.status_var = tk.StringVar(value="Index idle.")
        self.family_summary_var = tk.StringVar(value="No view loaded.")

        self.family_index: dict[tuple[str, str], list[tuple[str, int, int]]] = {}
        self.current_view_bundle: dict[str, object] | None = None
        self.displayed_ladder_rows: list[dict[str, object]] = []
        self.manual_outlier_keys: set[tuple[str, str, str, int, int, int, int]] = set()
        self.selected_row_keys: set[tuple[str, str, str, int, int, int, int]] = set()
        self._full_ladder_limits: tuple[float, float, float, float] | None = None
        self._full_aggregate_limits: tuple[float, float, float, float] | None = None
        self._pan_state: dict[str, object] | None = None
        self._mode_combo: ttk.Combobox | None = None
        self._lower_combo: ttk.Combobox | None = None
        self._bfi_combo: ttk.Combobox | None = None
        self._content_pane: ttk.Panedwindow | None = None
        self._bottom_pane: ttk.Panedwindow | None = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after_idle(self._apply_initial_layout)
        self.refresh_index()

    def _load_app_state(self) -> dict[str, object]:
        if not APP_STATE_PATH.exists() or not APP_STATE_PATH.is_file():
            return {}
        try:
            with APP_STATE_PATH.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
        except (OSError, ValueError, TypeError):
            return {}
        if not isinstance(loaded, dict):
            return {}
        return loaded

    def _save_app_state(self) -> None:
        state = {
            "last_output_dir": self.output_dir_var.get().strip(),
            "channel": self.channel_var.get().strip(),
            "ladder_kind": self.ladder_kind_var.get().strip(),
            "mode": self.mode_var.get().strip(),
            "lower_value": self.lower_var.get().strip(),
            "bfi": self.bfi_var.get().strip(),
            "show_all_bfis": bool(self.show_all_bfis_var.get()),
            "show_prev_floor": bool(self.show_prev_floor_var.get()),
            "show_next_floor": bool(self.show_next_floor_var.get()),
            "show_slope_lines": bool(self.show_slope_lines_var.get()),
            "manual_outlier_csv": self.manual_outlier_csv_var.get().strip(),
            "window_geometry": self.root.winfo_geometry(),
        }
        if self._content_pane is not None:
            try:
                state["content_sash"] = int(self._content_pane.sashpos(0))
            except (tk.TclError, IndexError):
                pass
        if self._bottom_pane is not None:
            try:
                state["bottom_sash"] = int(self._bottom_pane.sashpos(0))
            except (tk.TclError, IndexError):
                pass
        try:
            with APP_STATE_PATH.open("w", encoding="utf-8") as handle:
                json.dump(state, handle, indent=2)
        except OSError:
            return

    def _on_close(self) -> None:
        self._save_app_state()
        self.root.destroy()

    def _apply_initial_layout(self) -> None:
        if self._content_pane is not None:
            try:
                total_height = max(1, self._content_pane.winfo_height())
                content_sash = _safe_int(self._app_state.get("content_sash", 0), 0)
                if content_sash <= 0:
                    content_sash = int(total_height * 0.88)
                content_sash = max(220, min(total_height - 120, content_sash))
                self._content_pane.sashpos(0, content_sash)
            except (tk.TclError, IndexError):
                pass
        if self._bottom_pane is not None:
            try:
                total_width = max(1, self._bottom_pane.winfo_width())
                bottom_sash = _safe_int(self._app_state.get("bottom_sash", 0), 0)
                if bottom_sash <= 0:
                    bottom_sash = int(total_width * 0.74)
                bottom_sash = max(420, min(total_width - 260, bottom_sash))
                self._bottom_pane.sashpos(0, bottom_sash)
            except (tk.TclError, IndexError):
                pass

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=2)
        outer.pack(fill=tk.BOTH, expand=True)

        controls = ttk.LabelFrame(outer, text="Data Source", padding=2)
        controls.pack(fill=tk.X)
        ttk.Label(controls, text="Output dir").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.output_dir_var, width=132).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(controls, text="Browse", command=self._pick_output_dir).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(controls, text="Refresh Index", command=self.refresh_index).grid(row=0, column=3)
        controls.columnconfigure(1, weight=1)

        filters = ttk.LabelFrame(outer, text="Family Filter", padding=2)
        filters.pack(fill=tk.X, pady=(1, 0))

        ttk.Label(filters, text="Channel").grid(row=0, column=0, sticky="w")
        channel_combo = ttk.Combobox(filters, textvariable=self.channel_var, values=CHANNELS, width=8, state="readonly")
        channel_combo.grid(row=0, column=1, sticky="w", padx=(6, 16))
        channel_combo.bind("<<ComboboxSelected>>", self._on_filter_change)

        ttk.Label(filters, text="Ladder").grid(row=0, column=2, sticky="w")
        ladder_combo = ttk.Combobox(filters, textvariable=self.ladder_kind_var, values=list(LADDER_KINDS.keys()), width=12, state="readonly")
        ladder_combo.grid(row=0, column=3, sticky="w", padx=(6, 16))
        ladder_combo.bind("<<ComboboxSelected>>", self._on_filter_change)

        ttk.Label(filters, text="Mode").grid(row=0, column=4, sticky="w")
        self._mode_combo = ttk.Combobox(filters, textvariable=self.mode_var, width=12, state="readonly")
        self._mode_combo.grid(row=0, column=5, sticky="w", padx=(6, 16))
        self._mode_combo.bind("<<ComboboxSelected>>", self._on_filter_change)

        ttk.Label(filters, text="Lower floor").grid(row=0, column=6, sticky="w")
        self._lower_combo = ttk.Combobox(filters, textvariable=self.lower_var, width=10, state="readonly")
        self._lower_combo.grid(row=0, column=7, sticky="w", padx=(6, 16))
        self._lower_combo.bind("<<ComboboxSelected>>", self._on_filter_change)

        ttk.Label(filters, text="BFI").grid(row=0, column=8, sticky="w")
        self._bfi_combo = ttk.Combobox(filters, textvariable=self.bfi_var, width=10, state="readonly")
        self._bfi_combo.grid(row=0, column=9, sticky="w", padx=(6, 16))
        self._bfi_combo.bind("<<ComboboxSelected>>", self._on_filter_change)

        ttk.Button(filters, text="Load View", command=self.load_selected_family).grid(row=0, column=10, sticky="w", padx=(8, 8))
        ttk.Button(filters, text="Export Report", command=self.export_current_report).grid(row=0, column=11, sticky="w")

        overlays = ttk.LabelFrame(outer, text="Overlay Options", padding=2)
        overlays.pack(fill=tk.X, pady=(1, 0))
        ttk.Checkbutton(
            overlays,
            text="Show all BFIs for selected floor",
            variable=self.show_all_bfis_var,
            command=self._on_overlay_change,
        ).grid(row=0, column=0, sticky="w", padx=(0, 16))
        ttk.Checkbutton(
            overlays,
            textvariable=self.prev_floor_label_var,
            variable=self.show_prev_floor_var,
            command=self._on_overlay_change,
        ).grid(row=0, column=1, sticky="w", padx=(0, 16))
        ttk.Checkbutton(
            overlays,
            textvariable=self.next_floor_label_var,
            variable=self.show_next_floor_var,
            command=self._on_overlay_change,
        ).grid(row=0, column=2, sticky="w", padx=(0, 16))
        ttk.Checkbutton(
            overlays,
            text="Draw slope line for each displayed series",
            variable=self.show_slope_lines_var,
            command=self._on_overlay_change,
        ).grid(row=0, column=3, sticky="w", padx=(0, 16))

        marks = ttk.LabelFrame(outer, text="Manual Outlier Marks", padding=2)
        marks.pack(fill=tk.X, pady=(1, 0))
        ttk.Label(marks, text="CSV").grid(row=0, column=0, sticky="w")
        ttk.Entry(marks, textvariable=self.manual_outlier_csv_var, width=118).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(marks, text="Browse", command=self._pick_manual_outlier_csv).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(marks, text="Mark Selected Rows", command=self.mark_selected_rows).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(marks, text="Open Mark CSV Folder", command=self._open_manual_outlier_folder).grid(row=0, column=4)
        marks.columnconfigure(1, weight=1)

        ttk.Label(outer, textvariable=self.status_var).pack(fill=tk.X, pady=(1, 0))
        ttk.Label(outer, textvariable=self.family_summary_var).pack(fill=tk.X)

        content = ttk.Panedwindow(outer, orient=tk.VERTICAL)
        content.pack(fill=tk.BOTH, expand=True, pady=(1, 0))
        self._content_pane = content

        top = ttk.Frame(content, padding=0)
        bottom = ttk.Panedwindow(content, orient=tk.HORIZONTAL)
        self._bottom_pane = bottom
        content.add(top, weight=7)
        content.add(bottom, weight=2)

        plot_frame = ttk.Frame(top, padding=0)
        plot_frame.pack(fill=tk.BOTH, expand=True)
        self.figure = Figure(figsize=(9.6, 8.0), dpi=100)
        self.ladder_ax = self.figure.add_subplot(211)
        self.aggregate_ax = self.figure.add_subplot(212)
        self.figure.subplots_adjust(hspace=0.28, top=0.96, bottom=0.06, left=0.08, right=0.98)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.toolbar = NavigationToolbar2Tk(self.canvas, plot_frame, pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.pack(fill=tk.X)
        self.canvas.mpl_connect("scroll_event", self._on_plot_scroll)
        self.canvas.mpl_connect("button_press_event", self._on_plot_button_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_plot_motion)
        self.canvas.mpl_connect("button_release_event", self._on_plot_button_release)

        bottom_left = ttk.Frame(bottom, padding=0)
        bottom_right = ttk.Frame(bottom, padding=0)
        bottom.add(bottom_left, weight=5)
        bottom.add(bottom_right, weight=2)

        table_frame = ttk.LabelFrame(bottom_left, text="Displayed Ladder Rows", padding=2)
        table_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("relation", "mode", "lower", "upper", "value", "bfi", "q16", "estimated", "normalized")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=14, selectmode="none")
        widths = {
            "relation": 90,
            "mode": 80,
            "lower": 60,
            "upper": 60,
            "value": 60,
            "bfi": 50,
            "q16": 80,
            "estimated": 100,
            "normalized": 100,
        }
        for name in columns:
            self.tree.heading(name, text=name)
            self.tree.column(name, width=widths[name], stretch=name in {"relation", "estimated", "normalized"})
        self.tree.tag_configure("manual_outlier", background="#fde7ea", foreground="#7b1021")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<Button-1>", self._on_tree_click, add="+")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        tree_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        detail_frame = ttk.LabelFrame(bottom_right, text="View Notes", padding=2)
        detail_frame.pack(fill=tk.BOTH, expand=True)
        self.detail_text = tk.Text(detail_frame, wrap="word", height=10)
        self.detail_text.pack(fill=tk.BOTH, expand=True)

    def _pick_output_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.output_dir_var.get() or str(SCRIPT_DIR))
        if chosen:
            self.output_dir_var.set(chosen)
            self._save_app_state()
            self.refresh_index()

    def _pick_manual_outlier_csv(self) -> None:
        chosen = filedialog.asksaveasfilename(
            initialdir=Path(self.manual_outlier_csv_var.get()).parent if self.manual_outlier_csv_var.get().strip() else self.output_dir_var.get().strip(),
            initialfile=Path(self.manual_outlier_csv_var.get()).name if self.manual_outlier_csv_var.get().strip() else "manual_ladder_outliers.csv",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if chosen:
            self.manual_outlier_csv_var.set(chosen)
            self._save_app_state()
            self._refresh_manual_outlier_state()

    def _open_manual_outlier_folder(self) -> None:
        out_path = Path(self.manual_outlier_csv_var.get().strip())
        target_dir = out_path.parent if out_path.suffix else out_path
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(target_dir))
        except Exception as exc:
            messagebox.showerror("Temporal Ladder Family Viewer", f"Unable to open folder:\n{exc}")

    def _on_filter_change(self, _event=None) -> None:
        self._save_app_state()
        self._sync_filter_values()

    def _on_overlay_change(self) -> None:
        self._save_app_state()
        self._reload_overlay_data()

    def _reload_overlay_data(self) -> None:
        """Re-read displayed data with current overlay settings and redraw, preserving zoom."""
        prior_selection_keys = set(self.selected_row_keys)
        try:
            ladder_rows = self._read_displayed_ladder_rows()
        except FileNotFoundError:
            return
        measured_rows = self._read_displayed_measured_rows()
        aggregate_rows = self._read_displayed_aggregate_rows()
        if not ladder_rows:
            return

        ladder_limits = tuple(self.ladder_ax.get_xlim()) + tuple(self.ladder_ax.get_ylim())
        aggregate_limits = tuple(self.aggregate_ax.get_xlim()) + tuple(self.aggregate_ax.get_ylim())

        series_summaries = self._build_series_summaries(ladder_rows, measured_rows, aggregate_rows)
        metadata = {
            "output_dir": self.output_dir_var.get().strip(),
            "channel": self.channel_var.get().strip(),
            "ladder_kind": self.ladder_kind_var.get().strip(),
            "mode": self.mode_var.get().strip(),
            "selected_lower_value": _safe_int(self.lower_var.get(), 0),
            "selected_bfi": _safe_int(self.bfi_var.get(), 0),
            "show_all_bfis_for_selected_floor": bool(self.show_all_bfis_var.get()),
            "show_previous_floor": bool(self.show_prev_floor_var.get()),
            "show_next_floor": bool(self.show_next_floor_var.get()),
            "show_slope_lines": bool(self.show_slope_lines_var.get()),
        }
        self.current_view_bundle = {
            "metadata": metadata,
            "ladder_rows": ladder_rows,
            "measured_rows": measured_rows,
            "aggregate_rows": aggregate_rows,
            "series_summaries": series_summaries,
            "manual_outlier_csv": self.manual_outlier_csv_var.get().strip(),
        }
        self.displayed_ladder_rows = list(ladder_rows)
        available_row_keys = {self._row_key(row) for row in self.displayed_ladder_rows}
        self.selected_row_keys = {row_key for row_key in prior_selection_keys if row_key in available_row_keys}
        self.manual_outlier_keys = self._load_manual_outlier_keys()

        self._populate_tree(ladder_rows)
        self._apply_tree_row_tags()
        self._sync_tree_selection_from_keys()
        self._draw_family(ladder_rows, measured_rows, aggregate_rows)

        # Restore zoom after redraw
        self.ladder_ax.set_xlim(ladder_limits[0], ladder_limits[1])
        self.ladder_ax.set_ylim(ladder_limits[2], ladder_limits[3])
        self.aggregate_ax.set_xlim(aggregate_limits[0], aggregate_limits[1])
        self.aggregate_ax.set_ylim(aggregate_limits[2], aggregate_limits[3])
        self.canvas.draw_idle()

        self._write_detail(series_summaries, ladder_rows, measured_rows, aggregate_rows)
        self._save_app_state()

    def _ladder_csv_path(self, channel: str, ladder_kind: str) -> Path:
        suffix = LADDER_KINDS[ladder_kind]
        return Path(self.output_dir_var.get().strip()) / f"{channel.lower()}_{suffix}.csv"

    def _measured_csv_path(self, channel: str) -> Path:
        return Path(self.output_dir_var.get().strip()) / f"{channel.lower()}_measured_points.csv"

    def _aggregate_csv_path(self) -> Path:
        return Path(self.output_dir_var.get().strip()) / "all_measurement_points.csv"

    def refresh_index(self) -> None:
        output_dir = Path(self.output_dir_var.get().strip())
        if not output_dir.exists():
            messagebox.showerror("Temporal Ladder Family Viewer", f"Output dir does not exist:\n{output_dir}")
            return

        family_index: dict[tuple[str, str], set[tuple[str, int, int]]] = defaultdict(set)
        blend8_lowers: dict[tuple[str, str], set[int]] = defaultdict(set)
        has_fill8_bfi0: set[tuple[str, str]] = set()
        scanned_files = 0
        for channel in CHANNELS:
            for ladder_kind in LADDER_KINDS:
                csv_path = self._ladder_csv_path(channel, ladder_kind)
                if not csv_path.exists():
                    continue
                scanned_files += 1
                with csv_path.open("r", encoding="utf-8", newline="") as handle:
                    for row in csv.DictReader(handle):
                        family_key = (channel, ladder_kind)
                        source_mode = str(row.get("mode", "") or "").strip()
                        family_mode = _family_mode(source_mode)
                        lower_value = _safe_int(row.get("lower_value", 0))
                        bfi_value = _effective_bfi(source_mode, row.get("bfi", 0))
                        family_index[family_key].add((family_mode, lower_value, bfi_value))
                        if family_mode == "blend8" and source_mode == "blend8":
                            blend8_lowers[family_key].add(lower_value)
                        if _is_fill8_bfi0(source_mode, family_mode):
                            has_fill8_bfi0.add(family_key)

        for family_key in has_fill8_bfi0:
            synthetic_lowers = set(blend8_lowers.get(family_key, set()))
            synthetic_lowers.add(0)
            for lower_value in synthetic_lowers:
                family_index[family_key].add(("blend8", lower_value, 0))

        self.family_index = {
            key: sorted(values, key=lambda item: (item[0], item[1], item[2]))
            for key, values in family_index.items()
        }
        self.status_var.set(f"Indexed {sum(len(values) for values in self.family_index.values())} families from {scanned_files} ladder files.")
        self._save_app_state()
        self._sync_filter_values(force_reset=True)

    def _current_families(self) -> list[tuple[str, int, int]]:
        return self.family_index.get((self.channel_var.get().strip(), self.ladder_kind_var.get().strip()), [])

    def _sync_filter_values(self, force_reset: bool = False) -> None:
        if self._mode_combo is None or self._lower_combo is None or self._bfi_combo is None:
            return

        families = self._current_families()
        modes = sorted({mode for mode, _lower, _bfi in families})
        if force_reset or self.mode_var.get().strip() not in modes:
            self.mode_var.set(modes[0] if modes else "")
        self._mode_combo["values"] = modes

        filtered_by_mode = [family for family in families if family[0] == self.mode_var.get().strip()]
        lowers = [str(value) for value in sorted({lower for _mode, lower, _bfi in filtered_by_mode})]
        if force_reset or self.lower_var.get().strip() not in lowers:
            self.lower_var.set(lowers[0] if lowers else "")
        self._lower_combo["values"] = lowers

        selected_floor = _safe_int(self.lower_var.get(), 0)
        filtered_by_lower = [family for family in filtered_by_mode if family[1] == selected_floor]
        bfis = [str(value) for value in sorted({bfi for _mode, _lower, bfi in filtered_by_lower})]
        if force_reset or self.bfi_var.get().strip() not in bfis:
            self.bfi_var.set(bfis[0] if bfis else "")
        self._bfi_combo["values"] = bfis

        previous_floor, next_floor = self._neighbor_floor_values()
        self.prev_floor_label_var.set(
            f"Overlay previous floor ({previous_floor})" if previous_floor is not None else "Overlay previous floor (none)"
        )
        self.next_floor_label_var.set(
            f"Overlay next floor ({next_floor})" if next_floor is not None else "Overlay next floor (none)"
        )
        if previous_floor is None:
            self.show_prev_floor_var.set(False)
        if next_floor is None:
            self.show_next_floor_var.set(False)

    def _neighbor_floor_values(self) -> tuple[int | None, int | None]:
        selected_floor = _safe_int(self.lower_var.get(), 0)
        floors = sorted(
            {
                lower
                for mode, lower, _bfi in self._current_families()
                if mode == self.mode_var.get().strip()
            }
        )
        previous_floor: int | None = None
        next_floor: int | None = None
        for floor_value in floors:
            if floor_value < selected_floor:
                previous_floor = floor_value
            if floor_value > selected_floor:
                next_floor = floor_value
                break
        return previous_floor, next_floor

    def _requested_floor_map(self) -> dict[int, str]:
        selected_floor = _safe_int(self.lower_var.get(), 0)
        previous_floor, next_floor = self._neighbor_floor_values()
        requested = {selected_floor: "selected"}
        if self.show_prev_floor_var.get() and previous_floor is not None:
            requested[previous_floor] = "prev"
        if self.show_next_floor_var.get() and next_floor is not None:
            requested[next_floor] = "next"
        return requested

    def _requested_bfi_map(self, requested_floors: dict[int, str]) -> dict[int, set[int] | None]:
        selected_floor = _safe_int(self.lower_var.get(), 0)
        selected_bfi = _safe_int(self.bfi_var.get(), 0)
        requested: dict[int, set[int] | None] = {}
        for floor_value in requested_floors:
            if self.show_all_bfis_var.get():
                # Show all BFI levels for every displayed floor
                requested[floor_value] = None
            elif floor_value == selected_floor:
                requested[floor_value] = {selected_bfi}
            else:
                # Overlay floor without show-all: show the selected BFI
                # plus BFI 0 (fill8) so the base ramp is always visible
                requested[floor_value] = {selected_bfi, 0} if selected_bfi != 0 else {0}
        return requested

    def _row_floor_targets(
        self,
        source_mode: str,
        family_mode: str,
        source_lower_value: int,
        requested_floors: dict[int, str],
        requested_bfis: dict[int, set[int] | None],
    ) -> list[tuple[int, str]]:
        if _is_fill8_bfi0(source_mode, family_mode):
            targets: list[tuple[int, str]] = []
            for floor_value, relation in requested_floors.items():
                allowed_bfis = requested_bfis.get(floor_value)
                if allowed_bfis is not None and 0 not in allowed_bfis:
                    continue
                targets.append((floor_value, relation))
            return targets

        relation = requested_floors.get(source_lower_value)
        if relation is None:
            return []
        return [(source_lower_value, relation)]

    def _read_displayed_ladder_rows(self) -> list[dict[str, object]]:
        csv_path = self._ladder_csv_path(self.channel_var.get().strip(), self.ladder_kind_var.get().strip())
        if not csv_path.exists():
            raise FileNotFoundError(f"Missing ladder CSV: {csv_path}")
        requested_floors = self._requested_floor_map()
        requested_bfis = self._requested_bfi_map(requested_floors)
        rows: list[dict[str, object]] = []
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                source_mode = str(row.get("mode", "")).strip()
                mode_name = _family_mode(source_mode)
                if mode_name != self.mode_var.get().strip():
                    continue
                source_lower_value = _safe_int(row.get("lower_value", 0))
                bfi_value = _effective_bfi(source_mode, row.get("bfi", 0))
                floor_targets = self._row_floor_targets(source_mode, mode_name, source_lower_value, requested_floors, requested_bfis)
                for lower_value, relation in floor_targets:
                    allowed_bfis = requested_bfis.get(lower_value)
                    if allowed_bfis is not None and bfi_value not in allowed_bfis:
                        continue
                    rows.append(
                        {
                            "relation": relation,
                            "channel": self.channel_var.get().strip(),
                            "mode": mode_name,
                            "source_mode": source_mode,
                            "lower_value": lower_value,
                            "upper_value": _safe_int(row.get("upper_value", 0)),
                            "value": _safe_int(row.get("value", row.get("upper_value", 0))),
                            "bfi": bfi_value,
                            "estimated_output": _safe_float(row.get("estimated_output", 0.0)),
                            "output_q16": _safe_int(row.get("output_q16", 0)),
                            "normalized_output": _safe_float(row.get("normalized_output", 0.0)),
                        }
                    )
        rows.sort(key=lambda item: (int(item["lower_value"]), int(item["bfi"]), int(item["upper_value"]), int(item["value"])))
        return rows

    def _read_displayed_measured_rows(self) -> list[dict[str, object]]:
        csv_path = self._measured_csv_path(self.channel_var.get().strip())
        if not csv_path.exists():
            return []
        requested_floors = self._requested_floor_map()
        requested_bfis = self._requested_bfi_map(requested_floors)
        rows: list[dict[str, object]] = []
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                source_mode = str(row.get("mode", "")).strip()
                mode_name = _family_mode(source_mode)
                if mode_name != self.mode_var.get().strip():
                    continue
                source_lower_value = _safe_int(row.get("lower_value", 0))
                bfi_value = _effective_bfi(source_mode, row.get("bfi", 0))
                floor_targets = self._row_floor_targets(source_mode, mode_name, source_lower_value, requested_floors, requested_bfis)
                for lower_value, relation in floor_targets:
                    allowed_bfis = requested_bfis.get(lower_value)
                    if allowed_bfis is not None and bfi_value not in allowed_bfis:
                        continue
                    rows.append(
                        {
                            "relation": relation,
                            "channel": self.channel_var.get().strip(),
                            "mode": mode_name,
                            "source_mode": source_mode,
                            "lower_value": lower_value,
                            "upper_value": _safe_int(row.get("upper_value", row.get("value", 0))),
                            "value": _safe_int(row.get("value", 0)),
                            "bfi": bfi_value,
                            "normalized_output": _safe_float(row.get("normalized_output", 0.0)),
                        }
                    )
        rows.sort(key=lambda item: (int(item["lower_value"]), int(item["bfi"]), int(item["upper_value"]), int(item["value"])))
        return rows

    def _read_displayed_aggregate_rows(self) -> list[dict[str, object]]:
        csv_path = self._aggregate_csv_path()
        if not csv_path.exists():
            return []
        requested_floors = self._requested_floor_map()
        requested_bfis = self._requested_bfi_map(requested_floors)
        rows: list[dict[str, object]] = []
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("channel", "")).strip().upper() != self.channel_var.get().strip().upper():
                    continue
                source_mode = str(row.get("mode", "")).strip()
                mode_name = _family_mode(source_mode)
                if mode_name != self.mode_var.get().strip():
                    continue
                source_lower_value = _safe_int(row.get("lower_value", 0))
                bfi_value = _effective_bfi(source_mode, row.get("bfi", 0))
                floor_targets = self._row_floor_targets(source_mode, mode_name, source_lower_value, requested_floors, requested_bfis)
                for lower_value, relation in floor_targets:
                    allowed_bfis = requested_bfis.get(lower_value)
                    if allowed_bfis is not None and bfi_value not in allowed_bfis:
                        continue
                    rows.append(
                        {
                            "relation": relation,
                            "channel": self.channel_var.get().strip(),
                            "mode": mode_name,
                            "source_mode": source_mode,
                            "lower_value": lower_value,
                            "upper_value": _safe_int(row.get("upper_value", row.get("value", 0))),
                            "value": _safe_int(row.get("value", 0)),
                            "bfi": bfi_value,
                            "y_measured_avg": _safe_float(row.get("y_measured_avg", 0.0)),
                            "y_est_nobfi": _safe_float(row.get("y_est_nobfi", 0.0)),
                            "samples": _safe_int(row.get("samples", 0)),
                        }
                    )
        rows.sort(key=lambda item: (int(item["lower_value"]), int(item["bfi"]), int(item["upper_value"]), int(item["value"])))
        return rows

    def _build_series_summaries(
        self,
        ladder_rows: list[dict[str, object]],
        measured_rows: list[dict[str, object]],
        aggregate_rows: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        measured_lookup = {
            (str(row["mode"]), int(row["lower_value"]), int(row["bfi"]), int(row["upper_value"]), int(row["value"])): float(row["normalized_output"])
            for row in measured_rows
        }
        aggregate_lookup = {
            (str(row["mode"]), int(row["lower_value"]), int(row["bfi"]), int(row["upper_value"]), int(row["value"])): row
            for row in aggregate_rows
        }
        grouped: dict[tuple[str, int, int, str], list[dict[str, object]]] = defaultdict(list)
        for row in ladder_rows:
            grouped[(str(row["mode"]), int(row["lower_value"]), int(row["bfi"]), str(row["relation"]))].append(row)

        summaries: list[dict[str, object]] = []
        for (mode_name, lower_value, bfi_value, relation), rows in sorted(grouped.items()):
            rows.sort(key=lambda item: (int(item["upper_value"]), int(item["value"])))
            q16_steps = [
                int(rows[idx]["output_q16"]) - int(rows[idx - 1]["output_q16"])
                for idx in range(1, len(rows))
            ]
            estimated_steps = [
                float(rows[idx]["estimated_output"]) - float(rows[idx - 1]["estimated_output"])
                for idx in range(1, len(rows))
            ]
            measured_gaps = []
            aggregate_gaps = []
            for row in rows:
                key = (mode_name, lower_value, bfi_value, int(row["upper_value"]), int(row["value"]))
                measured_norm = measured_lookup.get(key)
                if measured_norm is not None:
                    measured_gaps.append(abs(float(row["normalized_output"]) - float(measured_norm)))
                aggregate_row = aggregate_lookup.get(key)
                if aggregate_row is not None:
                    aggregate_gaps.append(abs(float(aggregate_row["y_measured_avg"]) - float(aggregate_row["y_est_nobfi"])))
            summaries.append(
                {
                    "relation": relation,
                    "mode": mode_name,
                    "lower_value": lower_value,
                    "bfi": bfi_value,
                    "rows": len(rows),
                    "upper_min": int(rows[0]["upper_value"]),
                    "upper_max": int(rows[-1]["upper_value"]),
                    "negative_estimated_steps": sum(1 for delta in estimated_steps if delta < 0.0),
                    "min_q16_step": min(q16_steps) if q16_steps else 0,
                    "max_q16": max((int(row["output_q16"]) for row in rows), default=0),
                    "max_estimated_output": max((float(row["estimated_output"]) for row in rows), default=0.0),
                    "max_normalized_gap": max(measured_gaps, default=0.0),
                    "max_aggregate_gap": max(aggregate_gaps, default=0.0),
                }
            )
        return summaries

    def _selected_tree_rows(self) -> list[dict[str, object]]:
        selected_rows: list[dict[str, object]] = []
        for item_id in self.tree.selection():
            try:
                row_index = int(item_id)
            except ValueError:
                continue
            if 0 <= row_index < len(self.displayed_ladder_rows):
                selected_rows.append(dict(self.displayed_ladder_rows[row_index]))
        return selected_rows

    def _row_key(self, row: dict[str, object], ladder_kind: str | None = None) -> tuple[str, str, str, int, int, int, int]:
        mode_name = _family_mode(row.get("mode", ""))
        return (
            str(row.get("channel", self.channel_var.get())).strip().upper(),
            str(ladder_kind or self.ladder_kind_var.get()).strip(),
            mode_name,
            _safe_int(row.get("lower_value", 0)),
            _safe_int(row.get("upper_value", 0)),
            _safe_int(row.get("value", 0)),
            _effective_bfi(row.get("mode", mode_name), row.get("bfi", 0)),
        )

    def _load_manual_outlier_keys(self) -> set[tuple[str, str, str, int, int, int, int]]:
        mark_path = Path(self.manual_outlier_csv_var.get().strip())
        if not mark_path.exists() or not mark_path.is_file():
            return set()

        current_channel = self.channel_var.get().strip().upper()
        current_ladder_kind = self.ladder_kind_var.get().strip()
        keys: set[tuple[str, str, str, int, int, int, int]] = set()
        with mark_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                row_channel = str(row.get("channel", "")).strip().upper()
                row_ladder_kind = str(row.get("ladder_kind", "")).strip()
                if row_channel and row_channel != current_channel:
                    continue
                if row_ladder_kind and row_ladder_kind != current_ladder_kind:
                    continue
                keys.add(
                    (
                        row_channel or current_channel,
                        row_ladder_kind or current_ladder_kind,
                        _family_mode(row.get("mode", "")),
                        _safe_int(row.get("lower_value", 0)),
                        _safe_int(row.get("upper_value", 0)),
                        _safe_int(row.get("value", 0)),
                        _effective_bfi(row.get("mode", ""), row.get("bfi", 0)),
                    )
                )
        return keys

    def _refresh_manual_outlier_state(self) -> None:
        self.manual_outlier_keys = self._load_manual_outlier_keys()
        if self.displayed_ladder_rows:
            self._apply_tree_row_tags()
        if self.current_view_bundle:
            self._redraw_current_view(preserve_limits=True)

    def _apply_tree_row_tags(self) -> None:
        for idx, row in enumerate(self.displayed_ladder_rows):
            tags: tuple[str, ...] = ()
            if self._row_key(row) in self.manual_outlier_keys:
                tags = ("manual_outlier",)
            self.tree.item(str(idx), tags=tags)

    def _on_tree_select(self, _event=None) -> None:
        self.selected_row_keys = {self._row_key(row) for row in self._selected_tree_rows()}
        if self.current_view_bundle:
            self._redraw_current_view(preserve_limits=True)

    def _on_tree_click(self, event) -> str | None:
        region = self.tree.identify("region", event.x, event.y)
        if region not in {"tree", "cell"}:
            return None

        item_id = self.tree.identify_row(event.y)
        if not item_id:
            self.tree.selection_remove(self.tree.selection())
            self._on_tree_select()
            return "break"

        current_selection = set(self.tree.selection())
        if item_id in current_selection:
            current_selection.remove(item_id)
        else:
            current_selection.add(item_id)
        self.tree.selection_set(tuple(sorted(current_selection, key=int)))
        self.tree.focus(item_id)
        self.tree.see(item_id)
        self._on_tree_select()
        return "break"

    def _toolbar_mode_active(self) -> bool:
        return bool(getattr(self.toolbar, "mode", ""))

    def _sync_tree_selection_from_keys(self) -> None:
        selected_items = [
            str(idx)
            for idx, row in enumerate(self.displayed_ladder_rows)
            if self._row_key(row) in self.selected_row_keys
        ]
        self.tree.selection_set(tuple(selected_items))
        if selected_items:
            self.tree.focus(selected_items[-1])
            self.tree.see(selected_items[-1])

    def _toggle_row_key_selection(self, row_key: tuple[str, str, str, int, int, int, int] | None) -> None:
        if row_key is None:
            return
        if row_key in self.selected_row_keys:
            self.selected_row_keys.remove(row_key)
        else:
            self.selected_row_keys.add(row_key)
        self._sync_tree_selection_from_keys()
        if self.current_view_bundle:
            self._redraw_current_view(preserve_limits=True)

    def _nearest_row_key_for_event(self, event) -> tuple[str, str, str, int, int, int, int] | None:
        if not self.current_view_bundle or event.inaxes not in {self.ladder_ax, self.aggregate_ax}:
            return None

        ladder_rows = list(self.current_view_bundle.get("ladder_rows", []))
        measured_rows = list(self.current_view_bundle.get("measured_rows", []))
        aggregate_rows = list(self.current_view_bundle.get("aggregate_rows", []))
        candidates: list[tuple[tuple[str, str, str, int, int, int, int], float, float]] = []
        if event.inaxes is self.ladder_ax:
            candidates.extend(
                (self._row_key(row), float(row["upper_value"]), float(row["normalized_output"]))
                for row in ladder_rows
            )
            candidates.extend(
                (self._row_key(row), float(row["upper_value"]), float(row["normalized_output"]))
                for row in measured_rows
            )
        else:
            for row in aggregate_rows:
                row_key = self._row_key(row)
                candidates.append((row_key, float(row["upper_value"]), float(row["y_measured_avg"])))
                candidates.append((row_key, float(row["upper_value"]), float(row["y_est_nobfi"])))

        if not candidates:
            return None

        click_x = float(event.x)
        click_y = float(event.y)
        best_key: tuple[str, str, str, int, int, int, int] | None = None
        best_distance: float | None = None
        for row_key, x_value, y_value in candidates:
            point_x, point_y = event.inaxes.transData.transform((x_value, y_value))
            distance = ((point_x - click_x) ** 2 + (point_y - click_y) ** 2) ** 0.5
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_key = row_key
        if best_distance is None or best_distance > 14.0:
            return None
        return best_key

    def _zoom_axis_about_point(self, ax, center_x: float, center_y: float, scale_factor: float) -> None:
        current_xlim = ax.get_xlim()
        current_ylim = ax.get_ylim()
        ax.set_xlim(
            center_x - (center_x - current_xlim[0]) * scale_factor,
            center_x + (current_xlim[1] - center_x) * scale_factor,
        )
        ax.set_ylim(
            center_y - (center_y - current_ylim[0]) * scale_factor,
            center_y + (current_ylim[1] - center_y) * scale_factor,
        )

    def _on_plot_scroll(self, event) -> None:
        if self._toolbar_mode_active() or event.inaxes not in {self.ladder_ax, self.aggregate_ax}:
            return

        if getattr(event, "step", 0) > 0 or getattr(event, "button", None) == "up":
            scale_factor = 0.85
        elif getattr(event, "step", 0) < 0 or getattr(event, "button", None) == "down":
            scale_factor = 1.0 / 0.85
        else:
            return

        ax = event.inaxes
        x_center = float(event.xdata) if event.xdata is not None else sum(ax.get_xlim()) * 0.5
        y_center = float(event.ydata) if event.ydata is not None else sum(ax.get_ylim()) * 0.5
        self._zoom_axis_about_point(ax, x_center, y_center, scale_factor)
        self.canvas.draw_idle()

    def _on_plot_button_press(self, event) -> None:
        if self._toolbar_mode_active() or event.inaxes not in {self.ladder_ax, self.aggregate_ax}:
            return
        if event.button == 1:
            self._toggle_row_key_selection(self._nearest_row_key_for_event(event))
            return
        if event.button not in {2, 3}:
            return

        self._pan_state = {
            "ax": event.inaxes,
            "button": event.button,
            "x": float(event.x),
            "y": float(event.y),
            "xlim": tuple(event.inaxes.get_xlim()),
            "ylim": tuple(event.inaxes.get_ylim()),
        }

    def _on_plot_motion(self, event) -> None:
        if not self._pan_state:
            return
        ax = self._pan_state.get("ax")
        if event.inaxes is not ax:
            return

        origin_x = float(self._pan_state["x"])
        origin_y = float(self._pan_state["y"])
        start_xlim = self._pan_state["xlim"]
        start_ylim = self._pan_state["ylim"]
        bbox = ax.bbox
        if bbox.width <= 0.0 or bbox.height <= 0.0:
            return

        delta_ratio_x = (float(event.x) - origin_x) / float(bbox.width)
        delta_ratio_y = (float(event.y) - origin_y) / float(bbox.height)
        span_x = float(start_xlim[1]) - float(start_xlim[0])
        span_y = float(start_ylim[1]) - float(start_ylim[0])
        shift_x = delta_ratio_x * span_x
        shift_y = delta_ratio_y * span_y
        ax.set_xlim(float(start_xlim[0]) - shift_x, float(start_xlim[1]) - shift_x)
        ax.set_ylim(float(start_ylim[0]) - shift_y, float(start_ylim[1]) - shift_y)
        self.canvas.draw_idle()

    def _on_plot_button_release(self, event) -> None:
        if not self._pan_state:
            return
        if event.button == self._pan_state.get("button"):
            self._pan_state = None

    def _redraw_current_view(self, preserve_limits: bool = True) -> None:
        if not self.current_view_bundle:
            return
        ladder_limits = tuple(self.ladder_ax.get_xlim()) + tuple(self.ladder_ax.get_ylim()) if preserve_limits else None
        aggregate_limits = tuple(self.aggregate_ax.get_xlim()) + tuple(self.aggregate_ax.get_ylim()) if preserve_limits else None
        ladder_rows = list(self.current_view_bundle.get("ladder_rows", []))
        measured_rows = list(self.current_view_bundle.get("measured_rows", []))
        aggregate_rows = list(self.current_view_bundle.get("aggregate_rows", []))
        self._draw_family(ladder_rows, measured_rows, aggregate_rows)
        if ladder_limits is not None:
            self.ladder_ax.set_xlim(ladder_limits[0], ladder_limits[1])
            self.ladder_ax.set_ylim(ladder_limits[2], ladder_limits[3])
        if aggregate_limits is not None:
            self.aggregate_ax.set_xlim(aggregate_limits[0], aggregate_limits[1])
            self.aggregate_ax.set_ylim(aggregate_limits[2], aggregate_limits[3])
        if ladder_limits is not None or aggregate_limits is not None:
            self.canvas.draw_idle()

    def _set_axis_limits(
        self,
        ax,
        points: list[tuple[float, float]],
        fallback_limits: tuple[float, float, float, float] | None,
    ) -> None:
        if not points:
            if fallback_limits is not None:
                ax.set_xlim(fallback_limits[0], fallback_limits[1])
                ax.set_ylim(fallback_limits[2], fallback_limits[3])
            return

        x_values = [point[0] for point in points]
        y_values = [point[1] for point in points]
        min_x = min(x_values)
        max_x = max(x_values)
        min_y = min(y_values)
        max_y = max(y_values)

        x_span = max_x - min_x
        y_span = max_y - min_y
        x_pad = max(1.0, x_span * 0.12)
        y_pad = max(0.001, y_span * 0.16)
        if x_span <= 1e-9:
            x_pad = max(x_pad, 2.0)
        if y_span <= 1e-9:
            y_pad = max(y_pad, max(abs(max_y), 0.01) * 0.08)

        ax.set_xlim(min_x - x_pad, max_x + x_pad)
        ax.set_ylim(min_y - y_pad, max_y + y_pad)

    def _apply_selection_zoom(
        self,
        ladder_rows: list[dict[str, object]],
        measured_rows: list[dict[str, object]],
        aggregate_rows: list[dict[str, object]],
    ) -> None:
        if not self.selected_row_keys:
            self._set_axis_limits(self.ladder_ax, [], self._full_ladder_limits)
            self._set_axis_limits(self.aggregate_ax, [], self._full_aggregate_limits)
            return

        selected_ladder_points = [
            (float(row["upper_value"]), float(row["normalized_output"]))
            for row in ladder_rows
            if self._row_key(row) in self.selected_row_keys
        ]
        selected_ladder_points.extend(
            (
                float(row["upper_value"]),
                float(row["normalized_output"]),
            )
            for row in measured_rows
            if self._row_key(row) in self.selected_row_keys
        )
        selected_aggregate_points: list[tuple[float, float]] = []
        for row in aggregate_rows:
            if self._row_key(row) not in self.selected_row_keys:
                continue
            selected_aggregate_points.append((float(row["upper_value"]), float(row["y_measured_avg"])))
            selected_aggregate_points.append((float(row["upper_value"]), float(row["y_est_nobfi"])))

        self._set_axis_limits(self.ladder_ax, selected_ladder_points, self._full_ladder_limits)
        self._set_axis_limits(self.aggregate_ax, selected_aggregate_points, self._full_aggregate_limits)

    def mark_selected_rows(self) -> None:
        selected_rows = self._selected_tree_rows()
        if not selected_rows:
            messagebox.showerror("Temporal Ladder Family Viewer", "Select one or more displayed ladder rows to mark.")
            return
        mark_path = Path(self.manual_outlier_csv_var.get().strip())
        mark_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = dict(self.current_view_bundle.get("metadata", {})) if self.current_view_bundle else {}
        timestamp = datetime.now().isoformat(timespec="seconds")
        mark_rows = []
        for row in selected_rows:
            mark_rows.append(
                {
                    "marked_at": timestamp,
                    "channel": row.get("channel", metadata.get("channel", "")),
                    "ladder_kind": metadata.get("ladder_kind", ""),
                    "selected_mode": metadata.get("mode", ""),
                    "selected_lower_value": metadata.get("selected_lower_value", ""),
                    "selected_bfi": metadata.get("selected_bfi", ""),
                    "relation": row.get("relation", ""),
                    "mode": row.get("mode", ""),
                    "lower_value": row.get("lower_value", ""),
                    "upper_value": row.get("upper_value", ""),
                    "value": row.get("value", ""),
                    "bfi": row.get("bfi", ""),
                    "estimated_output": row.get("estimated_output", ""),
                    "output_q16": row.get("output_q16", ""),
                    "normalized_output": row.get("normalized_output", ""),
                }
            )
        self._append_csv_rows(mark_path, mark_rows)
        self._refresh_manual_outlier_state()
        self.status_var.set(f"Marked {len(mark_rows)} row(s) into {mark_path.name}")

    def _append_csv_rows(self, path: Path, rows: list[dict[str, object]]) -> None:
        if not rows:
            return
        fieldnames = list(rows[0].keys())
        file_exists = path.exists() and path.stat().st_size > 0
        with path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerows(rows)

    def load_selected_family(self) -> None:
        prior_selection_keys = set(self.selected_row_keys)

        # Capture current zoom before redraw so we can restore it.
        has_prior_view = self.current_view_bundle is not None
        if has_prior_view:
            ladder_limits = tuple(self.ladder_ax.get_xlim()) + tuple(self.ladder_ax.get_ylim())
            aggregate_limits = tuple(self.aggregate_ax.get_xlim()) + tuple(self.aggregate_ax.get_ylim())

        try:
            ladder_rows = self._read_displayed_ladder_rows()
        except FileNotFoundError as exc:
            messagebox.showerror("Temporal Ladder Family Viewer", str(exc))
            return

        measured_rows = self._read_displayed_measured_rows()
        aggregate_rows = self._read_displayed_aggregate_rows()

        if not ladder_rows:
            self.status_var.set("No rows matched the selected view.")
            self.family_summary_var.set("No view loaded.")
            self.current_view_bundle = None
            self._clear_views()
            return

        series_summaries = self._build_series_summaries(ladder_rows, measured_rows, aggregate_rows)
        metadata = {
            "output_dir": self.output_dir_var.get().strip(),
            "channel": self.channel_var.get().strip(),
            "ladder_kind": self.ladder_kind_var.get().strip(),
            "mode": self.mode_var.get().strip(),
            "selected_lower_value": _safe_int(self.lower_var.get(), 0),
            "selected_bfi": _safe_int(self.bfi_var.get(), 0),
            "show_all_bfis_for_selected_floor": bool(self.show_all_bfis_var.get()),
            "show_previous_floor": bool(self.show_prev_floor_var.get()),
            "show_next_floor": bool(self.show_next_floor_var.get()),
            "show_slope_lines": bool(self.show_slope_lines_var.get()),
        }
        self.current_view_bundle = {
            "metadata": metadata,
            "ladder_rows": ladder_rows,
            "measured_rows": measured_rows,
            "aggregate_rows": aggregate_rows,
            "series_summaries": series_summaries,
            "manual_outlier_csv": self.manual_outlier_csv_var.get().strip(),
        }
        self.displayed_ladder_rows = list(ladder_rows)
        available_row_keys = {self._row_key(row) for row in self.displayed_ladder_rows}
        self.selected_row_keys = {row_key for row_key in prior_selection_keys if row_key in available_row_keys}
        self.manual_outlier_keys = self._load_manual_outlier_keys()

        self._populate_tree(ladder_rows)
        self._apply_tree_row_tags()
        self._sync_tree_selection_from_keys()
        self._draw_family(ladder_rows, measured_rows, aggregate_rows)

        if has_prior_view:
            self.ladder_ax.set_xlim(ladder_limits[0], ladder_limits[1])
            self.ladder_ax.set_ylim(ladder_limits[2], ladder_limits[3])
            self.aggregate_ax.set_xlim(aggregate_limits[0], aggregate_limits[1])
            self.aggregate_ax.set_ylim(aggregate_limits[2], aggregate_limits[3])
            self.canvas.draw_idle()

        self._write_detail(series_summaries, ladder_rows, measured_rows, aggregate_rows)
        self._save_app_state()

        relations_present = sorted({str(row["relation"]) for row in ladder_rows})
        self.status_var.set(
            f"Loaded {len(series_summaries)} series, {len(ladder_rows)} ladder rows, {len(measured_rows)} measured rows, and {len(aggregate_rows)} aggregate rows."
        )
        self.family_summary_var.set(
            f"{metadata['channel']} {metadata['ladder_kind']} {metadata['mode']} lower={metadata['selected_lower_value']} BFI={metadata['selected_bfi']} relations={','.join(relations_present)}"
        )

    def export_current_report(self) -> None:
        if not self.current_view_bundle:
            messagebox.showerror("Temporal Ladder Family Viewer", "Load a view before exporting a report.")
            return

        metadata = dict(self.current_view_bundle.get("metadata", {}))
        default_name = (
            f"family_report_{metadata.get('channel', 'x').lower()}_"
            f"{metadata.get('mode', 'mode')}_lower{metadata.get('selected_lower_value', 0)}_"
            f"bfi{metadata.get('selected_bfi', 0)}.json"
        )
        report_path = filedialog.asksaveasfilename(
            initialdir=self.output_dir_var.get().strip() or str(SCRIPT_DIR),
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if not report_path:
            return

        report_file = Path(report_path)
        stem = report_file.with_suffix("")
        png_path = stem.with_suffix(".png")
        ladder_csv_path = Path(f"{stem}_ladder.csv")
        measured_csv_path = Path(f"{stem}_measured.csv")
        aggregate_csv_path = Path(f"{stem}_aggregate.csv")

        with report_file.open("w", encoding="utf-8") as handle:
            json.dump(self.current_view_bundle, handle, indent=2)
        self.figure.savefig(png_path, dpi=160, bbox_inches="tight")
        self._write_csv(ladder_csv_path, list(self.current_view_bundle.get("ladder_rows", [])))
        self._write_csv(measured_csv_path, list(self.current_view_bundle.get("measured_rows", [])))
        self._write_csv(aggregate_csv_path, list(self.current_view_bundle.get("aggregate_rows", [])))

        self.status_var.set(
            f"Exported report bundle: {report_file.name}, {png_path.name}, {ladder_csv_path.name}, {measured_csv_path.name}, {aggregate_csv_path.name}"
        )

    def _write_csv(self, path: Path, rows: list[dict[str, object]]) -> None:
        if not rows:
            with path.open("w", encoding="utf-8", newline="") as handle:
                handle.write("")
            return
        fieldnames = list(rows[0].keys())
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _clear_views(self) -> None:
        self.displayed_ladder_rows = []
        self.selected_row_keys = set()
        self._pan_state = None
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.detail_text.delete("1.0", tk.END)
        self.ladder_ax.clear()
        self.aggregate_ax.clear()
        self.canvas.draw_idle()

    def _populate_tree(self, ladder_rows: list[dict[str, object]]) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for idx, row in enumerate(ladder_rows):
            self.tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(
                    RELATION_LABELS.get(str(row["relation"]), str(row["relation"])),
                    row["mode"],
                    row["lower_value"],
                    row["upper_value"],
                    row["value"],
                    row["bfi"],
                    row["output_q16"],
                    f"{float(row['estimated_output']):.6f}",
                    f"{float(row['normalized_output']):.6f}",
                ),
            )

    def _draw_family(
        self,
        ladder_rows: list[dict[str, object]],
        measured_rows: list[dict[str, object]],
        aggregate_rows: list[dict[str, object]],
    ) -> None:
        self.ladder_ax.clear()
        self.aggregate_ax.clear()

        selected_floor = _safe_int(self.lower_var.get(), 0)
        previous_floor, next_floor = self._neighbor_floor_values()
        selected_bfi = _safe_int(self.bfi_var.get(), 0)

        grouped_ladder: dict[tuple[str, int, int, str], list[dict[str, object]]] = defaultdict(list)
        grouped_measured: dict[tuple[str, int, int, str], list[dict[str, object]]] = defaultdict(list)
        grouped_aggregate: dict[tuple[str, int, int, str], list[dict[str, object]]] = defaultdict(list)
        for row in ladder_rows:
            grouped_ladder[(str(row["mode"]), int(row["lower_value"]), int(row["bfi"]), str(row["relation"]))].append(row)
        for row in measured_rows:
            grouped_measured[(str(row["mode"]), int(row["lower_value"]), int(row["bfi"]), str(row["relation"]))].append(row)
        for row in aggregate_rows:
            grouped_aggregate[(str(row["mode"]), int(row["lower_value"]), int(row["bfi"]), str(row["relation"]))].append(row)

        for (mode_name, lower_value, bfi_value, relation), series_rows in sorted(grouped_ladder.items()):
            color = _bfi_color(bfi_value)
            is_primary = relation == "selected" and lower_value == selected_floor and bfi_value == selected_bfi and mode_name == self.mode_var.get().strip()
            line_width = 2.4 if is_primary else 1.4
            marker_size = 4.0 if is_primary else 3.0
            alpha = LINE_ALPHAS[relation]
            series_rows.sort(key=lambda item: (int(item["upper_value"]), int(item["value"])))
            ladder_x = [int(row["upper_value"]) for row in series_rows]
            ladder_y = [float(row["normalized_output"]) for row in series_rows]
            label = f"{mode_name} L{lower_value} BFI{bfi_value} ladder"
            if relation != "selected":
                label += f" ({RELATION_LABELS[relation]})"
            self.ladder_ax.plot(
                ladder_x,
                ladder_y,
                color=color,
                linestyle=LINE_STYLES[relation],
                linewidth=line_width,
                marker="o",
                markersize=marker_size,
                alpha=alpha,
                label=label,
            )
            if self.show_slope_lines_var.get():
                fit = _linear_fit(ladder_x, ladder_y)
                if fit is not None:
                    slope, intercept = fit
                    slope_y = [slope * float(x_value) + intercept for x_value in ladder_x]
                    self.ladder_ax.plot(
                        ladder_x,
                        slope_y,
                        color=color,
                        linestyle=(0, (2, 2)),
                        linewidth=1.1,
                        alpha=min(0.85, alpha),
                    )

            measured_series = grouped_measured.get((mode_name, lower_value, bfi_value, relation), [])
            if measured_series:
                measured_series.sort(key=lambda item: (int(item["upper_value"]), int(item["value"])))
                measured_x = [int(row["upper_value"]) for row in measured_series]
                measured_y = [float(row["normalized_output"]) for row in measured_series]
                self.ladder_ax.scatter(
                    measured_x,
                    measured_y,
                    facecolors="none",
                    edgecolors=color,
                    s=26 if relation == "selected" else 20,
                    alpha=min(1.0, alpha + 0.1),
                )

            negative_indexes = [
                idx
                for idx in range(1, len(series_rows))
                if float(series_rows[idx]["estimated_output"]) < float(series_rows[idx - 1]["estimated_output"])
            ]
            if negative_indexes:
                self.ladder_ax.scatter(
                    [ladder_x[idx] for idx in negative_indexes],
                    [ladder_y[idx] for idx in negative_indexes],
                    color="#b00020",
                    s=58,
                    marker="x",
                    linewidths=1.7,
                    alpha=0.95,
                )

        marked_ladder_rows = [row for row in ladder_rows if self._row_key(row) in self.manual_outlier_keys]
        if marked_ladder_rows:
            self.ladder_ax.scatter(
                [int(row["upper_value"]) for row in marked_ladder_rows],
                [float(row["normalized_output"]) for row in marked_ladder_rows],
                facecolors="#fff4f5",
                edgecolors="#b00020",
                s=96,
                marker="D",
                linewidths=1.6,
                alpha=0.95,
                label="marked outlier",
                zorder=7,
            )

        selected_ladder_rows = [row for row in ladder_rows if self._row_key(row) in self.selected_row_keys]
        if selected_ladder_rows:
            self.ladder_ax.scatter(
                [int(row["upper_value"]) for row in selected_ladder_rows],
                [float(row["normalized_output"]) for row in selected_ladder_rows],
                facecolors="none",
                edgecolors="#111111",
                s=156,
                marker="o",
                linewidths=1.7,
                alpha=0.95,
                label="selected row",
                zorder=8,
            )

        self.ladder_ax.set_title("Displayed ladder families")
        self.ladder_ax.set_xlabel("Upper value")
        self.ladder_ax.set_ylabel("Normalized output")
        self.ladder_ax.grid(True, alpha=0.25)
        self.ladder_ax.legend(loc="best", fontsize=8, ncol=2)

        for (mode_name, lower_value, bfi_value, relation), series_rows in sorted(grouped_aggregate.items()):
            color = _bfi_color(bfi_value)
            alpha = LINE_ALPHAS[relation]
            series_rows.sort(key=lambda item: (int(item["upper_value"]), int(item["value"])))
            aggregate_x = [int(row["upper_value"]) for row in series_rows]
            measured_avg_y = [float(row["y_measured_avg"]) for row in series_rows]
            estimated_no_bfi_y = [float(row["y_est_nobfi"]) for row in series_rows]
            sizes = [max(18, int(row["samples"]) * 6) for row in series_rows]
            label = f"{mode_name} L{lower_value} BFI{bfi_value} y_est"
            if relation != "selected":
                label += f" ({RELATION_LABELS[relation]})"
            self.aggregate_ax.plot(
                aggregate_x,
                estimated_no_bfi_y,
                color=color,
                linestyle=LINE_STYLES[relation],
                linewidth=2.0 if relation == "selected" and lower_value == selected_floor and bfi_value == selected_bfi and mode_name == self.mode_var.get().strip() else 1.2,
                marker="o",
                markersize=2.8,
                alpha=alpha,
                label=label,
            )
            self.aggregate_ax.scatter(
                aggregate_x,
                measured_avg_y,
                color=color,
                s=sizes,
                alpha=min(0.85, alpha),
            )

        marked_aggregate_rows = [row for row in aggregate_rows if self._row_key(row) in self.manual_outlier_keys]
        if marked_aggregate_rows:
            self.aggregate_ax.scatter(
                [int(row["upper_value"]) for row in marked_aggregate_rows],
                [float(row["y_measured_avg"]) for row in marked_aggregate_rows],
                facecolors="#fff4f5",
                edgecolors="#b00020",
                s=96,
                marker="D",
                linewidths=1.6,
                alpha=0.95,
                label="marked measured",
                zorder=7,
            )
            self.aggregate_ax.scatter(
                [int(row["upper_value"]) for row in marked_aggregate_rows],
                [float(row["y_est_nobfi"]) for row in marked_aggregate_rows],
                facecolors="none",
                edgecolors="#b00020",
                s=96,
                marker="D",
                linewidths=1.6,
                alpha=0.95,
                label="marked estimate",
                zorder=7,
            )

        selected_aggregate_rows = [row for row in aggregate_rows if self._row_key(row) in self.selected_row_keys]
        if selected_aggregate_rows:
            self.aggregate_ax.scatter(
                [int(row["upper_value"]) for row in selected_aggregate_rows],
                [float(row["y_measured_avg"]) for row in selected_aggregate_rows],
                facecolors="none",
                edgecolors="#111111",
                s=150,
                marker="o",
                linewidths=1.7,
                alpha=0.95,
                label="selected measured",
                zorder=8,
            )

        self.aggregate_ax.set_title("Aggregate measurement overlay")
        self.aggregate_ax.set_xlabel("Upper value")
        self.aggregate_ax.set_ylabel("Absolute Y")
        self.aggregate_ax.grid(True, alpha=0.25)
        if grouped_aggregate:
            self.aggregate_ax.legend(loc="best", fontsize=8, ncol=2)

        self.ladder_ax.relim()
        self.ladder_ax.autoscale_view()
        self.aggregate_ax.relim()
        self.aggregate_ax.autoscale_view()
        ladder_xlim = self.ladder_ax.get_xlim()
        ladder_ylim = self.ladder_ax.get_ylim()
        aggregate_xlim = self.aggregate_ax.get_xlim()
        aggregate_ylim = self.aggregate_ax.get_ylim()
        self._full_ladder_limits = (ladder_xlim[0], ladder_xlim[1], ladder_ylim[0], ladder_ylim[1])
        self._full_aggregate_limits = (aggregate_xlim[0], aggregate_xlim[1], aggregate_ylim[0], aggregate_ylim[1])
        self._apply_selection_zoom(ladder_rows, measured_rows, aggregate_rows)

        self.canvas.draw_idle()

    def _write_detail(
        self,
        series_summaries: list[dict[str, object]],
        ladder_rows: list[dict[str, object]],
        measured_rows: list[dict[str, object]],
        aggregate_rows: list[dict[str, object]],
    ) -> None:
        self.detail_text.delete("1.0", tk.END)
        lines = [
            f"Displayed ladder rows: {len(ladder_rows)}",
            f"Displayed measured rows: {len(measured_rows)}",
            f"Displayed aggregate rows: {len(aggregate_rows)}",
            f"Marked outlier rows in view: {sum(1 for row in ladder_rows if self._row_key(row) in self.manual_outlier_keys)}",
            f"Series count: {len(series_summaries)}",
            "",
        ]
        for summary in series_summaries:
            lines.extend(
                [
                    f"{RELATION_LABELS.get(str(summary['relation']), str(summary['relation']))}: mode={summary['mode']} lower={summary['lower_value']} bfi={summary['bfi']} upper={summary['upper_min']}..{summary['upper_max']}",
                    f"  rows={summary['rows']} negative_steps={summary['negative_estimated_steps']} min_q16_step={summary['min_q16_step']} max_q16={summary['max_q16']}",
                    f"  max_estimated_Y={float(summary['max_estimated_output']):.6f} max_norm_gap={float(summary['max_normalized_gap']):.6f} max_aggregate_gap={float(summary['max_aggregate_gap']):.6f}",
                    "",
                ]
            )
        self.detail_text.insert("1.0", "\n".join(lines).rstrip())


def main() -> None:
    root = tk.Tk()
    TemporalLadderFamilyViewerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()