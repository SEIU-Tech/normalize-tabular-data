import pytest

from normalize_tabular_data.io import (
    detect_format,
    excel_sheets,
    read_table,
    write_table,
)

ROUNDTRIP_CASES = [
    # (fixture name, fmt)
    ("csv_path", "csv"),
    ("jsonl_path", "jsonl"),
    ("parquet_path", "parquet"),
    ("xlsx_path", "xlsx"),
]


@pytest.mark.parametrize("fixture_name,fmt", ROUNDTRIP_CASES)
def test_read_and_roundtrip(request, tmp_path, fixture_name, fmt):
    src = request.getfixturevalue(fixture_name)
    df = read_table(src, detect_format(src))
    assert df.width == 4 and df.height == 4
    assert set(df.columns) == {"id", "Hired Date", "Dept", "Notes"}

    out = tmp_path / f"out{src.suffix if fmt != 'jsonl' else '.jsonl'}"
    write_table(df, out, fmt)
    assert read_table(out, fmt).shape == df.shape


def test_detect_format():
    from pathlib import Path

    assert detect_format(Path("a.csv")) == "csv"
    assert detect_format(Path("a.tsv")) == "tsv"
    assert detect_format(Path("a.ndjson")) == "jsonl"
    assert detect_format(Path("a.pq")) == "parquet"
    assert detect_format(Path("a.xls")) == "xlsx"


def test_detect_format_unknown():
    from pathlib import Path

    with pytest.raises(ValueError, match="Unsupported"):
        detect_format(Path("a.wacz"))


def test_excel_sheets(tmp_path):
    xlsx = tmp_path / "multi.xlsx"
    import polars as pl

    pl.DataFrame({"a": [1]}).write_excel(xlsx, worksheet="First")
    assert excel_sheets(xlsx) == ["First"]


def test_write_unknown_format(tmp_path):
    import polars as pl

    with pytest.raises(ValueError, match="Unknown format"):
        write_table(pl.DataFrame({"a": [1]}), tmp_path / "out.csv", "wacz")
