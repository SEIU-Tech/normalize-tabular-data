"""The Textual application: preview table + column sidebar + step pipeline."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

import polars as pl
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label, ListItem, ListView

from normalize_tabular_data import io
from normalize_tabular_data.ops import OP_REGISTRY, Operation, Pipeline, analyze_column
from normalize_tabular_data.screens import (
    DateCheckModal,
    ModalDialog,
    OpenFileModal,
    OpParamsModal,
    SaveModal,
    SheetPickerModal,
)
from normalize_tabular_data.widgets import ColumnSidebar, StepsBar

PREVIEW_ROWS = 500


class OpChooserModal(ModalDialog):
    """Pick an operation from the registry; dismisses with the op's key."""

    dialog_title = "Choose operation"

    def compose_body(self) -> ComposeResult:
        items = [ListItem(Label(op.title), name=op.key) for op in OP_REGISTRY.values()]
        yield ListView(*items, id="oplist")

    def __init__(self) -> None:
        super().__init__()

    def on_mount(self) -> None:
        self.query_one("#oplist", ListView).focus()

    @on(ListView.Selected)
    def on_op_selected(self, event: ListView.Selected) -> None:
        if event.item.name:
            self.post_result(event.item.name)


class ColumnPickModal(ModalDialog):
    """Pick one string column (used for the date-check sample)."""

    dialog_title = "Date check: pick a column"

    def __init__(self, columns: list[str]) -> None:
        super().__init__()
        self.columns = columns

    def compose_body(self) -> ComposeResult:
        items = [ListItem(Label(name), name=name) for name in self.columns]
        yield ListView(*items, id="collist")

    def on_mount(self) -> None:
        self.query_one("#collist", ListView).focus()

    @on(ListView.Selected)
    def on_col_selected(self, event: ListView.Selected) -> None:
        if event.item.name:
            self.post_result(event.item.name)


