"""Headless --run mode: subprocess tests of the -s/-x/-o command line."""

import polars as pl
from io import StringIO
from pathlib import Path
from subprocess import run

import pytest

ROOT = Path(__file__).parents[1]

# a script that stands in for any real normalization pass
TIDY_LINES = (
    "# normalize-tabular-data script\n"
    'trim_collapse(columns=["Dept", "Notes"])\n'
    'date_normalize(column="Hired Date")\n'
)


@pytest.fixture
def sample_csv(tmp_path) -> Path:
    """Same shape as conftest's csv_path, locally owned so output paths
    collide with nothing."""
    path = tmp_path / "sample.csv"
    pl.DataFrame(
        {
            "id": ["1", "2"],
            "Hired Date": ["2022-03-22", "Mar 1, 2019"],
            "Dept": ["  Engineering ", "Ops"],
            "Notes": ["  Alice  Doe  ", ""],
        }
    ).write_csv(path)
    return path


@pytest.fixture
def tidy_script(tmp_path) -> Path:
    path = tmp_path / "tidy.ntd"
    path.write_text(TIDY_LINES)
    return path


def cli(*argv: str) -> "run":
    return run(
        ["uv", "run", "normalize-tabular-data", *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_run_writes_default_normalized_csv(sample_csv, tidy_script):
    result = cli(str(sample_csv), "-s", str(tidy_script), "-x")
    assert result.returncode == 0, result.stderr
    # steps echo to stdout in script-line form, one per operation
    assert 'trim_collapse(columns=["Dept", "Notes"])' in result.stdout
    assert 'date_normalize(column="Hired Date")' in result.stdout
    # default destination: <stem>-normalized<ext> beside the original
    out = sample_csv.with_stem(sample_csv.stem + "-normalized")
    assert out.exists()
    cleaned = pl.read_csv(out)
    assert cleaned["Dept"].to_list() == ["Engineering", "Ops"]
    # parsed dates were saved at second resolution: no sub-second digits
    assert cleaned["Hired Date"].to_list()[0] == "2022-03-22T00:00:00"


def test_run_output_option(sample_csv, tidy_script, tmp_path):
    out_dir = tmp_path / "done"
    out_dir.mkdir()
    out = out_dir / "members.parquet"
    result = cli(str(sample_csv), "-s", str(tidy_script), "-x", "-o", str(out))
    assert result.returncode == 0, result.stderr
    assert out.exists()
    assert pl.read_parquet(out).height == 2
    # no default file was made: -o chooses the destination
    assert not sample_csv.with_stem("sample-normalized").exists()


# both spellings of the STDOUT marker parse natively
STDOUT_SPELLINGS = (["-o", "-"], ["-o-"])


@pytest.mark.parametrize("tokens", STDOUT_SPELLINGS, ids=" ".join)
def test_run_output_stdout_suppresses_steps(sample_csv, tidy_script, tokens):
    result = cli(str(sample_csv), "-s", str(tidy_script), "-x", *tokens)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    # stdout is nothing but the transformed table itself
    assert "trim_collapse(" not in result.stdout
    assert lines[0] == "id,Hired Date,Dept,Notes"
    cleaned = pl.read_csv(StringIO(result.stdout))
    assert cleaned["Dept"].to_list() == ["Engineering", "Ops"]
    # the confirmation is on stderr, not stdout
    assert "Applied 2 steps" in result.stderr
    # nothing was written to disk either
    assert not sample_csv.with_stem("sample-normalized").exists()


def test_run_failure_names_step_on_stderr(sample_csv):
    script = Path(sample_csv.parent) / "broken.ntd"
    script.write_text(
        'trim_collapse(columns=["Dept"])\n'
        'trim_collapse(columns=["No Such Column"])\n'
    )
    result = cli(str(sample_csv), "-s", str(script), "-x")
    assert result.returncode != 0
    # the same wording the interactive player alerts: the failing step,
    # numbered among the script's steps
    assert "Step 2 of 2 (Trim whitespace) failed:" in result.stderr, result.stderr
    # all-or-nothing: nothing was written, default or otherwise
    assert not (sample_csv.parent / "sample-normalized.csv").exists()


def test_run_unknown_operation(sample_csv):
    script = Path(sample_csv.parent) / "mystery.ntd"
    script.write_text("bogus_op(mystery=1)\n")
    result = cli(str(sample_csv), "-s", str(script), "-x")
    assert result.returncode != 0
    assert "Step 1: 'bogus_op' is not a known operation" in result.stderr


def test_unreadable_script(sample_csv):
    result = cli(str(sample_csv), "-s", str(sample_csv.parent / "missing.ntd"), "-x")
    assert result.returncode != 0
    assert "Could not read" in result.stderr


@pytest.mark.parametrize(
    "argv,fragment",
    [
        (["-s", "s.ntd"], "--script needs a FILE"),
        (["-x"], "--run needs a FILE"),
        (["f.csv", "-x"], "--run needs --script"),
        (["f.csv", "-s", "s.ntd", "-o", "out.csv"], "--output only applies with --run"),
    ],
)
def test_argument_errors_go_to_stderr(argv, fragment):
    """Usage problems quit before the TUI with a nonzero exit."""
    fixed = ["test" if a == "f.csv" else a for a in argv]
    result = cli(*fixed)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "usage:" in result.stderr
    assert fragment in result.stderr


def test_run_stdout_rejects_binary_source_formats(conftest_xlsx, tidy_script):
    """xlsx cannot stream through a pipe: an --output file is required."""
    result = cli(str(conftest_xlsx), "-s", str(tidy_script), "-x", "-o", "-")
    assert result.returncode != 0
    assert "cannot be written to STDOUT" in result.stderr


@pytest.fixture
def conftest_xlsx(tmp_path) -> Path:
    path = tmp_path / "sample.xlsx"
    pl.DataFrame(
        {
            "id": ["1", "2"],
            "Hired Date": ["2022-03-22", "Mar 1, 2019"],
            "Dept": ["  Engineering ", "Ops"],
            "Notes": ["  Alice  Doe  ", ""],
        }
    ).write_excel(path)
    return path
