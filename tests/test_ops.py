import polars as pl
import pytest
from datetime import date, datetime

from normalize_tabular_data.ops import (
    OP_REGISTRY,
    ColumnInfo,
    Operation,
    Pipeline,
    analyze_column,
)

# --- individual operations ---------------------------------------------------


def test_date_normalize():
    op = OP_REGISTRY["date_normalize"]
    df = op.apply(
        pl.DataFrame({"d": ["2022-03-22", "Mar 1, 2019", "garbage", None]}),
        {"column": "d"},
    )
    # in-memory dates stay real UTC datetimes at millisecond resolution
    # (the text exports serialize them to seconds; parquet/xlsx do not)
    assert df["d"].dtype == pl.Datetime("ms")
    assert df["d"].to_list() == [
        datetime(2022, 3, 22),
        datetime(2019, 3, 1),
        None,
        None,
    ]
    # fractioned input keeps its milliseconds (truncated at ns -> ms)
    fract = op.apply(
        pl.DataFrame({"d": ["2022-03-22T10:15:59.673918"]}), {"column": "d"}
    )
    assert fract["d"].to_list()[0] == datetime(2022, 3, 22, 10, 15, 59, 673000)


def test_date_only():
    op = OP_REGISTRY["date_only"]
    df = op.apply(
        pl.DataFrame(
            {
                "d": [
                    "2022-03-22",
                    "Mar 1, 2019",
                    "2021-02-13T03:04:00",
                    "garbage",
                    None,
                ]
            }
        ),
        {"column": "d"},
    )
    # date-only ISO-8601: any input condenses to the UTC calendar date
    assert df["d"].dtype == pl.Date
    assert df["d"].to_list() == [
        date(2022, 3, 22),
        date(2019, 3, 1),
        date(2021, 2, 13),
        None,
        None,
    ]


def test_trim_collapse():
    op = OP_REGISTRY["trim_collapse"]
    df = op.apply(
        pl.DataFrame({"a": ["  hello   world ", "\tmulti\t brk "], "n": [1, 2]}),
        {"columns": ["a"]},
    )
    assert df["a"].to_list() == ["hello world", "multi brk"]
    assert df["n"].to_list() == [1, 2]


def test_dedup_rows_all_and_subset():
    op = OP_REGISTRY["dedup_rows"]
    df = pl.DataFrame({"a": [1, 1, 2], "b": [1, 2, 2]})
    assert op.apply(df, {"columns": ["a"], "keep": "first"}).height == 2
    assert op.apply(df, {"columns": [], "keep": "first"}).height == 3


def test_combine_columns():
    op = OP_REGISTRY["combine_columns"]
    df = op.apply(
        pl.DataFrame({"first": ["Al", None], "last": ["Doe", "Doe"]}),
        {"columns": ["first", "last"], "separator": " ", "new_name": "full"},
    )
    assert df["full"].to_list() == ["Al Doe", "Doe"]  # null parts skipped


def test_split_column_unlimited():
    op = OP_REGISTRY["split_column"]
    df = op.apply(
        pl.DataFrame({"name": ["Al Doe", "Bo S. Ray", "X"], "n": [1, 2, 3]}),
        {"column": "name", "delimiter": " "},
    )
    assert df.columns == ["n", "name_1", "name_2", "name_3"]
    row = df.filter(pl.col("n") == 3).to_dicts()[0]
    assert row["name_1"] == "X" and row["name_2"] is None


def test_unknown_column_raises_validation():
    op = OP_REGISTRY["date_normalize"]
    pl_df = pl.DataFrame({"d": ["2022-01-01"]})
    pipe = Pipeline(pl_df)
    with pytest.raises(ValueError, match="pick a column"):
        pipe.apply(op, {"column": "nope"})


def test_combine_requires_two_and_unique_name():
    pipe = Pipeline(pl.DataFrame({"a": ["1"], "b": ["2"]}))
    with pytest.raises(ValueError, match="at least 2"):
        pipe.apply(
            OP_REGISTRY["combine_columns"],
            {"columns": ["a"], "separator": "-", "new_name": "c"},
        )
    with pytest.raises(ValueError, match="already exists"):
        pipe.apply(
            OP_REGISTRY["combine_columns"],
            {"columns": ["a", "b"], "separator": "-", "new_name": "a"},
        )


# --- pipeline ----------------------------------------------------------------


def test_pipeline_recompute_and_undo_redo(sample_df):
    pipe = Pipeline(sample_df)
    pipe.apply(OP_REGISTRY["trim_collapse"], {"columns": ["Dept"]})
    pipe.apply(
        OP_REGISTRY["date_normalize"],
        {"column": "Hired Date"},
    )
    cur = pipe.current()
    assert "Ops  " not in " ".join(cur["Dept"].to_list())
    assert cur["Hired Date"].dtype == pl.Datetime("ms")
    assert cur["Hired Date"][0] == datetime(2022, 3, 22)

    # undo: back to trimmed state (Hired Date still raw strings)
    assert pipe.undo()
    df1 = pipe.current()
    assert df1["Hired Date"].dtype == pl.String
    assert pipe.undo() and not pipe.undo()  # only two steps existed
    assert pipe.current().equals(sample_df)

    assert pipe.redo() and pipe.redo()  # re-apply both steps
    cur = pipe.current()
    assert cur["Hired Date"].dtype == pl.Datetime("ms")
    assert cur["Hired Date"][0] == datetime(2022, 3, 22)
    assert len(pipe.step_summary()) == 2


