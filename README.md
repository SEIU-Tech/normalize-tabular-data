# normalize-tabular-data

A terminal UI (Textual) for interactively normalizing tabular data, backed by
[polars](https://pola.rs) for speed and
[gnosis-date-parser](https://pypi.org/project/gnosis-date-parser/) for fuzzy
date parsing at Rust speed.

Load a file, see a preview, build up a pipeline of normalization operations
(normalize messy dates, trim/collapse whitespace, empty→null, rename columns,
deduplicate, fill or drop nulls, combine/split columns), then save the
cleaned result.

## Install

```bash
uv tool install normalize-tabular-data
# or run directly from a checkout:
uv run normalize-tabular-data
```

## Usage

Launch with `normalize-tabular-data`. Keys:

| Key | Action |
|-----|--------|
| `o` | Open a file |
| `n` | Choose an operation |
| `a` | Apply the selected operation |
| `p` | Edit pending operation parameters |
| `u` | Undo last applied step |
| `r` | Redo |
| `c` | Date-parse sample check (raw ↔ parsed preview) |
| `s` | Save the normalized table |
| `q` | Quit |

## Operations

- **Normalize dates** — parse a messy date column of *any* input format into
  canonical UTC datetimes; unparseable values become null.
- **Trim & collapse whitespace**, **empty strings → null** — per selected columns.
- **Rename columns** — snake_case / lowercase / slugify.
- **Deduplicate rows** — on all or selected columns, keeping first or last.
- **Fill nulls**, **drop rows with ≥ N nulls**.
- **Combine columns** — concatenate two or more columns with a separator.
- **Split column** — break one column on a delimiter into `{col}_1..{col}_k`.

## Formats

Reads: CSV, TSV, JSON lines, Parquet, Excel (`.xlsx`/`.xls` — first sheet).
Writes: CSV, TSV, JSON lines, Parquet, Excel (`.xlsx`).

Large files are previewed with a sampled table; every operation still runs on
the full data.

![TUI preview](docs/screenshot.png)

## License

BSD 2-Clause. Copyright (c) 2026, Members of Service Employees International
Union (SEIU). See [LICENSE](LICENSE).
