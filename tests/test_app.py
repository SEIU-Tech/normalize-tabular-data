from datetime import datetime

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
        assert app.pipeline.current()["Hired Date"].dtype == pl.Datetime("ms")
        assert app.pipeline.current()["Hired Date"].to_list()[0] == datetime(
            2022, 3, 22
        )
        # undo restores the raw strings
        app.action_undo()
        assert app.pipeline.current()["Hired Date"].dtype == pl.String
        assert app.pipeline.current()["Hired Date"].to_list()[0] == "2022-03-22"


async def test_provided_csv_sample(csv_path):
    from normalize_tabular_data import io

    df = io.read_table(csv_path, "csv")
    assert df.columns == ["id", "Hired Date", "Dept", "Notes"]


async def test_unreadable_files_show_message_not_crash(tmp_path):
    """Bad files produce an in-TUI error toast; the app keeps running."""
    bad_ext = tmp_path / "model.wacz"
    bad_ext.write_text("not a table")
    bad_xlsx = tmp_path / "fake.xlsx"
    bad_xlsx.write_bytes(b"this is not an excel file at all")
    garbage_csv = tmp_path / "garbage.csv"
    # rows with more fields than the header -> Polars ComputeError
    garbage_csv.write_bytes(b"a,b\n1,2\n1,2,3,4\n")

    app = NormalizeApp()
    async with app.run_test() as pilot:
        for path in (bad_ext, bad_xlsx, garbage_csv):
            app.load_path(path)  # must not raise
            await pilot.pause()
            assert app.pipeline is None
        # the app is still responsive afterwards
        await pilot.press("o")  # op chooser warns 'open a file first'
        await pilot.pause()
        assert app.screen.__class__.__name__ == "MainScreen"
        await pilot.press("q")


def test_dtype_marks():
    """Compact dtype marks: dt/str/int/dec; everything else oth."""
    from normalize_tabular_data.widgets import _dtype_mark

    assert _dtype_mark("Datetime(time_unit='ns', time_zone=None)") == "dt "
    assert _dtype_mark("Date") == "day"
    assert _dtype_mark("Time") == "dt "
    assert _dtype_mark("String") == "str"
    assert _dtype_mark("Categorical(...)") == "str"
    assert _dtype_mark("Int64") == "int" and _dtype_mark("UInt32") == "int"
    assert _dtype_mark("Float64") == "dec"
    assert _dtype_mark("Decimal(12, 2)") == "dec"
    assert _dtype_mark("Boolean") == "t/f"
    # special types fall back to "oth"
    assert _dtype_mark("List(String)") == "oth"
    assert _dtype_mark("Null") == "oth"


async def test_sidebar_scrollable_when_column_list_long(tmp_path):
    """A column list taller than the sidebar panel scrolls instead of
    clipping; a short list leaves no scrollbar."""
    from textual.containers import VerticalScroll

    from normalize_tabular_data.widgets import ColumnSidebar

    wide = tmp_path / "wide.csv"
    pl.DataFrame({f"col{i:02d}": ["x"] for i in range(40)}).write_csv(wide)
    app = NormalizeApp()
    async with app.run_test(size=(70, 20)) as pilot:
        app.load_path(wide)
        await pilot.pause()
        sidebar = app.screen.query_one("#sidebar", ColumnSidebar)
        scroll = sidebar.query_one(VerticalScroll)
        assert scroll.max_scroll_y > 0

        # all 40 columns present in the scrolled content, lines built for
        # the scrollbar-reduced inner width so none wraps
        lines = sidebar.content_text.plain.split("\n")
        assert len(lines) == 41
        assert max(len(l) for l in lines) <= 33
        scroll.scroll_end(animate=False)
        await pilot.pause()
        assert scroll.scroll_offset.y == scroll.max_scroll_y

        # short file: fits, nothing to scroll
        small = tmp_path / "small.csv"
        pl.DataFrame({f"col{i:02d}": ["x"] for i in range(6)}).write_csv(small)
        app.load_path(small)
        await pilot.pause()
        assert sidebar.query_one(VerticalScroll).max_scroll_y == 0


