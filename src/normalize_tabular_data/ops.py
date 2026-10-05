"""Normalization engine: operation registry and re-computing pipeline.

Pure polars — no Textual imports here, so the whole engine is testable
without a terminal.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import date_parser
import polars as pl

ParamKind = Literal["column_multi", "column", "text", "number", "choice", "bool"]


@dataclass(frozen=True)
class ParamSpec:
    """One parameter of an operation, consumed by the UI to build a dialog."""

    name: str
    kind: ParamKind
    title: str
    default: Any = None
    choices: tuple[str, ...] | None = None
    min_value: int | None = None
    help: str = ""


@dataclass(frozen=True)
class Operation:
    key: str
    title: str
    params: tuple[ParamSpec, ...]
    apply: Callable[[pl.DataFrame, dict[str, Any]], pl.DataFrame]
    # designated chooser hotkey letter; "" lets the chooser pick the first
    # unused letter in the title
    hotkey: str = ""


# --- apply functions -------------------------------------------------------


def _apply_date_normalize(df: pl.DataFrame, p: dict[str, Any]) -> pl.DataFrame:
    col: str = p["column"]
    series = df.get_column(col)
    if series.dtype != pl.String:
        series = series.cast(pl.String)
    # canonical UTC at second resolution: polars has no second-unit
    # Datetime (ns/us/ms only, all of which print sub-second digits in
    # every export), so the normalized column is the truncated
    # `year-month-dayThh:mm:ss` string; fractional parts are dropped and
    # unparseable values become null
    return df.with_columns(
        date_parser.parse_series(series)
        .dt.truncate("1s")
        .dt.to_string("%Y-%m-%dT%H:%M:%S")
        .alias(col)
    )


def _apply_trim_collapse(df: pl.DataFrame, p: dict[str, Any]) -> pl.DataFrame:
    cols: list[str] = p["columns"]
    return df.with_columns(
        pl.col(c).cast(pl.String).str.strip_chars().str.replace_all(r"\s+", " ")
        for c in cols
    )


def _apply_dedup_rows(df: pl.DataFrame, p: dict[str, Any]) -> pl.DataFrame:
    cols: list[str] = p["columns"]
    keep: str = p["keep"]
    return df.unique(
        subset=cols or None,
        keep="first" if keep == "first" else "last",
    )


def _apply_drop_columns(df: pl.DataFrame, p: dict[str, Any]) -> pl.DataFrame:
    return df.drop(p["columns"])


def _apply_combine_columns(df: pl.DataFrame, p: dict[str, Any]) -> pl.DataFrame:
    cols: list[str] = p["columns"]
    sep: str = p["separator"]
    name: str = p["new_name"]
    return df.with_columns(
        pl.concat_str(
            [pl.col(c).cast(pl.String) for c in cols],
            separator=sep,
            ignore_nulls=True,
        ).alias(name)
    )


def _apply_split_column(df: pl.DataFrame, p: dict[str, Any]) -> pl.DataFrame:
    col: str = p["column"]
    delim: str = p["delimiter"]
    rest = df.drop(col)
    # Always strip edge whitespace first; a space delimiter additionally
    # collapses internal whitespace runs so one-or-many spaces/tabs split
    # the same way.
    cleaned = pl.col(col).cast(pl.String).str.strip_chars()
    if delim.strip() == "" or set(delim) <= set(" \t\r\n\f\v"):
        cleaned = cleaned.str.replace_all(r"\s+", " ").replace("", None)
        delim = " "
    split = df.select(cleaned.str.split(delim).alias("__split"))
    # part count comes from the data: the longest actual split for this
    # delimiter; short rows pad with null
    width = split.select(pl.col("__split").list.len().max()).item() or 1
    names = [f"{col}_{i + 1}" for i in range(width)]
    parts = split.select(
        pl.col("__split").list.to_struct(
            fields=names,
            upper_bound=width,
        )
    )
    pieces = parts.get_column("__split").struct.unnest()
    return rest.hstack(pieces) if rest.width else pieces


# --- registry ---------------------------------------------------------------

OPS: tuple[Operation, ...] = (
    Operation(
        key="date_normalize",
        title="Normalize dates",
        hotkey="d",
        params=(
            ParamSpec(
                "column",
                "column",
                "Date column",
                help="Any input format; unparseable -> null",
            ),
        ),
        apply=_apply_date_normalize,
    ),
    Operation(
        key="trim_collapse",
        title="Trim whitespace",
        hotkey="w",
        params=(
            ParamSpec(
                "columns",
                "column_multi",
                "Columns",
                help="Strip edges, collapse internal runs to one space",
            ),
        ),
        apply=_apply_trim_collapse,
    ),
    Operation(
        key="dedup_rows",
        title="Deduplicate rows",
        hotkey="p",
        params=(
            ParamSpec("columns", "column_multi", "Key columns (empty = all)"),
            ParamSpec(
                "keep",
                "choice",
                "Keep",
                default="first",
                choices=("first", "last"),
            ),
        ),
        apply=_apply_dedup_rows,
    ),
    Operation(
        key="combine_columns",
        title="Combine columns",
        hotkey="c",
        params=(
            ParamSpec("columns", "column_multi", "Columns (>= 2)"),
            ParamSpec("separator", "text", "Separator", default=" "),
            ParamSpec("new_name", "text", "New column name"),
        ),
        apply=_apply_combine_columns,
    ),
    Operation(
        key="split_column",
        title="Split column",
        hotkey="s",
        params=(
            ParamSpec("column", "column", "Column to split"),
            ParamSpec(
                "delimiter",
                "text",
                "Delimiter",
                default="",
                help=(
                    "Default split is on whitespace. "
                    "If specified, split on exact characters given."
                ),
            ),
        ),
        apply=_apply_split_column,
    ),
    Operation(
        key="remove_columns",
        title="Remove columns",
        hotkey="r",
        params=(
            ParamSpec(
                "columns",
                "column_multi",
                "Columns to remove",
                help="Remove the selected columns entirely",
            ),
        ),
        apply=_apply_drop_columns,
    ),
)

OP_REGISTRY: dict[str, Operation] = {op.key: op for op in OPS}

# internal op (not in the chooser): renames one column via sample header clicks
RENAME_OP = Operation(
    key="rename_single",
    title="Rename column",
    params=(
        ParamSpec("column", "column", "Column"),
        ParamSpec("new_name", "text", "New name"),
    ),
    apply=lambda df, p: df.rename({p["column"]: p["new_name"]}),
)

# The script player resolves against this: every chooser op plus the internal
# rename op (header-click renames are logged under the key "rename_single",
# so saved scripts contain those lines and have to play back).
PLAY_REGISTRY: dict[str, Operation] = {**OP_REGISTRY, RENAME_OP.key: RENAME_OP}


def apply_script_steps(
    steps: list[tuple[str, dict]],
    pipeline: Pipeline,
    op_log: list[tuple[str, Any]],
    on_failure: Callable[[str], None],
) -> bool:
    """Apply a played script's steps to `pipeline`, all-or-nothing.

    Each step is resolved against PLAY_REGISTRY, applied, and logged to
    `op_log` (the same keys the interactive player records). On the first
    step that is impossible for the currently loaded file the work done so
    far is rolled back — `pipeline.applied` and `op_log` truncated to where
    the script started and the redo stack cleared — and the failure reason
    is passed to `on_failure`. Returns False when a step failed, in which
    case `pipeline` is left exactly as it was before the call."""
    started_applied = len(pipeline.applied)
    started_log = len(op_log)

    def give_up(reason: str) -> None:
        del pipeline.applied[started_applied:]
        pipeline.redo_stack.clear()
        del op_log[started_log:]
        on_failure(reason)

    for index, (key, params) in enumerate(steps, 1):
        op = PLAY_REGISTRY.get(key)
        if op is None:
            give_up(f"Step {index}: {key!r} is not a known operation")
            return False
        try:
            pipeline.apply(op, params)
            # the pipeline refolds lazily; fold now so an op-specific error
            # (e.g. unparseable dates) rolls back this step too
            pipeline.current()
        except Exception as exc:
            give_up(f"Step {index} of {len(steps)} ({op.title}) failed: {exc}")
            return False
        op_log.append((key, dict(params)))
    return True


# --- pipeline ---------------------------------------------------------------


@dataclass
class AppliedOp:
    op: Operation
    params: dict[str, Any]


@dataclass
class Pipeline:
    """Original DataFrame + ordered applied ops; every change re-folds from source."""

    source: pl.DataFrame
    applied: list[AppliedOp] = field(default_factory=list)
    redo_stack: list[AppliedOp] = field(default_factory=list)

    def current(self) -> pl.DataFrame:
        df = self.source
        for step in self.applied:
            df = step.op.apply(df, step.params)
        return df

    def validate(self, op: Operation, params: dict[str, Any]) -> str | None:
        cols = list(self.current().columns)
        for spec in op.params:
            val = params.get(spec.name)
            if spec.kind == "column":
                if not isinstance(val, str) or val not in cols:
                    return f"{op.title}: pick a column"
            elif spec.kind == "column_multi":
                picked = [c for c in (val or []) if c in cols]
                if not picked:
                    return f"{op.title}: pick at least one column"
                need = 2 if op.key == "combine_columns" else 1
                if len(set(picked)) < need:
                    return f"{op.title}: pick at least {need} columns"
            elif spec.kind == "text":
                # split_column's blank delimiter is allowed: it means
                # "split on runs of whitespace"
                if op.key == "combine_columns" and spec.name == "new_name" and not val:
                    return f"{op.title}: new name required"
                if (
                    op.key == "combine_columns"
                    and spec.name == "new_name"
                    and val in cols
                ):
                    return f"{op.title}: {val!r} already exists"
            elif spec.kind == "number":
                if val is None:
                    return f"{op.title}: set a value for {spec.title}"
                if spec.min_value is not None and val < spec.min_value:
                    return f"{op.title}: {spec.title} must be >= {spec.min_value}"
        return None

    def apply(self, op: Operation, params: dict[str, Any]) -> None:
        if (err := self.validate(op, params)) is not None:
            raise ValueError(err)
        self.applied.append(AppliedOp(op, dict(params)))
        self.redo_stack.clear()

    def undo(self) -> bool:
        if not self.applied:
            return False
        self.redo_stack.append(self.applied.pop())
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        self.applied.append(self.redo_stack.pop())
        return True

    def step_summary(self) -> list[str]:
        out = []
        for step in self.applied:
            bits = " ".join(
                f"{k}={v}" for k, v in step.params.items() if v not in (None, ())
            )
            out.append(f"{step.op.key}({bits})" if bits else step.op.key)
        return out


# --- column analysis ---------------------------------------------------------


@dataclass
class ColumnInfo:
    name: str
    dtype: str
    null_count: int
    date_candidate: bool = False


def analyze_column(df: pl.DataFrame, col: str) -> ColumnInfo:
    """dtype, null count, and a date-candidate flag from a 200-row sample."""
    s = df.get_column(col)
    info = ColumnInfo(name=col, dtype=str(s.dtype), null_count=int(s.null_count()))
    if s.dtype == pl.String:
        sample = (
            s.drop_nulls().str.strip_chars().replace("", None).drop_nulls().head(200)
        )
        if sample.len() >= 3:
            parsed = date_parser.parse_series(sample)
            ratio = 1.0 - (parsed.null_count() / sample.len())
            info.date_candidate = ratio >= 0.5
    return info
