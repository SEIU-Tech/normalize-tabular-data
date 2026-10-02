import polars as pl
import pytest

from normalize_tabular_data.app import NormalizeApp

pytestmark = pytest.mark.asyncio


async def test_app_composes_and_quits(csv_path):
    app = NormalizeApp()
    async with app.run_test() as pilot:
        assert app.screen
        # open the sample file through the direct loader (param plumbing to ops/io)

        app.load_path(csv_path)
        await pilot.pause()
        assert app.pipeline is not None
        assert app.pipeline.current().height == 4
        assert len(app.analyzed) == 4
        # quit binding doesn't crash
        await pilot.press("q")


async def test_apply_date_op_through_pipeline(csv_path):
    app = NormalizeApp()
    async with app.run_test() as pilot:
        from normalize_tabular_data.ops import OP_REGISTRY

        app.load_path(csv_path)
        await pilot.pause()
        # exercise the pipeline directly (UI-independent behavior)
        app.pipeline.apply(OP_REGISTRY["date_normalize"], {"column": "Hired Date"})
        app.refresh_all()
        await pilot.pause()
        assert app.pipeline.current()["Hired Date"].dtype == pl.Datetime("ns")
        # undo restores String dtype
        app.action_undo()
        assert app.pipeline.current()["Hired Date"].dtype == pl.String


async def test_provided_csv_sample(csv_path):
    from normalize_tabular_data import io

    df = io.read_table(csv_path, "csv")
    assert df.columns == ["id", "Hired Date", "Dept", "Notes"]


def test_dtype_marks():
    """Compact dtype marks: dt/str/int/dec; everything else oth."""
    from normalize_tabular_data.widgets import _dtype_mark

    assert _dtype_mark("Datetime(time_unit='ns', time_zone=None)") == "dt "
    assert _dtype_mark("Date") == "dt "
    assert _dtype_mark("Time") == "dt "
    assert _dtype_mark("String") == "str"
    assert _dtype_mark("Categorical(...)") == "str"
    assert _dtype_mark("Int64") == "int" and _dtype_mark("UInt32") == "int"
    assert _dtype_mark("Float64") == "dec"
    assert _dtype_mark("Decimal(12, 2)") == "dec"
    # special types fall back to "oth"
    assert _dtype_mark("Boolean") == "oth"
    assert _dtype_mark("List(String)") == "oth"
    assert _dtype_mark("Null") == "oth"


async def test_sidebar_shows_dtype_marks(csv_path):
    """Sidebar lines carry the mark for each column, visually highlighted."""
    from normalize_tabular_data.widgets import ColumnSidebar

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(csv_path)
        await pilot.pause()
        sidebar = app.screen.query_one("#sidebar", ColumnSidebar)
        text = sidebar.render()
        lines = text.plain.split("\n")
        assert lines[0] == "Columns (4)"
        # every column line shows its dtype mark at a fixed slice: position 2,
        # after the one-char date-candidate flag and one space. ("1","2","3","4"
        # in the csv round-trips as Int64)
        assert [line[2:5] for line in lines[1:]] == [
            "int", "str", "str", "str",
        ]
        # the mark segment carries its own highlight style, distinct from text
        body_start = len("Columns (4)\n")
        assert any(
            "cyan" in str(s.style) and s.start >= body_start
            for s in text.spans
        )
        await pilot.press("q")


async def test_sidebar_truncates_long_names(csv_path):
    """Long column names are truncated to the sidebar's inner width (35):
    no line ever runs wide enough to wrap into extra rows."""
    from normalize_tabular_data.ops import ColumnInfo
    from normalize_tabular_data.widgets import ColumnSidebar

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(csv_path)
        await pilot.pause()
        sidebar = app.screen.query_one("#sidebar", ColumnSidebar)
        infos = list(app.analyzed.values()) + [ColumnInfo("X" * 40, "String", 5)]
        sidebar.set_infos(infos)
        await pilot.pause()
        text = sidebar.render()
        lines = text.plain.split("\n")
        # inner width: 35 - 2 (border) - 2 (padding) = 31
        assert all(len(line) <= 31 for line in lines)
        # the 40-char name is cut at exactly the fitting width, not wrapped
        assert lines[5].startswith("  str " + "X" * 17)
        assert "nulls=5" in lines[5] and lines[5].count("X") == 17
        # the "nulls=..." info left-aligns as one column on every line
        starts = {line.find("nulls=") for line in lines[1:]}
        assert starts == {24}
        await pilot.press("q")


async def test_footer_renders_menu_style(csv_path):
    """Footer keys have no key chip; the letter in "(F)ile" is highlighted."""
    from normalize_tabular_data.widgets import MenuFooter, MenuKey

    app = NormalizeApp()
    async with app.run_test() as pilot:
        footer = app.screen.query_one(MenuFooter)
        keys = list(footer.query(MenuKey))
        descriptions = [k.description for k in keys]
        assert any(d == "(F)ile" for d in descriptions)
        for key_obj in keys:
            if key_obj.description == "(F)ile":
                text = key_obj.render()
                assert text.plain == "(F)ile"  # no leading key chip
                # the hotkey char (index 1) carries the key-highlight style
                styled = [
                    (span.start, span.end, str(span.style))
                    for span in text.spans
                    if "bold" in str(span.style) or "+" in str(span.style)
                ]
                assert any(start <= 1 < end for start, end, _ in styled)
        await pilot.press("q")
