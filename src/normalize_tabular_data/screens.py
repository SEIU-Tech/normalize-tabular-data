"""Modal screens: file open/save, operation parameters, date sample check."""

from __future__ import annotations

from pathlib import Path

from rich.syntax import Syntax as RichSyntax
from textual import on
from textual.color import Color
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    SelectionList,
    Static,
)

from normalize_tabular_data.io import SCRIPT_SUFFIX, WRITE_SUFFIXES
from normalize_tabular_data.ops import Operation


class ModalDialog(ModalScreen):
    """Shared chrome: centered bordered box; Escape cancels."""

    DEFAULT_CSS = """
    ModalDialog { align: center middle; }
    ModalDialog > Vertical {
        background: $surface;
        border: round $accent;
        padding: 1 2;
        width: auto;
        height: auto;
        max-width: 96;
        max-height: 90%;
    }
    .buttons { align-horizontal: right; margin-top: 1; height: auto; }
    Button { margin-left: 1; width: auto; min-width: 6 !important; }
    Label.help { color: $text-muted; }
    #path_input, #save_input { width: 64; }
    ListView { height: 12; width: 64; }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    dialog_title: str = "Dialog"

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self.dialog_title)
            yield from self.compose_body()
            with Horizontal(classes="buttons"):
                yield Button("OK", id="btn_ok", variant="primary")
                yield Button("Cancel", id="btn_cancel")

    def compose_body(self) -> ComposeResult:
        return ()
        yield NotImplemented

    def post_result(self, value) -> None:
        self.dismiss(value)

    @on(Button.Pressed, "#btn_ok")
    def _ok_pressed(self) -> None:
        self.action_ok()

    @on(Button.Pressed, "#btn_cancel")
    def _cancel_pressed(self) -> None:
        self.action_cancel()

    def action_ok(self) -> None:
        self.post_result(None)

    def action_cancel(self) -> None:
        self.post_result(None)


class OpenFileModal(ModalDialog):
    """Type a path or browse the current directory; choose a file."""

    dialog_title = "Open file"

    def __init__(self, start: Path | None = None) -> None:
        super().__init__()
        self.dir = (start or Path.cwd()).resolve()

    def compose_body(self) -> ComposeResult:
        yield Input(placeholder="type a path, then press Enter", id="path_input")
        yield ListView(id="opendir")

    def on_mount(self) -> None:
        self._refresh_dir(self.dir)
        self.query_one("#path_input", Input).focus()

    def _refresh_dir(self, directory: Path) -> None:
        self.dir = directory
        input_widget = self.query_one("#path_input", Input)
        input_widget.placeholder = f"path under {directory}"
        listing = self.query_one("#opendir", ListView)
        listing.clear()
        listing.extend(self._entries(directory))

    def _entries(self, directory: Path) -> list[ListItem]:
        children = sorted(
            (p for p in directory.iterdir() if not p.name.startswith(".")),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
        items = [ListItem(Label("../"), name=str(directory.parent.resolve()))]
        items += [
            ListItem(Label(p.name + ("/" if p.is_dir() else "")), name=str(p))
            for p in children
        ]
        return items

    @on(ListView.Selected)
    def on_list_selected(self, event: ListView.Selected) -> None:
        if not event.item.name:
            return
        chosen = Path(event.item.name)
        if chosen.is_dir():
            self._refresh_dir(chosen)
            return
        self.post_result(chosen)

    @on(Input.Submitted, "#path_input")
    def on_input_submitted(self) -> None:
        raw = self.query_one("#path_input", Input).value.strip()
        if raw:
            self.post_result(Path(raw).expanduser())


class ScriptPickerModal(OpenFileModal):
    """Browse for an operation script file to play against the open table.

    As the browse list highlight moves (or a path is typed), a syntax-
    highlighted preview of the `.ntd` file shows underneath."""

    dialog_title = "Play script"

    DEFAULT_CSS = """
    ScriptPickerModal > Vertical > Static#script_preview {
        height: 10;
        width: 64;
        margin-top: 1;
        background: $boost;
    }
    """

    PREVIEW_LINES = 40

    preview_text: str = ""
    preview_background: str = "#272727"

    def compose_body(self) -> ComposeResult:
        yield Input(placeholder="type a path, then press Enter", id="path_input")
        yield ListView(id="opendir")
        self.preview = Static(
            RichSyntax("", lexer="python", background_color=self._preview_background()),
            id="script_preview",
        )
        yield self.preview

    def on_mount(self) -> None:
        self._refresh_dir(self.dir)
        # browse-first dialog: arrows move the highlight (and the preview),
        # Enter on a file plays it, OK confirms the current selection —
        # the list takes focus after the screen's default focus pass
        self.call_after_refresh(self.query_one("#opendir", ListView).focus)

    def _current_choice(self) -> Path | None:
        """The script the dialog would play right now: a typed path that
        exists, else the currently highlighted list entry (file paths
        only — directories are browsed, not played)."""
        raw = self.query_one("#path_input", Input).value.strip()
        if raw and Path(raw).expanduser().is_file():
            return Path(raw).expanduser()
        child = self.query_one("#opendir", ListView).highlighted_child
        if child is not None and child.name:
            chosen = Path(child.name)
            if chosen.is_file():
                return chosen
        return None

    def action_ok(self) -> None:
        chosen = self._current_choice()
        if chosen is None:
            self.app.notify(
                "Select a script file first (arrow keys highlight, Enter plays)",
                severity="warning",
            )
            return
        self.post_result(chosen)

    def _update_preview(self, target: Path) -> None:
        self.preview_text = self._script_text(target)
        self.preview.update(
            RichSyntax(
                self.preview_text,
                lexer="python",
                background_color=self.preview_background,
            )
        )

    def _preview_background(self) -> str:
        """Hex color the preview strip paints behind the highlighted text.

        The strip's CSS is `$boost` over the dialog's `$surface`; rich's
        'default' background would leave those cells to the terminal's own
        background color, which is not the box color. Composite the same
        colors the compositor uses, and paint the text cells with the
        result — foreground (monokai) colors are untouched."""
        variables = self.app.get_css_variables()
        boost = Color.parse(variables["boost"])
        surface = Color.parse(variables["surface"])
        alpha = boost.a  # Color.a is already a 0..1 float
        channels = tuple(
            round(channel * alpha + base * (1 - alpha))
            for channel, base in zip(boost.rgb, surface.rgb)
        )
        hex = f"#{channels[0]:02X}{channels[1]:02X}{channels[2]:02X}"
        self.preview_background = hex
        return hex

    def _script_text(self, target: Path) -> str:
        """The script file's text (capped), or '' when target is not one."""
        try:
            if target.is_file() and target.suffix.lower() == SCRIPT_SUFFIX:
                lines = target.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                head, note = lines[: self.PREVIEW_LINES], ""
                if len(lines) > self.PREVIEW_LINES:
                    note = f"\n# … {len(lines) - self.PREVIEW_LINES} more lines"
                return "\n".join(head) + note
        except OSError:
            pass
        return ""

    @on(ListView.Highlighted, "#opendir")
    def _preview_highlighted(self, event: ListView.Highlighted) -> None:
        """As highlight moves through the listing, preview highlighted file."""
        if event.item and event.item.name:
            target = Path(event.item.name)
            if target.is_file():
                self._update_preview(target)

    @on(Input.Changed, "#path_input")
    def _preview_typed(self, event: Input.Changed) -> None:
        raw = event.value.strip()
        if raw:
            self._update_preview(Path(raw).expanduser())


