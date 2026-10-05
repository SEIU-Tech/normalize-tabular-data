# normalize-tabular-data

A terminal UI (Textual) for interactively normalizing tabular data, backed by
[polars](https://pola.rs) for speed and
[gnosis-date-parser](https://pypi.org/project/gnosis-date-parser/) for fuzzy
date parsing at Rust speed.

Load a file, see a preview, build up a pipeline of normalization operations
(normalize messy dates, trim whitespace, rename a column, deduplicate,
combine/split columns, drop columns), then save the
cleaned result.

## Install

```bash
uv tool install normalize-tabular-data
# or run directly from a checkout:
uv run normalize-tabular-data
```

## Usage

Launch with `normalize-tabular-data`. Keys:

| Key | Action                      |
|-----|-----------------------------|
| `f` | (F)ile — open a file        |
| `o` | (O)peration — choose an op  |
| `u` | (U)ndo last applied step    |
| `r` | (R)edo                      |
| `s` | (S)ave the data in a format |
| `q` | (Q)uit                      |

## Operations

- **Normalize dates** — parse a messy date column of *any* input format into
  canonical UTC datetimes; unparseable values become null.
- **Trim whitespace** — strip edges and collapse internal whitespace runs,
  per selected columns.
- Rename a column — click its header in the preview and type the new name.
- **Deduplicate rows** — on all or selected columns, keeping first or last.
- **Combine columns** — concatenate two or more columns with a separator.
- **Split column** — break one column into `{col}_1..{col}_k`; a blank
  delimiter splits on runs of whitespace.
- **Remove columns** — drop selected columns entirely.

## Formats

Reads: CSV, TSV, JSON lines, Parquet, Excel (`.xlsx`/`.xls` — first sheet).
Writes: CSV, TSV, JSON lines, Parquet, Excel (`.xlsx`).

Large files are previewed with a random sample of 250 rows; every operation
still runs on the full data.

![TUI preview](docs/screenshot.png)

## License

BSD 2-Clause. Copyright (c) 2026, Service Employees International Union (SEIU). 

See [LICENSE](LICENSE).