async def test_large_file_previews_random_sample(tmp_path):
    """>250-row files preview 250 random rows, not the first 250; the same
    sample stays stable across preview refreshes within one load.
    (Preview cells are rendered strings, so compare converted ids.)"""
    import polars as pl

    path = tmp_path / "big.csv"
    pl.DataFrame({"id": range(2000)}).write_csv(path)

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(path)
        await pilot.pause()
        table = app.screen.query_one("#preview")
        assert table.row_count == 250
        ids1 = [int(table.get_row_at(r)[0]) for r in range(table.row_count)]
        assert len(set(ids1)) == 250  # all in range, no duplicates
        # not just the first 250 rows of the file
        assert set(ids1) != set(range(250))

        app.refresh_preview()
        await pilot.pause()
        ids2 = [int(table.get_row_at(r)[0]) for r in range(table.row_count)]
        assert ids1 == ids2


async def test_sidebar_shows_dtype_marks(csv_path):
    """Sidebar lines carry the mark for each column, visually highlighted."""
    from normalize_tabular_data.widgets import ColumnSidebar

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(csv_path)
        await pilot.pause()
        sidebar = app.screen.query_one("#sidebar", ColumnSidebar)
        text = sidebar.content_text
        lines = text.plain.split("\n")
        assert lines[0] == "Columns (4)"
        # every column line shows its dtype mark at a fixed slice: position 2,
        # after the one-char date-candidate flag and one space. ("1","2","3","4"
        # in the csv round-trips as Int64)
        assert [line[2:5] for line in lines[1:]] == [
            "int",
            "str",
            "str",
            "str",
        ]
        # the mark segment carries its own highlight style, distinct from text
        body_start = len("Columns (4)\n")
        assert any("cyan" in str(s.style) and s.start >= body_start for s in text.spans)
        await pilot.press("q")


async def test_sidebar_truncates_long_names(csv_path):
    """Long column names are truncated to the sidebar's inner width (39):
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
        text = sidebar.content_text
        lines = text.plain.split("\n")
        # inner width: 39 - 2 (border) - 2 (padding) = 35
        assert all(len(line) <= 35 for line in lines)
        # the 40-char name is cut at exactly the fitting width, not wrapped
        assert lines[5].startswith("  str " + "X" * 21)
        assert "nulls=5" in lines[5] and lines[5].count("X") == 21
        # the "nulls=..." info left-aligns as one column on every line
        starts = {line.find("nulls=") for line in lines[1:]}
        assert starts == {28}
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


async def test_header_labels_app_with_version(csv_path):
    """The header's docked label reads "normalize-tabular-data <version>"."""
    from normalize_tabular_data import __version__
    from normalize_tabular_data.app import AppHeader

    app = NormalizeApp()
    async with app.run_test() as pilot:
        label = app.screen.query_one(AppHeader).query_one(".app_name")
        assert label.render().plain == f"normalize-tabular-data {__version__}"


def test_theme_persists_user_selection(tmp_path):
    """Choosing a theme writes its name to the app's configuration file."""
    from normalize_tabular_data.app import NormalizeApp

    config_dir = tmp_path / "config"
    app = NormalizeApp(config_dir=config_dir)
    app._app_ready = True  # a real run does this at mount
    app.theme = "textual-light"
    assert (config_dir / "theme").read_text(encoding="utf-8").strip() == (
        "textual-light"
    )


async def test_theme_config_relaunches_with_saved_theme(tmp_path):
    """The theme picked last time is applied when the app starts."""
    from normalize_tabular_data.app import NormalizeApp

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "theme").write_text("textual-light\n", encoding="utf-8")
    app = NormalizeApp(config_dir=config_dir)
    async with app.run_test():
        assert app.theme == "textual-light"


async def test_theme_config_with_gone_theme_name(tmp_path):
    """A saved theme that no longer exists is ignored; the app keeps the
    default and still runs."""
    from normalize_tabular_data.app import NormalizeApp
    import textual.constants as constants

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "theme").write_text("vanished-theme-name\n", encoding="utf-8")
    app = NormalizeApp(config_dir=config_dir)
    async with app.run_test():
        assert app.theme == constants.DEFAULT_THEME