class RenameColumnModal(ModalDialog):
    """Enter a new name for one column; dismisses with the name or None.

    Docks in the sidebar and hugs its content: title + input + buttons."""

    dialog_title = "Rename column"

    DEFAULT_CSS = """
    RenameColumnModal {
        align: left middle;
    }
    RenameColumnModal > Vertical {
        width: 38;
    }
    RenameColumnModal Input {
        width: 32;
    }
    RenameColumnModal > Vertical > Horizontal.buttons {
        height: auto;
    }
    """

    def __init__(self, current: str) -> None:
        super().__init__()
        self.current = current

    def compose_body(self) -> ComposeResult:
        self.name_input = Input(value=self.current, id="rename_input")
        yield self.name_input

    def on_mount(self) -> None:
        self.name_input.focus()

    def action_ok(self) -> None:
        raw = self.name_input.value.strip()
        if not raw:
            self.app.notify("Column name cannot be empty", severity="error")
            return
        self.post_result(raw)

    @on(Input.Submitted, "#rename_input")
    def _rename_input_submit(self) -> None:
        self.action_ok()


class SheetPickerModal(ModalDialog):
    """Pick which worksheet to load from an xlsx."""

    dialog_title = "Choose worksheet"

    def __init__(self, sheet_names: list[str]) -> None:
        super().__init__()
        self.sheet_names = sheet_names

    def compose_body(self) -> ComposeResult:
        # Select.BLANK is just `False` in this Textual version; never pass it
        # as `value` — omit `value` instead (default is the true blank sentinel)
        self.sheet_choice = Select(
            [(name, name) for name in self.sheet_names],
            allow_blank=False,
            id="sheet_pick",
        )
        yield self.sheet_choice

    def action_ok(self) -> None:
        self.post_result(self.sheet_choice.value)


