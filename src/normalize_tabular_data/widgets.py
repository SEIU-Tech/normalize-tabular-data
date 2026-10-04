"""Custom widgets: column sidebar with dtype/date-candidate markers, steps bar,
and a menu-style footer."""

from __future__ import annotations

import re
from collections import defaultdict
from itertools import groupby

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Footer, Static
from textual.widgets._footer import FooterKey, FooterLabel, KeyGroup

from normalize_tabular_data.ops import ColumnInfo


class ColumnSidebar(Widget):
    """Read-only panel listing columns with dtype, nulls, date-candidate flag.

    Column selection for operations happens inside the operation parameter
    dialogs (SelectionList); the sidebar is informational.

    The list lives in a VerticalScroll child because a plain Widget never
    registers as scrollable: a list longer than the panel scrolls instead
    of clipping."""

    DEFAULT_CSS = """
    ColumnSidebar {
        width: 39;
        height: 1fr;
        border: round $accent;
        padding: 1 1;
        layout: vertical;
    }
    ColumnSidebar > VerticalScroll {
        height: 1fr;
        width: 1fr;
    }
    ColumnSidebar > VerticalScroll > Static {
        width: 100%;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.infos: list[ColumnInfo] = []
        self.content_text = Text("Columns (0)")

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static(self.content_text, id="sidebar_text")

    def set_infos(self, infos: list[ColumnInfo]) -> None:
        self.infos = infos
        self.content_text = self._build_text()
        try:
            self.query_one("#sidebar_text", Static).update(self.content_text)
        except NoMatches:
            pass  # not unmounted yet: compose will show content_text

    def _build_text(self) -> Text:
        text = Text(f"Columns ({len(self.infos)})")
        # usable width (self.size already excludes border and padding); keep
        # every line within it so long column names truncate instead of wrapping
        avail = max(self.size.width, 9)
        # when the list outgrows the panel the scrollbar claims two columns
        # of the inner area: build the lines for the reduced width so they
        # never wrap inside the scrolling region
        if len(self.infos) + 1 > self.size.height:
            avail = max(avail - 2, 9)
        # the null counts left-align as one column, as wide as the widest count
        null_w = max(
            (len(f"nulls={info.null_count}") for info in self.infos),
            default=6,
        )
        name_w = max(avail - 6 - null_w - 1, 1)
        for info in self.infos:
            text.append("\n")
            text.append("~" if info.date_candidate else " ")
            text.append(" ")
            # the dtype mark in the highlight color
            text.append(_dtype_mark(info.dtype), style="cyan")
            name = info.name[:name_w]
            # pad the (possibly cut) name so every "nulls=..." starts together
            text.append(" " + name.ljust(name_w))
            text.append(f" nulls={info.null_count}")
        return text


def _dtype_mark(dtype: str) -> str:
    """Compact 3-wide dtype mark for the sidebar: dt (datetime/date),
    str (string), int (integer), dec (float/decimal), t/f (boolean);
    everything else oth. Each mark is padded to 3 columns so column
    names left-align."""
    for prefix, mark in (
        ("Datetime", "dt "), ("Date", "dt "), ("Time", "dt "),
        ("String", "str"), ("Categorical", "str"), ("Enum", "str"),
        ("Int", "int"), ("UInt", "int"),
        ("Float", "dec"), ("Decimal", "dec"),
        ("Boolean", "t/f"),
    ):
        if dtype.startswith(prefix):
            return mark
    return "oth"


class StepsBar(Static):
    """One-line summary of the applied operation pipeline."""

    DEFAULT_CSS = """
    StepsBar {
        height: 1;
        dock: bottom;
        background: $panel;
        color: $text;
        padding: 0 1;
    }
    """

    def set_steps(self, steps: list[str]) -> None:
        text = "Steps: " + ("  ->  ".join(steps) if steps else "(none)")
        self.update(text)


_HOTKEY_RE = re.compile(r"^\((.)\)(.*)$")


class MenuKey(FooterKey):
    """Footer key shown menu-style: no key chip; the hotkey letter inside
    parentheses (e.g. "(F)ile") is drawn in the key-highlight style.
    Descriptions that don't follow the pattern fall back to the default
    chip rendering."""

    DEFAULT_CSS = """
    MenuKey {
        margin-right: 2;
    }
    """

    def render(self) -> Text:
        if _HOTKEY_RE.match(self.description) is None:
            return super().render()
        key_style = self.get_component_rich_style("footer-key--key")
        description_style = self.get_component_rich_style("footer-key--description")
        text = Text(self.description, description_style)
        # the hotkey letter is the single character between the parentheses
        text.stylize(key_style, 1, 2)
        text.stylize_before(self.rich_style)
        return text


class MenuFooter(Footer):
    """Footer whose keys render as menus. Mirrors Footer.compose but
    yields MenuKey widgets."""

    def compose(self) -> "ComposeResult":
        if not self._bindings_ready:
            return
        active_bindings = self.screen.active_bindings
        bindings = [
            (binding, enabled, tooltip)
            for (_, binding, enabled, tooltip) in active_bindings.values()
            if binding.show
        ]
        action_to_bindings: defaultdict[str, list] = defaultdict(list)
        for binding, enabled, tooltip in bindings:
            action_to_bindings[binding.action].append((binding, enabled, tooltip))

        self.styles.grid_size_columns = len(action_to_bindings)

        for group, multi_bindings_iterable in groupby(
            action_to_bindings.values(),
            lambda multi_bindings_: multi_bindings_[0][0].group,
        ):
            multi_bindings = list(multi_bindings_iterable)
            if group is not None and len(multi_bindings) > 1:
                with KeyGroup(classes="-compact" if group.compact else ""):
                    for multi_bindings in multi_bindings:
                        binding, enabled, tooltip = multi_bindings[0]
                        yield MenuKey(
                            binding.key,
                            self.app.get_key_display(binding),
                            "",
                            binding.action,
                            disabled=not enabled,
                            tooltip=tooltip or binding.description,
                            classes="-grouped",
                        ).data_bind(compact=Footer.compact)
                yield FooterLabel(group.description)
            else:
                for multi_bindings in multi_bindings:
                    binding, enabled, tooltip = multi_bindings[0]
                    yield MenuKey(
                        binding.key,
                        self.app.get_key_display(binding),
                        binding.description,
                        binding.action,
                        disabled=not enabled,
                        tooltip=tooltip,
                    ).data_bind(compact=Footer.compact)
        if self.show_command_palette and self.app.ENABLE_COMMAND_PALETTE:
            try:
                _node, binding, enabled, tooltip = active_bindings[
                    self.app.COMMAND_PALETTE_BINDING
                ]
            except KeyError:
                pass
            else:
                yield MenuKey(
                    binding.key,
                    self.app.get_key_display(binding),
                    binding.description,
                    binding.action,
                    classes="-command-palette",
                    disabled=not enabled,
                    tooltip=binding.tooltip or binding.description,
                )
