"""The Textual application: preview table + column sidebar + step pipeline."""

from __future__ import annotations

import bisect
import datetime as _dt
import random
from pathlib import Path
from platformdirs import user_config_dir
from typing import Any, Iterable

from textual import on
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.color import Color
from textual.command import CommandPalette
from textual.content import Content
from textual.containers import Horizontal
from textual.events import Key
from textual.screen import Screen
from textual.widgets import DataTable, Header, Label, ListItem, ListView

from normalize_tabular_data import io
from normalize_tabular_data.io import SCRIPT_SUFFIX
from normalize_tabular_data.ops import (
    OP_REGISTRY,
    PLAY_REGISTRY,
    RENAME_OP,
    Operation,
    Pipeline,
    analyze_column,
    apply_script_steps as ops_apply_script_steps,
)
from normalize_tabular_data.screens import (
    ModalDialog,
    OpenFileModal,
    OpParamsModal,
    RenameColumnModal,
    SaveModal,
    ScriptNameModal,
    ScriptPickerModal,
    SheetPickerModal,
)
from normalize_tabular_data.widgets import ColumnSidebar, MenuFooter, StepsBar

PREVIEW_ROWS = 250
APP_CONFIG_NAME = "normalize-tabular-data"


class CommandMenu(CommandPalette):
    """The command palette minus its search row: a pure arrow-over/Enter
    command menu (the search field is hidden in CSS).

    The hidden field keeps the palette internals honest — the list is
    populated with every command by the mount-time empty gather — but no
    focus is given to it, so typing does nothing: there is no search.
    Arrow keys move the highlight through the screen's own 'command_list'
    actions; Enter runs the highlighted command (the hidden input's
    Submit gesture replaced by a screen binding)."""

    AUTO_FOCUS = ""
    """Focus nothing: the (hidden) search input must stay un-focused so
    keys reach the screen bindings and typing can't re-run the search."""
    # (None would fall through to App.AUTO_FOCUS "*", which would focus it)

    BINDINGS = [
        *CommandPalette.BINDINGS,
        Binding("enter", "accept_highlighted", "", show=False),
    ]

    def action_accept_highlighted(self) -> None:
        """Run the highlighted command (menu-pick mode)."""
        self._select_or_command()


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

    def _marked_title(self, op_key: str, title: str, hotkey: str = "") -> str:
        """Return "Normalize (d)ates"-style markup: the op's hotkey letter
        highlighted where it sits in the title (keeping its case). A title
        that already parenthesizes its letter ("Normalize date(t)imes")
        highlights the letter between the parens; a plain title matches
        its first occurrence and adds the parens. Ops without a designated
        hotkey claim the first unused letter in the title instead; plain
        title if no letter can be claimed."""
        if hotkey:
            i = title.lower().find(f"({hotkey.lower()})")
            if i >= 0:
                # the letter to claim sits inside existing parentheses:
                # highlight it without adding a second pair
                self._hotkeys[title[i + 1].lower()] = op_key
                return f"{title[: i + 1]}[cyan]{title[i + 1]}[/cyan]{title[i + 2:]}"
            i = title.lower().find(hotkey.lower())
        else:
            i = next(
                (
                    i
                    for i, c in enumerate(title)
                    if c.isalnum() and c.lower() not in self._hotkeys
                ),
                -1,
            )
        if i < 0:
            return title
        self._hotkeys[title[i].lower()] = op_key
        return f"{title[:i]}([cyan]{title[i]}[/cyan]){title[i + 1:]}"

    def compose_body(self) -> ComposeResult:
        items = [
            ListItem(
                Label(self._marked_title(op.key, op.title, op.hotkey)), name=op.key
            )
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


class AppHeader(Header):
    """Header with the application name docked hard right (it previously
    shared the centered title slot with the file/row info)."""

    DEFAULT_CSS = """
    AppHeader > Label.app_name {
        dock: right;
        height: 1;
        margin-right: 2;
        padding: 0 1;
        color: $foreground-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Label("normalize-tabular-data", classes="app_name")


class MainScreen(Screen[None]):
    BINDINGS = [
        ("f", "app.open", "(F)ile"),
        ("o", "app.choose_op", "(O)peration"),
        ("p", "app.play_script", "(P)lay script"),
        ("u", "app.undo", "(U)ndo"),
        ("r", "app.redo", "(R)edo"),
        ("s", "app.save", "(S)ave"),
        ("q", "app.quit_app", "(Q)uit"),
        ("tab", "app.focus_next", ""),
        ("shift+tab", "app.focus_previous", ""),
    ]

    def compose(self) -> ComposeResult:
        yield AppHeader()
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
    /* notification toasts: bottom-left, lifted clear of the panes' bottom
     * border row (default rack is bottom-right, 1 line up, over the border);
     * nudged one row and one column inward from the screen corner */
    ToastRack {
        align: left bottom;
        margin-bottom: 2;
        padding-left: 1;
    }
    ToastHolder {
        align-horizontal: left;
    }
    /* infobox itself: a full outline in the severity color (replacing the
     * default left-hand bar) on a background of its own — the theme accent
     * at low strength over the theme background, warm against the cool
     * slate of the panes ($infobox-bg comes from get_theme_variable_defaults) */
    Toast {
        background: $infobox-bg;
        border: round $accent-muted;
        &:ansi {
            background: $infobox-bg;
        }
    }
    Toast.-information {
        border: round $success;
    }
    Toast.-warning {
        border: round $warning;
    }
    Toast.-error {
        border: round $error;
    }
    /* command menu (palette minus its search row): centered with 5-space
    * side margins and 3 rows of air above the drop-down; arrows move the
    * highlight, Enter runs the highlighted command */
    CommandPalette #--input {
        display: none;
    }
    CommandPalette > Vertical {
        margin-top: 3;
        margin-left: 5;
        margin-right: 5;
    }
    """

    def __init__(
        self,
        initial_file: str | Path | None = None,
        initial_script: str | Path | None = None,
        config_dir: Path | None = None,
    ) -> None:
        super().__init__()
        # where the chosen theme (and any future settings) are stored;
        # None means the per-user platform directory
        self._config_dir = config_dir
        # flips to True at on_mount: only theme changes made after are the
        # user's and only those are persisted
        self._app_ready = False
        # filesystem path to open when the app starts (the optional file
        # named on the command line); loaded like a file chosen in-app
        self.initial_file: Path | None = (
            Path(initial_file) if initial_file is not None else None
        )
        # .ntd script played automatically once that file is loaded (the
        # optional --script named on the command line); requires a file
        self.initial_script: Path | None = (
            Path(initial_script) if initial_script is not None else None
        )
        self.path: Path | None = None
        self.pipeline: Pipeline | None = None
        self.analyzed: dict[str, Any] = {}
        # operations applied since this file was opened: (op key, params);
        # the raw material for a saved ".ntd" script
        self.op_log: list[tuple[str, dict[str, Any]]] = []
        # preview sampling seed, redrawn per load so previews are a random
        # sample but stable across refreshes within one load
        self._preview_seed: int = 0

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        """Palette system commands minus Quit and Screenshot: quitting
        belongs to the (Q) footer key, and screenshots aren't part of this
        tool's workflow."""
        yield from (
            command
            for command in super().get_system_commands(screen)
            if command.title not in ("Quit", "Screenshot")
        )

    def action_change_theme(self) -> None:
        """The Theme command (and its keybinding): same no-search menu,
        over the theme provider instead of the system commands."""
        from textual.theme import ThemeProvider

        self.push_screen(CommandMenu(id="--theme-picker", providers=[ThemeProvider]))

    def action_command_palette(self) -> None:
        """Open the command menu: the palette with no search field and a
        3-row top margin above its drop-down list (CSS below)."""
        self.push_screen(CommandMenu(id="--command-palette"))

    def get_theme_variable_defaults(self) -> dict[str, str]:
        """Define $infobox-bg: the theme accent blended at low strength
        into the theme background — warm against the cool slate of the
        regular panes, so the infobox reads as its own surface."""
        variables = super().get_theme_variable_defaults()
        theme_colors = self.current_theme.to_color_system().generate()
        background = Color.parse(theme_colors["background"])
        accent = theme_colors.get("accent")
        if accent:
            variables["infobox-bg"] = Color.blend(
                background, Color.parse(accent), 0.18
            ).hex
        else:  # no accent in this theme: a plain lift of the background
            variables["infobox-bg"] = background.lighten(2).hex
        return variables

    def format_title(self, title: str, sub_title: str) -> Content:
        # centered header slot: file/row info only — the app name lives
        # docked hard right in the header
        return Content(sub_title)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # menus that need a loaded table are grayed out in the footer (None)
        # while there is no file, and their keys do nothing
        if action in ("play_script", "choose_op", "undo", "redo", "save"):
            return True if self.pipeline is not None else None
        return True

    @property
    def current_columns(self) -> list[str]:
        if self.pipeline is None:
            return []
        return list(self.pipeline.current().columns)

    def on_mount(self) -> None:
        # remember this point so theme changes from here on are the
        # user's own choices and get persisted
        self._apply_saved_theme()
        self.push_screen(MainScreen())
        self._refresh_steps()
        # the command line's file, if any, is opened once the main screen
        # is composed; load_path toasts a readable alert instead of
        # crashing if it is unreadable or has an unsupported format
        if self.initial_file is not None:
            self.call_after_refresh(self.load_path, self.initial_file)
        self._app_ready = True

    # --- theme persistence ---------------------------------------------

    def watch_theme(self, theme_name: str) -> None:
        """Persist every theme the user chooses (menu or command), so the
        next launch opens with it again. Skipped while headless, so the
        pilot tests cannot touch the real configuration; skipped before
        mount, where only the reactive's default applies."""
        if self._app_ready and not self.is_headless:
            try:
                self._theme_config_path().parent.mkdir(parents=True, exist_ok=True)
                self._theme_config_path().write_text(
                    theme_name + "\n", encoding="utf-8"
                )
            except OSError:
                pass  # unwritable config location: run without remembering

    def _apply_saved_theme(self) -> None:
        """Restore the theme chosen in a previous session, if it still exists.

        Skipped in headless runs that use the real configuration location
        (pilot tests): an eyeballing developer's own saved theme should
        not leak into supposedly default-themed tests. A headless run
        given an explicit config_dir is a deliberate fixture and loads it."""
        if self.is_headless and self._config_dir is None:
            return
        try:
            saved = self._theme_config_path().read_text(encoding="utf-8").strip()
        except OSError:
            return
        if not saved:
            return
        try:
            self.theme = saved
        except Exception:
            pass  # a theme name that no longer exists: keep the default

    def _theme_config_path(self) -> Path:
        return (self._config_dir or Path(user_config_dir(APP_CONFIG_NAME))) / "theme"

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
        # opening a file starts a fresh operation log for it
        self.op_log = []
        self._preview_seed = random.getrandbits(64)
        self.analyze_columns()
        self.refresh_preview()
        self.refresh_sidebar()
        self._refresh_steps()
        # pipeline is now set: re-evaluate the footer's enabled keys
        self.screen.refresh_bindings()
        self.notify(f"Loaded {path.name} ({df.height:,} rows x {df.width} columns)")
        # --script named on the command line: play it as soon as its file
        # is on screen (same flow as the P key, with the same rollback)
        if self.initial_script is not None:
            self.play_script_file(self.initial_script)
            self.initial_script = None

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

    def action_play_script(self) -> None:
        if self.pipeline is None:
            self.notify("Open a file first (o)", severity="warning")
            return
        # scripts usually live beside the table they were saved from
        start = self.path.parent if self.path else None

        def handle_result(chosen: Path | None) -> None:
            if chosen:
                self.play_script_file(chosen)

        self.push_screen(ScriptPickerModal(start), handle_result)

    def play_script_file(self, script_path: Path) -> None:
        """Apply a script's steps to the open table, all-or-nothing.

        On the first step that is impossible for the currently loaded file
        (unknown operation, validation failure, apply error) the alert names
        the failing step and everything applied from the script so far is
        rolled back to the state before it started."""
        try:
            steps = io.read_script(script_path)
        except Exception as exc:
            self.notify(f"Could not read {script_path.name}: {exc}", severity="error")
            return
        if not steps:
            self.notify(
                f"{script_path.name} contains no operations", severity="warning"
            )
            return
        started_applied = len(self.pipeline.applied)
        started_log = len(self.op_log)

        def alert(reason: str) -> None:
            # same alert the player has always shown: step description plus
            # how much of the script had to be rolled back
            undid = len(self.pipeline.applied) - started_applied
            detail = (
                f" — rolled back {undid} step{'s' if undid != 1 else ''}"
                if undid
                else ""
            )
            self.refresh_all()
            self.notify(f"{reason}{detail}", severity="error")

        if not ops_apply_script_steps(steps, self.pipeline, self.op_log, alert):
            return
        self.refresh_all()
        count = len(steps)
        self.notify(
            f"Applied {count} step{'s' if count != 1 else ''} from {script_path.name}"
        )

    def _apply_now(self, op: Operation, params: dict[str, Any]) -> None:
        try:
            self.pipeline.apply(op, params)
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        self.op_log.append((op.key, dict(params)))
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
            self._apply_now(RENAME_OP, {"column": old_name, "new_name": new_name})

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

        def handle_result(chosen: tuple[Path, str, bool] | None) -> None:
            if not chosen:
                return
            target, fmt, want_script = chosen
            try:
                io.write_table(self.pipeline.current(), target, fmt)
            except Exception as exc:
                self.notify(f"Save failed: {exc}", severity="error")
                return
            self.notify(f"Saved {target}")
            if want_script:
                self._offer_script_save(target)

        suggested = self.path
        if suggested is not None:
            suggested = suggested.with_stem(suggested.stem + "-normalized")
        self.push_screen(SaveModal(suggested), handle_result)

    def _offer_script_save(self, table_path: Path) -> None:
        suggested = table_path.with_suffix(SCRIPT_SUFFIX).expanduser()

        def handle_result(script_path: Path | None) -> None:
            if script_path is None:
                return
            try:
                io.write_script(
                    script_path,
                    self.op_log,
                    header_fields={
                        "source": str(self.path) if self.path else "",
                        "table": str(table_path),
                        "saved": _dt.datetime.now().isoformat(timespec="seconds"),
                    },
                )
            except Exception as exc:
                self.notify(f"Script save failed: {exc}", severity="error")
                return
            self.notify(f"Saved script {script_path}")

        self.push_screen(ScriptNameModal(suggested), handle_result)

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