def test_pipeline_applies_recompute_from_source(sample_df):
    pipe = Pipeline(sample_df)
    pipe.apply(OP_REGISTRY["trim_collapse"], {"columns": ["Notes"]})
    pipe.apply(OP_REGISTRY["date_normalize"], {"column": "Hired Date"})
    # recompute folds all steps from the original source
    cur = pipe.current()
    assert cur["Notes"].to_list() == ["", "", "Alice Doe", ""]
    assert cur["Hired Date"].dtype == pl.Datetime("ms")
    assert cur["Hired Date"].to_list()[0] == datetime(2022, 3, 22)


def test_analyze_column_flags_date_candidate():
    df = pl.DataFrame(
        {"d": ["2022-03-22", "Mar 1, 2019", "Sept 5 2021", "not a date at all!?!"]}
    )
    info = analyze_column(df, "d")
    assert isinstance(info, ColumnInfo)
    assert info.dtype == "String" and info.date_candidate
    assert not analyze_column(pl.DataFrame({"n": [1, 2, 3]}), "n").date_candidate


def test_registry_complete():
    assert set(OP_REGISTRY) == {
        "date_normalize",
        "date_only",
        "trim_collapse",
        "dedup_rows",
        "combine_columns",
        "split_column",
        "remove_columns",
    }
    assert all(isinstance(o, Operation) for o in OP_REGISTRY.values())
    # the header-click rename is internal: it exists but is not offered
    from normalize_tabular_data.ops import RENAME_OP

    assert RENAME_OP.key not in OP_REGISTRY
    renamed = RENAME_OP.apply(
        pl.DataFrame({"a": [1], "b": [2]}), {"column": "a", "new_name": "z"}
    )
    assert renamed.columns == ["z", "b"]
    assert all(isinstance(o, Operation) for o in OP_REGISTRY.values())


def test_split_column_whitespace_mode_default():
    """' ' (and blank-forced whitespace) splits on any run of whitespace,
    after stripping edges."""
    op = OP_REGISTRY["split_column"]
    df = op.apply(
        pl.DataFrame({"name": ["  Al    Doe ", "\tBo \n S. Ray\t", "", None]}),
        {"column": "name", "delimiter": " "},
    )
    assert df["name_1"].dtype == pl.String
    assert df["name_1"].to_list() == ["Al", "Bo", None, None]
    assert df["name_2"].to_list() == ["Doe", "S.", None, None]
    assert df["name_3"].to_list() == [None, "Ray", None, None]


def test_split_column_width_chosen_from_data():
    """No max-parts entry: the number of {col}_N columns is whatever the
    longest actual split needs (here 4 tokens beats 2 and 3)."""
    op = OP_REGISTRY["split_column"]
    df = op.apply(
        pl.DataFrame({"v": ["a-b", "a", "a-b-c-d"]}),
        {"column": "v", "delimiter": "-"},
    )
    assert df.columns == ["v_1", "v_2", "v_3", "v_4"]
    assert df["v_2"].to_list() == ["b", None, "b"]
    assert df["v_4"].to_list() == [None, None, "d"]
    # short values pad with null, not empty strings
    assert df.filter(pl.col("v_2").is_null()).to_dicts()[0] == {
        "v_1": "a",
        "v_2": None,
        "v_3": None,
        "v_4": None,
    }


def test_pipeline_split_blank_delimiter_means_whitespace():
    """Blank delimiter passes validation and splits on whitespace runs."""
    pipe = Pipeline(pl.DataFrame({"name": ["A   B"]}))
    pipe.apply(OP_REGISTRY["split_column"], {"column": "name", "delimiter": ""})
    assert pipe.current().columns == ["name_1", "name_2"]


def test_split_column_other_delimiter_still_trims_edges():
    op = OP_REGISTRY["split_column"]
    df = op.apply(
        pl.DataFrame({"v": [" a-b - c ", "-d"]}),
        {"column": "v", "delimiter": "-"},
    )
    assert df["v_1"].to_list() == ["a", ""]
    assert df["v_2"].to_list() == ["b ", "d"]


def test_remove_columns():
    op = OP_REGISTRY["remove_columns"]
    df = op.apply(
        pl.DataFrame({"a": [1], "b": [2], "c": [3]}),
        {"columns": ["a", "c"]},
    )
    assert df.columns == ["b"]


def test_remove_columns_requires_selection():
    pipe = Pipeline(pl.DataFrame({"a": [1], "b": [2]}))
    with pytest.raises(ValueError, match="pick at least one"):
        pipe.apply(OP_REGISTRY["remove_columns"], {"columns": []})