class OpParamsModal(ModalDialog):
    """Collect parameters for an Operation; dismisses with the params dict.

    Docks over the sidebar (like the op chooser), so the preview table in the
    main pane keeps showing data rows while parameters are entered."""

    dialog_title = "Parameters"

    DEFAULT_CSS = """
    OpParamsModal {
        align: left middle;
    }
    OpParamsModal > Vertical {
        width: 38;
    }
    OpParamsModal SelectionList,
    OpParamsModal Select,
    OpParamsModal Input {
        width: 32;
    }
    /* a long column list must not push the OK/Cancel buttons and later
    * fields out of the dialog: cap it and let it scroll internally */
    OpParamsModal SelectionList {
        max-height: 10;
    }
    OpParamsModal Label.help {
        width: 32;
        text-wrap: wrap;
    }
    """

    def __init__(self, op: Operation) -> None:
        super().__init__()
        self.op = op
        self.dialog_title = op.title

    def compose_body(self) -> ComposeResult:
        self.widgets: dict[str, object] = {}
        candidates = self._date_candidates() if self.op.key == "date_normalize" else []
        for spec in self.op.params:
            if spec.kind == "column_multi":
                sel = SelectionList(
                    *[(name, name, False) for name in self._available_columns()],
                    id="param_columns",
                )
                self.widgets[spec.name] = sel
                yield sel
            elif spec.kind == "column":
                col_names = self._available_columns()
                preselect = (
                    candidates[0] if candidates and candidates[0] in col_names else None
                )
                sel = Select(
                    [(name, name) for name in col_names],
                    allow_blank=True,
                    id="param_column",
                )
                self.preselect_column = preselect
                self.widgets[spec.name] = sel
                yield sel
            elif spec.kind == "choice":
                sel = Select(
                    [(c, c) for c in spec.choices or ()],
                    allow_blank=False,
                    value=spec.default,
                    id="param_choice",
                )
                self.widgets[spec.name] = sel
                yield sel
            elif spec.kind == "number":
                inp = Input(
                    str(spec.default or ""),
                    type="integer",
                    id=f"param_number_{spec.name}",
                    classes="param_input",
                )
                self.widgets[spec.name] = inp
                yield inp
            elif spec.kind == "bool":
                chk = Checkbox(spec.title, spec.default is True)
                self.widgets[spec.name] = chk
                yield chk
            else:
                default = spec.default if isinstance(spec.default, str) else ""
                # a whitespace-only default (the separator's single space)
                # looks empty anyway; start blank so the placeholder acts
                # as visible shadow text
                value = "" if not default.strip() else default
                inp = Input(
                    value=value,
                    placeholder=spec.title,
                    id=f"param_text_{spec.name}",
                    classes="param_input",
                )
                self.widgets[spec.name] = inp
                yield inp
            if spec.help:
                yield Label(spec.help, classes="help")

    def on_mount(self) -> None:
        # Select options are usable only after mount; apply any preselect here
        preselect = getattr(self, "preselect_column", None)
        if preselect is not None:
            self.widgets["column"].value = preselect

    def _available_columns(self) -> list[str]:
        return list(getattr(self.app, "current_columns", []) or [])

    def _date_candidates(self) -> list[str]:
        analyzed = getattr(self.app, "analyzed", {}) or {}
        return [name for name, info in analyzed.items() if info.date_candidate]

    def collect_params(self) -> dict:
        params: dict = {}
        for spec in self.op.params:
            widget = self.widgets[spec.name]
            if spec.kind == "column_multi":
                params[spec.name] = list(widget.selected)
            elif spec.kind == "column":
                params[spec.name] = (
                    None if widget.value is Select.NULL else widget.value
                )
            elif spec.kind == "number":
                raw = widget.value.strip()
                params[spec.name] = int(raw) if raw else None
            elif spec.kind == "bool":
                params[spec.name] = widget.value is True
            else:
                params[spec.name] = widget.value
        return params

    def action_ok(self) -> None:
        pipeline = getattr(self.app, "pipeline", None)
        if pipeline is None:
            self.app.notify("No file loaded", severity="error")
            return
        params = self.collect_params()
        problem = pipeline.validate(self.op, params)
        if problem:
            self.app.notify(problem, severity="error")
            return
        self.post_result(params)

    @on(Input.Submitted, ".param_input")
    def _input_submit_ok(self) -> None:
        self.action_ok()