class MainScreen(Screen[None]):
    BINDINGS = [
        ("o", "app.open", "Open"),
        ("n", "app.choose_op", "Op"),
        ("a", "app.apply", "Apply"),
        ("p", "app.edit_params", "Params"),
        ("u", "app.undo", "Undo"),
        ("r", "app.redo", "Redo"),
        ("c", "app.check_dates", "Check"),
        ("s", "app.save", "Save"),
        ("q", "app.quit_app", "Quit"),
        ("tab", "app.focus_next", ""),
        ("shift+tab", "app.focus_previous", ""),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ColumnSidebar(id="sidebar")
            yield DataTable(show_cursor=True, id="preview", cursor_type="row")
        yield StepsBar(id="steps")
        yield Footer()


class NormalizeApp(App[None]):
    TITLE = "normalize-tabular-data"

    CSS = """
    #preview { border: round $accent; }
    DataTable { width: 1fr; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.path: Path | None = None
        self.pipeline: Pipeline | None = None
        self.pending: tuple[Operation, dict[str, Any]] | None = None
        self.analyzed: dict[str, Any] = {}

    @property
    def current_columns(self) -> list[str]:
        if self.pipeline is None:
            return []
        return list(self.pipeline.current().columns)

    def on_mount(self) -> None:
        self.push_screen(MainScreen())
        self._refresh_steps()

    # --- data plumbing ---------------------------------------------------

    def load_path(self, path: Path, sheet: str | None = None) -> None:
        fmt = io.detect_format(path)
        if fmt == "xlsx" and sheet is None:
            sheets = io.excel_sheets(path)
            def sheet_callback(chosen: str | None) -> None:
                if not chosen:
                    return
                self._load_complete(path, fmt, chosen)
            if len(sheets) > 1:
                self.push_screen(SheetPickerModal(sheets), sheet_callback)
                return
        self._load_complete(path, fmt, sheet)

    def _load_complete(self, path: Path, fmt: str, sheet: str | None) -> None:
        try:
            df = io.read_table(path, fmt, sheet)
        except Exception as exc:  # pragma: no cover - user-facing message
            self.notify(f"Could not read {path.name}: {exc}", severity="error")
            return
        self.path = path
        self.pipeline = Pipeline(source=df)
        self.pending = None
        self.title = f"normalize-tabular-data — {path.name}"
        self.analyze_columns()
        self.refresh_preview()
        self.refresh_sidebar()
        self._refresh_steps()
        self.notify(f"Loaded {path.name} ({df.height:,} rows x {df.width} columns)")

    def analyze_columns(self) -> None:
        if self.pipeline is None:
            return
        df = self.pipeline.current()
        self.analyzed = {name: analyze_column(df, name) for name in df.columns}

    # --- rendering --------------------------------------------------------

    def refresh_preview(self) -> None:
        try:
            table = self.screen.query_one("#preview", DataTable)
        except Exception:
            return
        if self.pipeline is None:
            return
        df = self.pipeline.current().head(PREVIEW_ROWS)
        table.clear(columns=True)
        table.add_columns(*df.columns)
        for row in df.iter_rows(named=False):
            table.add_row(*[_cell(v) for v in row])
        self.screen.sub_title = (
            f"{self.path.name if self.path else ''} — "
            f"showing first {df.height:,} of {self.pipeline.current().height:,} rows"
        )

    def refresh_sidebar(self) -> None:
        try:
            sidebar = self.screen.query_one("#sidebar", ColumnSidebar)
        except Exception:
            return
        sidebar.set_infos(list(self.analyzed.values()))

    def _refresh_steps(self) -> None:
        try:
            steps = self.screen.query_one("#steps", StepsBar)
        except Exception:
            return
        steps.set_steps(
            self.pipeline.step_summary() if self.pipeline else [],
            self.pending[0].title if self.pending else None,
        )

    def refresh_all(self) -> None:
        self.analyze_columns()
        self.refresh_preview()
        self.refresh_sidebar()
        self._refresh_steps()

    # --- actions ------------------------------------------------------------

    def action_open(self) -> None:
        def handle_result(chosen: Path | None) -> None:
            if chosen:
                self.load_path(chosen)

        self.push_screen(OpenFileModal(), handle_result)

    def action_choose_op(self) -> None:
        if self.pipeline is None:
            self.notify("Open a file first (o)", severity="warning")
            return

        def handle_result(key: str | None) -> None:
            if key is None:
                return
            op = OP_REGISTRY[key]

            def params_result(params: dict[str, Any] | None) -> None:
                if params:
                    self.pending = (op, params)
                    self._refresh_steps()

            self.push_screen(OpParamsModal(op), params_result)

        self.push_screen(OpChooserModal(), handle_result)

    def action_edit_params(self) -> None:
        if self.pending is None:
            self.notify("No pending operation", severity="warning")
            return
        op, _old = self.pending

        def params_result(params: dict[str, Any] | None) -> None:
            if params:
                self.pending = (op, params)
                self._refresh_steps()

        self.push_screen(OpParamsModal(op), params_result)

    def action_apply(self) -> None:
        if self.pipeline is None:
            self.notify("Open a file first (o)", severity="warning")
            return
        if self.pending is None:
            self.notify("Choose an operation (n)", severity="warning")
            return
        op, params = self.pending
        try:
            self.pipeline.apply(op, params)
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        self.pending = None
        self.refresh_all()
        self.notify(f"Applied: {op.title}", severity="information")

    def action_undo(self) -> None:
        if self.pipeline is None or not self.pipeline.undo():
            self.notify("Nothing to undo", severity="warning")
            return
        self.refresh_all()

    def action_redo(self) -> None:
        if self.pipeline is None or not self.pipeline.redo():
            self.notify("Nothing to redo", severity="warning")
            return
        self.refresh_all()

    def action_check_dates(self) -> None:
        if self.pipeline is None:
            self.notify("Open a file first (o)", severity="warning")
            return
        df = self.pipeline.current()
        string_cols = [c for c in df.columns if df.get_column(c).dtype == pl.String]

        def column_result(column: str | None) -> None:
            if column is None:
                return
            values = [
                v for v in df.get_column(column).cast(pl.String).drop_nulls().to_list()
                if isinstance(v, str) and v.strip()
            ][:20]
            self.analyzed |= {column: analyze_column(df, column)}
            self.push_screen(DateCheckModal(column, values))

        self.push_screen(ColumnPickModal(string_cols), column_result)

    def action_save(self) -> None:
        if self.pipeline is None:
            self.notify("Open a file first (o)", severity="warning")
            return

        def handle_result(chosen: tuple[Path, str] | None) -> None:
            if not chosen:
                return
            target, fmt = chosen
            try:
                io.write_table(self.pipeline.current(), target, fmt)
            except Exception as exc:
                self.notify(f"Save failed: {exc}", severity="error")
                return
            self.notify(f"Saved {target}")

        suggested = self.path
        if suggested is not None:
            suggested = suggested.with_stem(suggested.stem + "-normalized")
        self.push_screen(SaveModal(suggested), handle_result)

    def action_quit_app(self) -> None:
        self.exit()


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, _dt.datetime | _dt.date):
        return value.isoformat()
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)
