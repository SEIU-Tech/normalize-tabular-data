"""Format dispatch: suffix -> polars read/write. No Textual imports."""

from __future__ import annotations

from pathlib import Path

import polars as pl

READ_SUFFIXES: dict[str, str] = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".txt": "csv",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".parquet": "parquet",
    ".pq": "parquet",
    ".xlsx": "xlsx",
    ".xls": "xlsx",
}

WRITE_SUFFIXES: dict[str, str] = {k: v for k, v in READ_SUFFIXES.items() if k != ".xls"}

FORMAT_SUFFIX: dict[str, str] = {
    "csv": ".csv",
    "tsv": ".tsv",
    "jsonl": ".jsonl",
    "parquet": ".parquet",
    "xlsx": ".xlsx",
}


def detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    fmt = READ_SUFFIXES.get(suffix)
    if fmt is None:
        known = ", ".join(sorted(READ_SUFFIXES))
        raise ValueError(f"Unsupported file type {suffix!r} (known: {known})")
    return fmt


def read_table(path: Path, fmt: str, sheet: str | None = None) -> pl.DataFrame:
    """Read one table. For xlsx, `sheet` picks a sheet; default is the first."""
    if fmt == "csv":
        return pl.read_csv(path)
    if fmt == "tsv":
        return pl.read_csv(path, separator="\t")
    if fmt == "jsonl":
        return pl.read_ndjson(path)
    if fmt == "parquet":
        return pl.read_parquet(path)
    if fmt == "xlsx":
        if sheet is None:
            sheets = excel_sheets(path)
            sheet = sheets[0] if sheets else "Sheet1"
        return pl.read_excel(path, sheet_name=sheet)
    raise ValueError(f"Unknown format {fmt!r}")


def excel_sheets(path: Path) -> list[str]:
    """Sheet names of a workbook, in order (fastexcel/calamine)."""
    import fastexcel

    return list(fastexcel.read_excel(path).sheet_names)


def write_table(
    df: pl.DataFrame,
    path: Path,
    fmt: str,
    sheet_name: str = "data",
) -> None:
    if fmt == "csv":
        df.write_csv(path)
    elif fmt == "tsv":
        df.write_csv(path, separator="\t")
    elif fmt == "jsonl":
        df.write_ndjson(path)
    elif fmt == "parquet":
        df.write_parquet(path)
    elif fmt == "xlsx":
        df.write_excel(path, worksheet=sheet_name, autofit=True, freeze_panes="B2")
    else:
        raise ValueError(f"Unknown format {fmt!r}")
