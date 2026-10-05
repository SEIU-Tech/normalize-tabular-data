import polars as pl
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


def test_txt_reads_as_tsv(tmp_path, sample_df):
    """A .txt file is parsed as tab-separated: a real TSV loads cleanly."""
    out = tmp_path / "data.txt"
    sample_df.write_csv(out, separator="\t")
    df = read_table(out, detect_format(out))
    assert df.columns == ["id", "Hired Date", "Dept", "Notes"]
    assert df.height == 4


def test_csv_infers_types_from_10k_rows(tmp_path):
    """Inference samples 10_000 rows: a column that turns stringy after the
    first 100 rows (the old default sample) still loads instead of raising."""
    out = tmp_path / "late_type_change.csv"
    out.write_text(
        "id\n"
        + "\n".join(str(i) for i in range(150))  # numeric head
        + "\nlate-string\n"  # past the old sample
        + "\n".join(str(i) for i in range(151, 300))
        + "\n"
    )
    df = read_table(out, "csv")  # default length would raise ComputeError
    assert df.height == 300
    assert df["id"].dtype == pl.String


def test_csv_falls_back_to_all_strings_after_inference_window(tmp_path):
    """A non-numeric value past the 10_000-row inference window makes the
    typed read fail; the retry loads everything as String rather than
    erroring out."""
    out = tmp_path / "past_window.csv"
    out.write_text(
        "id,x\n"
        + "\n".join(f"{i},{i / 2}" for i in range(10_500))  # numeric head
        + "\nlate-condition,-1\n"  # past the window
        + "\n".join(f"{i},{i / 2}" for i in range(10_501, 11_000))
        + "\n"
    )
    df = read_table(out, "csv")
    assert df.height == 11_000
    assert df["id"].dtype == pl.String
    assert df["x"].dtype == pl.String
    assert df["id"][10_500] == "late-condition"


def test_detect_format():
    from pathlib import Path

    assert detect_format(Path("a.csv")) == "csv"
    assert detect_format(Path("a.tsv")) == "tsv"
    assert detect_format(Path("a.ndjson")) == "jsonl"
    assert detect_format(Path("a.pq")) == "parquet"
    assert detect_format(Path("a.parq")) == "parquet"
    # .txt files are assumed tab-separated
    assert detect_format(Path("a.txt")) == "tsv"
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


def test_datetime_exports_second_resolution_text_formats_only(tmp_path):
    """CSV/TSV/JSONL serialize datetime columns to canonical UTC
    second-resolution strings; Parquet and Excel keep the real Datetime
    (millisecond resolution) values."""
    import polars as pl
    from datetime import datetime

    df = pl.DataFrame(
        {"d": [datetime(2022, 3, 22, 10, 15, 59, 673000), None]},
        schema={"d": pl.Datetime("ms")},
    )
    # text formats: truncated to whole seconds as readable strings
    for name, fmt in [("x.csv", "csv"), ("x.tsv", "tsv"), ("x.jsonl", "jsonl")]:
        out = tmp_path / name
        write_table(df, out, fmt)
        back = read_table(out, fmt)
        assert back["d"].dtype == pl.String, fmt
        assert back["d"].to_list()[0].startswith("2022-03-22T10:15:59"), fmt
        assert ".673" not in back["d"].to_list()[0] and back["d"][1] is None, fmt
    # parquet/xlsx: real datetimes survive with their milliseconds
    pq = tmp_path / "x.parquet"
    write_table(df, pq, "parquet")
    assert read_table(pq, "parquet")["d"].to_list()[0] == datetime(
        2022, 3, 22, 10, 15, 59, 673000
    )
    xl = tmp_path / "x.xlsx"
    write_table(df, xl, "xlsx")
    got = read_table(xl, "xlsx")["d"].to_list()[0]
    assert isinstance(got, datetime) and got == datetime(
        2022, 3, 22, 10, 15, 59, 673000
    )


def test_script_text_shape():
    from normalize_tabular_data.io import SCRIPT_SUFFIX, script_text

    assert SCRIPT_SUFFIX == ".ntd"
    text = script_text(
        [
            ("date_normalize", {"column": "Hired Date"}),
            ("trim_collapse", {"columns": ["Dept", "Name"]}),
            ("remove_columns", {"columns": ["Zip"]}),
        ],
        header_fields={"source": "employees.csv", "saved": "10:22"},
    )
    lines = text.strip().split("\n")
    assert lines[0] == "# normalize-tabular-data script"
    assert lines[1] == "# employees.csv"
    assert lines[2] == "# 10:22"
    assert lines[3] == 'date_normalize(column="Hired Date")'
    assert lines[4] == 'trim_collapse(columns=["Dept", "Name"])'
    assert lines[5] == 'remove_columns(columns=["Zip"])'
    # plain ASCII, newline-terminated
    text.encode("ascii")
    assert text.endswith("\n")


def test_write_script_ascii(tmp_path):
    from normalize_tabular_data.io import write_script

    out = tmp_path / "ops.ntd"
    write_script(
        out,
        [("trim_collapse", {"columns": ["a"]})],
        header_fields={"source": "café.csv"},
    )
    # header field with a non-ASCII source name still writes as ASCII
    body = out.read_text(encoding="ascii")
    assert 'trim_collapse(columns=["a"])' in body


def test_parse_script_line_round_trips_saved_steps():
    """Saved script lines parse back to exactly the (key, params) steps."""
    from normalize_tabular_data.io import parse_script_line, script_text

    steps = [
        ("trim_collapse", {"columns": ["Dept", 'Weird "name"']}),
        ("date_normalize", {"column": "Hired Date"}),
        ("split_column", {"column": "Notes", "delimiter": "", "max_parts": 0}),
        ("dedup_rows", {"columns": [], "keep": "first"}),
        ("fill_nulls", {"columns": ["a"], "value": "x, y"}),
    ]
    for key, params in steps:
        line = script_text([(key, params)], {}).splitlines()[-1]
        assert parse_script_line(line) == (key, params)


def test_read_script_skips_comments_and_blank_lines(tmp_path):
    from normalize_tabular_data.io import read_script

    script = tmp_path / "s.ntd"
    script.write_text(
        "# normalize-tabular-data script\n"
        "# source: employees.csv\n"
        "\n"
        '   trim_collapse(columns=["Dept"])   \n'
        'date_normalize(column = "Hired Date")\n',
        encoding="ascii",
    )
    assert read_script(script) == [
        ("trim_collapse", {"columns": ["Dept"]}),
        ("date_normalize", {"column": "Hired Date"}),
    ]


def test_read_script_bad_line_names_the_line(tmp_path):
    from normalize_tabular_data.io import read_script

    script = tmp_path / "s.ntd"
    script.write_text('# hi\ntrim_collapse(columns=["a"])\nfrobnicate(x\n')
    with pytest.raises(ValueError, match="line 3.*not an operation line"):
        read_script(script)


def test_play_script_line_rejects_non_json_values():
    from normalize_tabular_data.io import parse_script_line

    with pytest.raises(ValueError, match="bad value for 'value'"):
        parse_script_line('fill_nulls(columns=["A"], value=starts_or_not)')
