# normalize-tabular-data (NTD)

A terminal UI (Textual) for interactively normalizing tabular data, backed by
[polars](https://pola.rs) for speed and
[gnosis-date-parser](https://pypi.org/project/gnosis-date-parser/) for fuzzy
date parsing at Rust speed. NTD also supports purely command-line operations 
for use in scripting.

**Quick start**: `uvx normalize-tabular-data`. No installation required if
you have `uv`.

Load a file, see a preview, build up a pipeline of normalization operations
(normalize messy dates, trim whitespace, rename a column, deduplicate,
combine/split columns, drop columns), then save the cleaned result.

## Formats

Reads: CSV, TSV, JSON lines, Parquet, Excel (`.xlsx`/`.xls` — first sheet).
Writes: CSV, TSV, JSON lines, Parquet, Excel (`.xlsx`).

Large files are previewed with a random sample of 250 rows; every operation
still runs on the full data.

## Running the Text User Interface

![TUI preview](https://raw.githubusercontent.com/SEIU-Tech/normalize-tabular-data/main/docs/screenshot.png)

Installation and launch options — persistent install, ephemeral `uvx`
runs, running from a git checkout, the single-file launchers for
Linux/macOS/Windows, and installing them as desktop icons — are
described in
[docs/running-the-tool.md](https://github.com/SEIU-Tech/normalize-tabular-data/blob/main/docs/running-the-tool.md).

## Capabilities in the TUI

Launch with `uvx normalize-tabular-data` (or a launcher). Keys:


| Key | Action                       |
|-----|------------------------------|
| `f` | (F)ile — open a file         |
| `o` | (O)peration — choose an op   |
| `p` | (P)lay script — apply `.ntd` |
| `u` | (U)ndo last applied step     |
| `r` | (R)edo                       |
| `s` | (S)ave the data in a format  |
| `q` | (Q)uit                       |

## Operations

- **Normalize date(t)imes** — parse a messy date column of *any* input
  format into canonical UTC datetimes at millisecond resolution;
  unparseable values become null. CSV/TSV/JSONLines export serializes
  datetime columns as second-resolution `year-month-dayThh:mm:ss`
  strings; Parquet and Excel keep the real datetime values.
- **Normalize (d)ates** — the same match-anything parsing, condensed to
  the UTC calendar date: the column becomes date-only ISO-8601
  (`year-month-day`); unparseable values become null.
- **Trim whitespace** — strip edges and collapse internal whitespace runs,
  per selected columns.
- Rename a column — click its header in the preview and type the new name.
- **Combine columns** — concatenate two or more columns with a separator.
- **Split column** — break one column into `{col}_1..{col}_k`; a blank
  delimiter splits on runs of whitespace.
- **Remove columns** — drop selected columns entirely.
- **Deduplicate rows** — on all or selected columns, keeping first or last.

## Command line usage

An optional `FILE` argument names a table to open at startup, as if you
had picked it from the in-app dialog.

```bash
uvx normalize-tabular-data data/members.tsv
```

If the file is missing or its format cannot be read, the TUI still
starts — it shows an alert toast and you can open something else.

### Open with a script

With `--script/-s`, an `.ntd` script is played on `FILE` as soon as it
loads (same flow as the `p` key, same stop-and-rollback on a step that
does not fit the file):

```bash
uvx normalize-tabular-data data/members.csv -s data/members.ntd
```

### Headless run (`-x`, `--run`)

`--run/-x` skips the TUI: it opens `FILE`, plays `SCRIPT` step by step,
saves the result and exits. Each operation prints to stdout as it is
applied; anything else — including a failing step, named and rolled
back exactly as the interactive player would — goes to stderr with a
nonzero exit code.

```bash
# saves data/members-normalized.csv next to the original
uvx normalize-tabular-data members.csv -s members.ntd -x

# choose the destination (format taken from its extension):
uvx normalize-tabular-data members.csv -s members.ntd -x -o out/members.parquet

# write the CSV to a pipe instead:
uvx normalize-tabular-data members.csv -s members.ntd -x -o - | gzip > clean.csv.gz
```

With `-o -` (attached `-o-` works too), the transformed table is written
to stdout itself and the step lines are suppressed, so stdout carries
only the data. After a successful run the confirmation line goes to
stderr.

## Operation scripts (`.ntd`)

Every open file keeps an internal log of the operations performed on it. When
saving, the dialog offers a **Save sequence of operations?** checkbox
(unticked by default); with it ticked, a second dialog asks where to write
the script — suggested `<table>.ntd`; scripts always use the `.ntd`
extension, so the name you type is saved with that suffix whatever it
ends in.

The script is plain ASCII text, one operation per line, e.g.:

```
# normalize-tabular-data script
# source: worksite.csv
# table: /data/worksite-normalized.csv
# saved: 2026-10-05T12:30:11
date_normalize(column="Signed Up")
trim_collapse(columns=["Full Name", "Worksite", "Job Class"])
split_column(column="Full Name", delimiter="")
rename_single(column="Full Name_1", new_name="First Name")
rename_single(column="Full Name_2", new_name="Last Name")
```

## Playing a script back

Press `p` (available while a file is loaded) to pick a script file: the
dialog previews the highlighted `.ntd` file (syntax-highlighted, first 40
lines) before you confirm. Its operations are applied, in order, to the table 
you have open. If any step cannot be performed against the currently loaded 
file — a column it renames, trims or splits is missing, the operation is 
unknown — playing stops with an alert naming the failing step, and every step
the script had already applied is rolled back, so the table is left exactly as 
it was.

## Publishing

PyPI credentials live in `$HOME/.pypirc` (sections `[pypi]` and
`[testpypi]`); uploads go through `twine`, which honors that file —
`uv publish` does not read `.pypirc`, so it is not used here.

```bash
make dist       # build sdist+wheel into dist/ and run `twine check`
make testpypi   # upload to the TestPyPI sandbox (login section [testpypi])
make pypi       # upload to PyPI (login section [pypi])
twine upload    # equivalent of `make pypi`, minus a fresh build
```

The targets fail fast if the package metadata does not pass `twine check`,
and `twine` runs with `--non-interactive` so a missing or wrong
credential aborts the upload instead of prompting mid-run.

## License

BSD 2-Clause. Copyright (c) 2026, Service Employees International Union (SEIU). 

See [LICENSE](https://github.com/SEIU-Tech/normalize-tabular-data/blob/main/LICENSE).