class SaveModal(ModalDialog):
    """Path + format for writing the normalized table."""

    dialog_title = "Save as"

    def __init__(self, suggested: Path | None) -> None:
        super().__init__()
        self.suggested = suggested

    def compose_body(self) -> ComposeResult:
        path_stub = self.suggested or Path("normalized.csv")
        self.path_input = Input(
            placeholder=str(path_stub),
            value=str(path_stub),
            id="save_input",
        )
        self.overwrite = Checkbox(
            "Allow overwrite if file exists", False, id="allow_overwrite"
        )
        self.save_script = Checkbox(
            "Save sequence of operations?", False, id="save_script"
        )
        extensions = " ".join(sorted(WRITE_SUFFIXES))
        yield self.path_input
        yield Static(f"Extensions: {extensions}", classes="help")
        yield self.overwrite
        yield self.save_script

    def action_ok(self) -> None:
        raw = self.path_input.value.strip()
        if not raw:
            self.app.notify("Type a file name or path", severity="error")
            return
        target = Path(raw).expanduser()
        fmt = WRITE_SUFFIXES.get(target.suffix.lower())
        if fmt is None:
            self.app.notify(
                "Unsupported extension: use one of "
                + ", ".join(sorted(WRITE_SUFFIXES)),
                severity="error",
            )
            return
        if target.exists() and not self.overwrite.value:
            self.app.notify(
                "File exists: tick the overwrite box or pick another path",
                severity="warning",
            )
            return
        self.post_result((target, fmt, self.save_script.value is True))

    @on(Input.Submitted, "#save_input")
    def _save_input_submit(self) -> None:
        self.action_ok()


class ScriptNameModal(ModalDialog):
    """Name the '.ntd' script file when saving a sequence of operations.

    The default carries the .ntd extension; typing a different one saves
    under that extension instead."""

    dialog_title = "Save script"

    def __init__(self, suggested: Path) -> None:
        super().__init__()
        self.suggested = suggested

    def compose_body(self) -> ComposeResult:
        self.path_input = Input(
            placeholder=str(self.suggested),
            value=str(self.suggested),
            id="script_input",
        )
        yield self.path_input
        yield Static(
            f"Default extension: {SCRIPT_SUFFIX} — type another to override",
            classes="help",
        )

    def action_ok(self) -> None:
        raw = self.path_input.value.strip()
        if not raw:
            self.app.notify("Type a script file name or path", severity="error")
            return
        target = Path(raw).expanduser()
        if target.exists():
            self.app.notify("Script file exists: pick another name", severity="warning")
            return
        self.post_result(target)

    @on(Input.Submitted, "#script_input")
    def _script_input_submit(self) -> None:
        self.action_ok()
