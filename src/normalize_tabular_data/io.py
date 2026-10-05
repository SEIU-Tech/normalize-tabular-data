"""Format dispatch: suffix -> polars read/write. No Textual imports."""

from __future__ import annotations

import json
import re
from pathlib import Path

import polars as pl

READ_SUFFIXES: dict[str, str] = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".txt": "tsv",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".parquet": "parquet",
    ".pq": "parquet",
    ".parq": "parquet",
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


def _read_tabular(path: Path, separator: str = ",") -> pl.DataFrame:
    """CSV/TSV read with a retry fallback.

    Inference looks at up to 10,000 rows; dtype-incompatible values can
    still appear later in a large file and fail parsing. When that happens,
    re-read with zero-length inference so every column stays String instead
    of erroring out."""
    try:
        return pl.read_csv(path, separator=separator, infer_schema_length=10_000)
    except pl.exceptions.PolarsError:
        return pl.read_csv(path, separator=separator, infer_schema_length=0)


def read_table(path: Path, fmt: str, sheet: str | None = None) -> pl.DataFrame:
    """Read one table. For xlsx, `sheet` picks a sheet; default is the first."""
    if fmt == "csv":
        return _read_tabular(path)
    if fmt == "tsv":
        return _read_tabular(path, separator="\t")
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


# --- operation scripts --------------------------------------------------------

SCRIPT_SUFFIX = ".ntd"


def step_line(key: str, params: dict) -> str:
    """One operation description: `<key>(<param>=<json value>, ...)`."""
    return f"{key}({', '.join(f'{p}={json.dumps(v)}' for p, v in params.items())})"


def script_text(steps: list[tuple[str, dict]], header_fields: dict[str, str]) -> str:
    """Human-readable ASCII text, one operation description per line.

    Every operation is `step_line()`'s `<key>(<param>=<json value>, ...)`
    so the lines stay readable while remaining mechanically parseable for a
    future "apply a script" capability. `header_fields` become leading `#`
    comment lines (source file, save time, ...)"""
    lines = ["# normalize-tabular-data script"]
    lines += [f"# {text}" for text in header_fields.values() if text]
    lines += [step_line(key, params) for key, params in steps]
    return "\n".join(lines) + "\n"


def write_script(
    path: Path,
    steps: list[tuple[str, dict]],
    header_fields: dict[str, str],
) -> None:
    """Write the script as plain ASCII (non-ASCII input becomes '?')."""
    path.write_text(
        script_text(steps, header_fields), encoding="ascii", errors="replace"
    )


_SCRIPT_LINE_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\((.*)\)")
_PARAM_NAME_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*")


def parse_script_line(line: str) -> tuple[str, dict]:
    """Parse one `key(param=<json value>, ...)` operation description.

    Values are plain JSON literals, so each parameter is read with a
    JSON decoder (no evaluation). Raises ValueError on anything else."""
    match = _SCRIPT_LINE_RE.fullmatch(line.strip())
    if match is None:
        raise ValueError(f"not an operation line: {line!r}")
    key, args = match.group(1), match.group(2)
    decoder = json.JSONDecoder()
    params: dict = {}
    pos = 0
    n = len(args)
    while pos < n:
        name_match = _PARAM_NAME_RE.match(args, pos)
        if name_match is None:
            raise ValueError(f"missing parameter value in: {line!r}")
        name = name_match.group(1)
        pos = name_match.end()
        try:
            params[name], pos = decoder.raw_decode(args, pos)
        except json.JSONDecodeError:
            raise ValueError(f"bad value for {name!r} in: {line!r}") from None
        while pos < n and args[pos] in " \t":
            pos += 1
        if pos < n and args[pos] == ",":
            pos += 1
            while pos < n and args[pos] in " \t":
                pos += 1
        elif pos < n:
            raise ValueError(f"expected ',' between parameters in: {line!r}")
    return key, params


def read_script(path: Path) -> list[tuple[str, dict]]:
    """Read an operation script: one (key, params) step per non-comment line."""
    steps: list[tuple[str, dict]] = []
    for lineno, raw in enumerate(
        path.read_text(encoding="ascii", errors="replace").splitlines(), 1
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            steps.append(parse_script_line(line))
        except ValueError as exc:
            raise ValueError(f"{path.name} line {lineno}: {exc}") from exc
    return steps
