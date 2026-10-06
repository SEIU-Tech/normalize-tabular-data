# Release notes

## Version 0.2.0

### Non-UTF-8 encoding inference (chardet)

The reader previously assumed UTF-8, so CSV/TSV/JSONL files in
other encodings failed with `invalid utf-8 sequence`. Reading now
retries through an inference pass:

- **Detection** — [chardet](https://pypi.org/project/chardet/) (≥ 7.0.0)
  sniffs the leading bytes of a file (ISO 8859-3, Windows-1256,
  Shift_JIS-2004, UTF-16, ...); already-valid UTF-8 passes through
  untouched, so the common case gains no work.
- **Transcoding** — detected bytes are decoded and re-encoded to UTF-8
  before polars parses them. A UTF-8 BOM is stripped, a UTF-16 BOM is
  consumed by the decoder rather than polluting the first column, and a
  guess that cannot decode the file degrades to an `errors="replace"`
  pass instead of failing the load.
- **Coverage** — applies to CSV, TSV (including `.txt`) and JSONL
  reads; Parquet and Excel are binary containers and keep their own
  encoding contract.
- **Fixtures** — `tests/data/` carries Maltese (`maltese-latin3.csv`),
  Arabic (`arabic-cp1256.csv`) and Japanese (`japanese-shiftjis2004.csv`)
  plus TSV/JSONL/BOM cases in `tests/test_encoding.py` (8 tests) with
  exact per-column round-trip assertions.

Also in this release: the title bar now shows the running version
(`normalize-tabular-data 0.2.0`) next to the file/row information.

## Version 0.1.5

Documentation-only: running instructions revised and the file
requirements clarified (`docs/running-the-tool.md`), a quick start for
command-line usage added to the README, and assorted spelling, wording
and rendered-markdown punctuation fixes. No code changes.

## Version 0.1.4

### Desktop launchers and publishing fixes

- **Launchers** — `launchers/normalize-tabular-data.sh` (Linux/macOS)
  and `.cmd` (Windows) install uv on first run through the official
  astral installers and then start the app via `uvx`.
- **Desktop icons** — `--add-shortcut` installs a custom-iconed icon:
  on macOS a minimal `Normalize Tabular Data.app` bundle whose stub
  hands the launcher to Terminal; on Windows a `.lnk` with
  `IconLocation` pointing at the `.ico` next to the `.cmd`.
- **Icon art** — `launchers/make_icon.py` (Pillow) generates the
  purple table-and-check `.ico`/`.icns` from scratch; restyle and
  regenerate then re-run `--add-shortcut`.
- **Docs** — the README's running section moved to
  `docs/running-the-tool.md` (now with a novice-edition guide for
  downloading the two files per platform, and the two-file minimum for
  a desktop icon); `docs/creating-icons.md` documents the art and the
  per-platform plumbing.
- **Publishing** — `make pypi`/`make testpypi` upload only the wheel
  and sdist matching the `pyproject.toml` version instead of every
  stale artifact in `dist/` (re-uploads answer 400 Bad Request);
  README links are absolute GitHub URLs so PyPI renders them.

## Version 0.1.3

### Date resolution, second date operation, theme persistence

- **What precision is where** — in-memory datetimes and Parquet/Excel
  exports carry millisecond resolution; CSV/TSV/JSONL export serializes
  datetime columns as second-resolution ISO-8601 strings.
- **Normalize date(t)imes** renamed from "Normalize dates"; a new
  **Normalize (d)ates** operation condenses any parseable input to the
  UTC calendar date (date-only ISO-8601).
- **Sidebar dtype marks** — datetimes `dt`, date-only values `day`.
- **Chooser order** — Deduplicate rows moved to the bottom of the
  operation list; the updated screenshot reflects the ordering.
- **Theme persistence** — the theme picked in the app's command-menu
  is saved (`platformdirs` user config) and restored on relaunch.
- **Scripts** — operation scripts are always saved with the `.ntd`
  extension, whatever name is typed in the dialog.

## Version 0.1.2

### First class command line

- **FILE argument** — a table opens at startup as if picked in-app;
  a missing/unreadable file starts the TUI anyway with an alert.
- **`-s`/`--script`** — play an `.ntd` script on the opened file with
  the same stop-and-rollback behavior as the interactive player.
- **`-x`/`--run`** — headless: open `FILE`, play `SCRIPT`, save, and
  exit; each applied step prints to stdout, failures roll back to the
  start state and go to stderr with a nonzero exit code.
- **`-o`/`--output`** — specify the destination file; the format comes
  from its extension. `-o -` (or attached `-o-`) writes the transforms
  to stdout and suppresses the step display, so stdout carries only
  the data. With no `-o`, the result saves beside the input as
  `<FILE stem>-normalized<ext>`.

## Version 0.1.1

### First follow-up: PyPI-runnable metadata

- The screenshot README link is an absolute raw-GitHub URL so the project
  page renders correctly.
- The `Makefile` gained a publishing workflow — `uv build` + `twine
  check` + `twine upload --non-interactive` honoring `$HOME/.pypirc` —
  with TestPyPI and PyPI targets and a documented login section layout.
- The README documents the run modes: persistent install
  (`uv tool install`), ephemeral `uvx` runs, and running from a git
  checkout.

## Version 0.1.0

### Initial release

A Textual TUI for interactive normalization of tabular data,
backed by polars and gnosis-date-parser:

- **Load & preview** — CSV, TSV, JSON lines, Parquet and Excel
  (`.xlsx`/`.xls`, first sheet; extra sheets through a picker); large
  files preview as a 250-row random sample while operations always run
  on full data; columns sidebar lists dtype, null counts and
  date-candidate flags.
- **Operations** — normalize messy dates, trim whitespace, rename a
  column (header click), combine columns, split a column (blank
  delimiter splits on whitespace), remove columns, deduplicate rows
  (all or key columns, first/last), with immediate apply, undo/redo
  and a steps bar across the bottom.
- **Save** — CSV, TSV, JSON lines, Parquet, Excel.
- **Operation scripts** — performed ops are logged per file, save to
  an `.ntd` script (ASCII, one op per line), and play back with a
  preview dialog and the same stop-and-rollback semantics.
- **Publishing** — `uv` packaging (an `uv_build` backend) plus the
  twine-based `make` targets wired to `~/.pypirc`, used to put this
  version on PyPI.
