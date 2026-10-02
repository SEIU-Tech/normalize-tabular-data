"""Normalization engine: operation registry and re-computing pipeline.

Pure polars — no Textual imports here, so the whole engine is testable
without a terminal.
"""

from __future__ import annotations

import re
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


# --- apply functions -------------------------------------------------------

def _apply_date_normalize(df: pl.DataFrame, p: dict[str, Any]) -> pl.DataFrame:
    col: str = p["column"]
    series = df.get_column(col)
    if series.dtype != pl.String:
        series = series.cast(pl.String)
    # Datetime("ns"), unparseable -> null
    return df.with_columns(date_parser.parse_series(series).alias(col))


def _apply_trim_collapse(df: pl.DataFrame, p: dict[str, Any]) -> pl.DataFrame:
    cols: list[str] = p["columns"]
    return df.with_columns(
        pl.col(c)
        .cast(pl.String)
        .str.strip_chars()
        .str.replace_all(r"\s+", " ")
        for c in cols
    )


def _apply_empty_to_null(df: pl.DataFrame, p: dict[str, Any]) -> pl.DataFrame:
    cols: list[str] = p["columns"]
    return df.with_columns(pl.col(c).cast(pl.String).replace("", None) for c in cols)


def _snake(name: str) -> str:
    s = re.sub(r"[\s\-]+", "_", str(name).strip())
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"[^0-9a-zA-Z_]", "_", s)
    s = re.sub(r"_{2,}", "_", s)
    return s.strip("_").lower() or "col"


def _apply_rename_columns(df: pl.DataFrame, p: dict[str, Any]) -> pl.DataFrame:
    style: str = p["style"]
    mapping = {
        c: {
            "snake_case": _snake(c),
            "lowercase": re.sub(r"[^0-9a-z]+", "_", c.lower()).strip("_") or "col",
            "slugify": re.sub(r"[^0-9a-z]+", "-", c.lower()).strip("-") or "col",
        }[style]
        for c in df.columns
    }
    return df.rename(mapping)


def _apply_dedup_rows(df: pl.DataFrame, p: dict[str, Any]) -> pl.DataFrame:
    cols: list[str] = p["columns"]
    keep: str = p["keep"]
    return df.unique(
        subset=cols or None,
        keep="first" if keep == "first" else "last",
    )


def _apply_fill_nulls(df: pl.DataFrame, p: dict[str, Any]) -> pl.DataFrame:
    cols: list[str] = p["columns"]
    value: str = p["value"]
    return df.with_columns(pl.col(c).cast(pl.String).fill_null(value) for c in cols)


def _apply_drop_null_rows(df: pl.DataFrame, p: dict[str, Any]) -> pl.DataFrame:
    n: int = p["n"]
    null_sum = pl.sum_horizontal(
        pl.col(c).is_null().cast(pl.UInt32) for c in df.columns
    )
    return df.filter(null_sum < n)


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
    max_parts: int = p["max_parts"]
    rest = df.drop(col)
    if max_parts:
        # splitn keeps the remainder glued into the last of the n fields
        name_map = {f"field_{i}": f"{col}_{i + 1}" for i in range(max_parts)}
        pieces = df.select(
            pl.col(col)
            .cast(pl.String)
            .str.splitn(delim, max_parts)
            .alias("__split")
        ).select(pl.col("__split").struct.unnest()).rename(name_map)
        return rest.hstack(pieces) if rest.width else pieces
    split = df.select(pl.col(col).cast(pl.String).str.split(delim).alias("__split"))
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
        params=(ParamSpec("column", "column", "Date column", help="Any input format; unparseable -> null"),),
        apply=_apply_date_normalize,
    ),
    Operation(
        key="trim_collapse",
        title="Trim & collapse whitespace",
        params=(ParamSpec("columns", "column_multi", "Columns", help="Trim edges, collapse internal runs"),),
        apply=_apply_trim_collapse,
    ),
    Operation(
        key="empty_to_null",
        title="Empty strings -> null",
        params=(ParamSpec("columns", "column_multi", "Columns"),),
        apply=_apply_empty_to_null,
    ),
    Operation(
        key="rename_columns",
        title="Rename columns",
        params=(ParamSpec("style", "choice", "Style", default="snake_case", choices=("snake_case", "lowercase", "slugify")),),
        apply=_apply_rename_columns,
    ),
    Operation(
        key="dedup_rows",
        title="Deduplicate rows",
        params=(
            ParamSpec("columns", "column_multi", "Key columns (empty = all)"),
            ParamSpec("keep", "choice", "Keep", default="first", choices=("first", "last")),
        ),
        apply=_apply_dedup_rows,
    ),
    Operation(
        key="fill_nulls",
        title="Fill nulls",
        params=(
            ParamSpec("columns", "column_multi", "Columns"),
            ParamSpec("value", "text", "Fill value", default=""),
        ),
        apply=_apply_fill_nulls,
    ),
    Operation(
        key="drop_null_rows",
        title="Drop rows with >= N nulls",
        params=(ParamSpec("n", "number", "Nulls per row threshold", default=1, min_value=1),),
        apply=_apply_drop_null_rows,
    ),
    Operation(
        key="combine_columns",
        title="Combine columns",
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
        params=(
            ParamSpec("column", "column", "Column to split"),
            ParamSpec("delimiter", "text", "Delimiter"),
            ParamSpec("max_parts", "number", "Max parts (0 = unlimited)", default=0, min_value=0),
        ),
        apply=_apply_split_column,
    ),
)

OP_REGISTRY: dict[str, Operation] = {op.key: op for op in OPS}


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
                if op.key == "split_column" and spec.name == "delimiter" and not val:
                    return f"{op.title}: delimiter required"
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
            bits = " ".join(f"{k}={v}" for k, v in step.params.items() if v not in (None, ()))
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
            s.drop_nulls()
            .str.strip_chars()
            .replace("", None)
            .drop_nulls()
            .head(200)
        )
        if sample.len() >= 3:
            parsed = date_parser.parse_series(sample)
            ratio = 1.0 - (parsed.null_count() / sample.len())
            info.date_candidate = ratio >= 0.5
    return info
