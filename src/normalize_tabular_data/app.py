"""The Textual application: preview table + column sidebar + step pipeline."""

from __future__ import annotations

import bisect
import datetime as _dt
import random
from pathlib import Path
from typing import Any

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.events import Key
from textual.screen import Screen
from textual.widgets import DataTable, Header, Label, ListItem, ListView

from normalize_tabular_data import io
from normalize_tabular_data.ops import (
    OP_REGISTRY,
    RENAME_OP,
    Operation,
    Pipeline,
    analyze_column,
)
from normalize_tabular_data.screens import (
    ModalDialog,
    OpenFileModal,
    OpParamsModal,
    RenameColumnModal,
    SaveModal,
    SheetPickerModal,
)
from normalize_tabular_data.widgets import ColumnSidebar, MenuFooter, StepsBar

PREVIEW_ROWS = 250


class PreviewTable(DataTable):
    """Preview whose Left/Right keys scroll a whole column per press.

    With the row cursor, DataTable's default Left/Right fall through to
    one-character scrolling; this snaps to column start boundaries instead."""

    def _column_offsets(self) -> list[float]:
        widths = [col.get_render_width(self) for col in self.columns.values()]
        offsets = [0.0]
        for w in widths:
            offsets.append(offsets[-1] + w)
        return offsets

    def _scroll_to_column(self, direction: int) -> None:
        offsets = self._column_offsets()
        if len(offsets) < 2:
            return
        eps = 0.5
        idx = bisect.bisect_right(offsets, self.scroll_x + eps) - 1
        if direction > 0:
            # land on the next boundary even if the current column is only
            # partly scrolled past
            target = min(idx + 1, len(offsets) - 2)
        else:
            # first finish revealing the current column, then step back one
            target = idx - 1 if self.scroll_x <= offsets[idx] + eps else idx
            target = max(target, 0)
        self.scroll_to(x=offsets[target], animate=False)

    def action_cursor_left(self) -> None:
        self._scroll_to_column(-1)

    def action_cursor_right(self) -> None:
        self._scroll_to_column(1)


class OpChooserModal(ModalDialog):
    """Pick an operation from the registry; dismisses with the op's key.

    Docked over the sidebar, narrower than it, so the preview table keeps
    showing data rows while the chooser is open."""

    dialog_title = "Choose operation"

    DEFAULT_CSS = """
    OpChooserModal {
        align: left middle;
    }
    OpChooserModal > Vertical {
        width: 38;
    }
    OpChooserModal ListView {
        width: 32;
        height: auto;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        # hotkey letter (lowercase) -> op key; letters are unique across ops
        self._hotkeys: dict[str, str] = {}

    def _marked_title(self, op_key: str, title: str) -> str:
        """Return the "(N)ormalize dates" label markup for a title, claiming
        its first unused letter as the hotkey; plain title if none is free."""
        for i, char in enumerate(title):
            if char.isalnum() and char.lower() not in self._hotkeys:
                self._hotkeys[char.lower()] = op_key
                return f"{title[:i]}([cyan]{char.upper()}[/cyan]){title[i + 1:]}"
        return title

    def compose_body(self) -> ComposeResult:
        items = [
            ListItem(Label(self._marked_title(op.key, op.title)), name=op.key)
            for op in OP_REGISTRY.values()
        ]
        yield ListView(*items, id="oplist")

    def on_mount(self) -> None:
        self.query_one("#oplist", ListView).focus()

    @on(Key)
    def _hotkey_pressed(self, event: Key) -> None:
        # pressing the marked letter selects that operation directly
        if event.character and (op_key := self._hotkeys.get(event.character.lower())):
            event.stop()
            event.prevent_default()
            self.post_result(op_key)

    @on(ListView.Selected)
    def on_op_selected(self, event: ListView.Selected) -> None:
        if event.item.name:
            self.post_result(event.item.name)


class MainScreen(Screen[None]):
    BINDINGS = [
        ("f", "app.open", "(F)ile"),
        ("o", "app.choose_op", "(O)peration"),
        ("u", "app.undo", "(U)ndo"),
        ("r", "app.redo", "(R)edo"),
        ("s", "app.save", "(S)ave"),
        ("q", "app.quit_app", "(Q)uit"),
        ("tab", "app.focus_next", ""),
        ("shift+tab", "app.focus_previous", ""),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ColumnSidebar(id="sidebar")
            yield PreviewTable(show_cursor=True, id="preview", cursor_type="row")
        yield StepsBar(id="steps")
        yield MenuFooter()


class NormalizeApp(App[None]):
    TITLE = "normalize-tabular-data"

    CSS = """
    #preview { border: round $accent; scrollbar-size: 0 0; }
    DataTable { width: 1fr; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.path: Path | None = None
        self.pipeline: Pipeline | None = None
        self.analyzed: dict[str, Any] = {}
        # preview sampling seed, redrawn per load so previews are a random
        # sample but stable across refreshes within one load
        self._preview_seed: int = 0

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
        # detect/sheet probing also runs in a modal callback; keep any failure
        # in here as a TUI toast instead of a terminal traceback
        try:
            fmt = io.detect_format(path)
            if fmt == "xlsx" and sheet is None:
                sheets = io.excel_sheets(path)
            else:
                self._load_complete(path, fmt, sheet)
                return
        except Exception as exc:  # user-facing: unsupported type, bad xlsx, ...
            self.notify(f"Could not read {path.name}: {exc}", severity="error")
            return

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
        except Exception as exc:  # user-facing message, keep the TUI alive
            self.notify(f"Could not read {path.name}: {exc}", severity="error")
            return
        self.path = path
        self.pipeline = Pipeline(source=df)
        self._preview_seed = random.getrandbits(64)
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
        full = self.pipeline.current()
        # large tables preview a random sample (same rows across refreshes
        # within one load); small tables show everything in file order
        df = (
            full.sample(PREVIEW_ROWS, seed=self._preview_seed)
            if full.height > PREVIEW_ROWS
            else full
        )
        table.clear(columns=True)
        table.add_columns(*df.columns)
        for row in df.iter_rows(named=False):
            table.add_row(*[_cell(v) for v in row])
        self.screen.sub_title = (
            f"{self.path.name if self.path else ''} — "
            f"{df.height:,} of {self.pipeline.current().height:,} rows"
            " — click column to rename"
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
        steps.set_steps(self.pipeline.step_summary() if self.pipeline else [])

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
                    self._apply_now(op, params)

            self.push_screen(OpParamsModal(op), params_result)

        self.push_screen(OpChooserModal(), handle_result)

    def _apply_now(self, op: Operation, params: dict[str, Any]) -> None:
        try:
            self.pipeline.apply(op, params)
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        self.refresh_all()
        self.notify(f"Applied: {op.title}", severity="information")

    @on(DataTable.HeaderSelected)
    def _on_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Clicking a column header opens the rename dialog for that column."""
        if self.pipeline is None:
            return
        old_name = str(event.label) or str(event.column_key)
        if old_name not in self.pipeline.current().columns:
            return

        def handle_result(new_name: str | None) -> None:
            if not new_name or new_name == old_name:
                return
            if new_name in self.pipeline.current().columns:
                self.notify(f"{new_name!r} already exists", severity="error")
                return
            self._apply_now(
                RENAME_OP, {"column": old_name, "new_name": new_name}
            )

        self.push_screen(RenameColumnModal(old_name), handle_result)

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
        return "<NULL>"
    if isinstance(value, _dt.datetime | _dt.date):
        return value.isoformat()
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)
