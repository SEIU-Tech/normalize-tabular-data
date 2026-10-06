"""normalize-tabular-data: TUI for normalizing tabular data with Polars."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

__version__ = "0.1.5"


def _run_script(path: Path, script_path: Path, output: Path | None) -> int:
    """`--run` mode: play SCRIPT against FILE and save the result, no TUI.

    Operation steps print to STDOUT as they are applied (suppressed when
    STDOUT itself is the output, so the only thing there is the table);
    every other message, including any step failure, goes to STDERR and
    exits nonzero. A failed script leaves nothing written."""
    from normalize_tabular_data import io
    from normalize_tabular_data.ops import Pipeline, apply_script_steps

    try:
        steps = io.read_script(script_path)
    except Exception as exc:
        print(f"Could not read {script_path.name}: {exc}", file=sys.stderr)
        return 1
    if not steps:
        print(f"{script_path.name} contains no operations", file=sys.stderr)
        return 1
    try:
        fmt = io.detect_format(path)
        table = io.read_table(path, fmt)
    except Exception as exc:
        print(f"Could not read {path.name}: {exc}", file=sys.stderr)
        return 1

    pipeline = Pipeline(source=table)
    op_log: list[tuple[str, dict]] = []
    to_stdout = output is not None and str(output) == "-"
    if not to_stdout:
        for key, params in steps:
            print(io.step_line(key, params))

    def fail(reason: str) -> None:
        print(reason, file=sys.stderr)

    if not apply_script_steps(steps, pipeline, op_log, fail):
        return 1
    # the transformed frame lives in the pipeline; the `table` variable
    # still holds the raw source
    table = pipeline.current()

    out_path = (
        None if to_stdout else (output or path.with_stem(path.stem + "-normalized"))
    )
    try:
        if out_path is None:
            if fmt not in ("csv", "tsv", "jsonl"):
                print(
                    f"{fmt!r} is not a text format: it cannot be written to "
                    "STDOUT. Name an --output file with a csv/tsv/jsonl "
                    "extension instead.",
                    file=sys.stderr,
                )
                return 1
            if fmt == "csv":
                table.write_csv(sys.stdout)
            elif fmt == "tsv":
                table.write_csv(sys.stdout, separator="\t")
            else:
                table.write_ndjson(sys.stdout)
        else:
            out_fmt = io.detect_format(out_path)
            if out_path.suffix.lower() == ".xls":
                print(
                    ".xls cannot be written; use --output <name>.xlsx", file=sys.stderr
                )
                return 1
            io.write_table(table, out_path, out_fmt)
    except Exception as exc:
        print(f"Save failed: {exc}", file=sys.stderr)
        return 1

    count = len(steps)
    landing = "STDOUT" if out_path is None else str(out_path)
    print(
        f"Applied {count} step{'s' if count != 1 else ''} from "
        f"{script_path.name} -> {landing}",
        file=sys.stderr,
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="normalize-tabular-data",
        description="A terminal UI for normalizing tabular data with polars.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        metavar="FILE",
        help="table file to open at startup (csv, tsv, jsonl, parquet, xlsx)",
    )
    parser.add_argument(
        "-s",
        "--script",
        type=Path,
        metavar="SCRIPT",
        help="an .ntd operation script to play on FILE after opening it",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        metavar="PATH",
        help="where --run saves the transformed table: a path whose format "
        "is its extension, or - for STDOUT (default: the FILE stem plus "
        "-normalized, same directory and extension)",
    )
    parser.add_argument(
        "-x",
        "--run",
        action="store_true",
        help="open FILE, play SCRIPT step by step, save the result and "
        "exit (no UI; requires FILE and --script)",
    )
    argv = sys.argv[1:]
    args = parser.parse_args(argv)

    if args.script is not None and args.file is None:
        parser.error("--script needs a FILE to open")
    if args.output is not None and not args.run:
        parser.error("--output only applies with --run")
    if args.run:
        if args.file is None:
            parser.error("--run needs a FILE to open")
        if args.script is None:
            parser.error("--run needs --script (there would be nothing to play)")
        raise SystemExit(_run_script(args.file, args.script, args.output))

    try:
        from normalize_tabular_data.app import NormalizeApp
    except ImportError as exc:  # helpful message if an optional engine is missing
        print(
            f"normalize-tabular-data is missing a dependency ({exc}).\n"
            "Reinstall with: "
            "uv tool install --force --reinstall normalize-tabular-data",
            file=sys.stderr,
        )
        raise SystemExit(1)
    NormalizeApp(initial_file=args.file, initial_script=args.script).run()
