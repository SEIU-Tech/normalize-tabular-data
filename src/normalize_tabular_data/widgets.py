"""Custom widgets: column sidebar with dtype/date-candidate markers, steps bar."""

from __future__ import annotations

from textual.widget import Widget
from textual.widgets import Static

from normalize_tabular_data.ops import ColumnInfo


class ColumnSidebar(Widget):
    """Read-only panel listing columns with dtype, nulls, date-candidate flag.

    Column selection for operations happens inside the operation parameter
    dialogs (SelectionList); the sidebar is informational.
    """

    DEFAULT_CSS = """
    ColumnSidebar {
        width: 42;
        height: 1fr;
        border: round $accent;
        padding: 1 2;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.infos: list[ColumnInfo] = []

    def set_infos(self, infos: list[ColumnInfo]) -> None:
        self.infos = infos
        self.refresh()

    def render(self) -> str:
        lines = [f"Columns ({len(self.infos)})"]
        for info in self.infos:
            flag = "~" if info.date_candidate else " "
            lines.append(
                f"{flag} {info.name[:20]:20} {info.dtype[:9]:9} nulls={info.null_count}"
            )
        return "\n".join(lines)


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

    def set_steps(self, steps: list[str], pending: str | None = None) -> None:
        text = "Steps: " + ("  ->  ".join(steps) if steps else "(none)")
        if pending:
            text += f"   [PENDING: {pending} -- press a to apply]"
        self.update(text)
