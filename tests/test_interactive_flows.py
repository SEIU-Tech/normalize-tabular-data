"""Interactive pilot tests: drive the actual TUI key flows end to end."""

import polars as pl
import pytest

from normalize_tabular_data.app import NormalizeApp

pytestmark = pytest.mark.asyncio


async def test_open_via_keys_and_apply_dates_via_keys(csv_path):
    app = NormalizeApp()
    async with app.run_test() as pilot:
        # o: open dialog, type the path, Enter
        await pilot.press("f")
        await pilot.pause()
        from textual.widgets import Input

        modal = app.screen
        assert modal.__class__.__name__ == "OpenFileModal"
        modal.query_one("#path_input", Input).value = str(csv_path)
        await pilot.press("enter")
        await pilot.pause()
        assert app.pipeline is not None
        assert app.pipeline.current().height == 4
        # preview table got populated
        from textual.widgets import DataTable

        table = app.screen.query_one("#preview", DataTable)
        assert table.row_count == 4

        # n: choose op — first item is "Normalize dates"; Enter selects it
        await pilot.press("o")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "OpChooserModal"
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "OpParamsModal"
        # confirm the parameter dialog (preselected date column validates fine):
        # choosing an operation applies it immediately — no separate apply step
        app.screen.action_ok()
        await pilot.pause()
        current = app.pipeline.current()
        assert current["Hired Date"].dtype == pl.Datetime("ns")
        assert not hasattr(app, "pending")  # removed two-step flow

        # u: undo restores the original data
        await pilot.press("u")
        assert app.pipeline.current()["Hired Date"].dtype == pl.String


async def test_escape_cancels_open_modal(csv_path):
    app = NormalizeApp()
    async with app.run_test() as pilot:
        await pilot.press("f")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "OpenFileModal"
        await pilot.press("escape")
        await pilot.pause()
        assert app.pipeline is None
        assert app.screen.__class__.__name__ == "MainScreen"


async def test_quit_binding(csv_path):
    app = NormalizeApp()
    async with app.run_test() as pilot:
        await pilot.press("f")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        # 'q' exits the app run loop
        await pilot.press("q")


async def test_save_via_keys(csv_path, tmp_path, monkeypatch):

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(csv_path)
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "SaveModal"
        fake = tmp_path / "out.tsv"
        app.screen.path_input.value = str(fake)
        app.screen.fmt_choice.value = "tsv"
        app.screen.action_ok()
        await pilot.pause()
        assert fake.exists()
        df = pl.read_csv(fake, separator="\t")
        assert df.height == 4


async def test_open_via_directory_listing(sample_data_dir, sample_csv_path):
    """Drive the open dialog's ListView (not just typing a path) — the path
    that used to crash with DuplicateIds on directory re-render."""
    from textual.widgets import DataTable, ListView

    app = NormalizeApp()
    async with app.run_test() as pilot:
        await pilot.press("f")
        await pilot.pause()
        modal = app.screen
        assert modal.__class__.__name__ == "OpenFileModal"

        # navigate into tests/data by re-selecting the dir (exercises _refresh_dir
        # twice: initial mount + navigation) and confirm no DuplicateIds crash
        modal._refresh_dir(sample_data_dir)
        await pilot.pause()
        modal._refresh_dir(sample_data_dir)
        await pilot.pause()

        listing = modal.query_one("#opendir", ListView)
        index = [item.name or "" for item in listing.children].index(
            str(sample_csv_path)
        )
        listing.focus()
        await pilot.pause()
        listing.index = index
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        assert app.pipeline is not None
        current = app.pipeline.current()
        assert current.height == 6
        assert current.columns == ["member_id", "Hired Date", "Dept", "Name", "Zip"]

        # polars-backed preview rendered in the main window
        table = app.screen.query_one("#preview", DataTable)
        assert table.row_count == 6
        assert len(table.columns) == 5


async def test_open_100_row_file_via_dialog(large_csv_path):
    """Second committed sample: 100 rows, different columns than employees.csv."""
    from textual.widgets import DataTable

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(large_csv_path)
        await pilot.pause()

        expected = [
            "employee_id", "Full Name", "Worksite", "Job Class",
            "Dues Status", "Signed Up", "Shift Code",
        ]
        assert app.pipeline.current().columns == expected
        assert app.pipeline.current().height == 100

        # full preview rendered (100 < PREVIEW_ROWS cap)
        table = app.screen.query_one("#preview", DataTable)
        assert (table.row_count, len(table.columns)) == (100, 7)
        # every distinct worksite phrase from the file is visible somewhere
        first_col = app.pipeline.current()["Worksite"].to_list()
        assert set(first_col) >= {"Hospital A", "Hospital B", "Logistics Yard", "Residence Hall"}


async def test_nulls_display_as_marker(sample_csv_path):
    """Hired Date row 3 is an empty cell in employees.csv -> shows <NULL>."""
    from textual.widgets import DataTable

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(sample_csv_path)
        await pilot.pause()
        table = app.screen.query_one("#preview", DataTable)
        row_idx = 2  # third data row: Hired Date is empty in the file
        row_cells = [str(cell) for cell in table.get_row_at(row_idx)]
        assert "<NULL>" in row_cells
        # explicitly non-empty cells never get the marker
        assert row_cells[0] == "1003"
        assert "<NULL>" not in [str(cell) for cell in table.get_row_at(0)]


async def test_split_column_op_applies(large_csv_path):
    """Regression: split-column params dialog used to crash at mount with
    InvalidSelectValueError because Select.BLANK == False in Textual 8.2.8."""
    from textual.widgets import ListView

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(large_csv_path)
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        listing = app.screen.query_one("#oplist", ListView)
        listing.index = [i.name for i in listing.children].index("split_column")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "OpParamsModal"

        # expected width: token count of the widest (whitespace-collapsed) name
        before = app.pipeline.current()
        tokens = (
            before["Full Name"]
            .str.strip_chars()
            .str.replace_all(r"\s+", " ")
            .str.split(" ")
            .list.len()
            .max()
        )

        # fill params: split "Full Name" on spaces; no max-parts entry —
        # width is chosen automatically from the data
        app.screen.widgets["column"].value = "Full Name"
        app.screen.widgets["delimiter"].value = " "
        app.screen.action_ok()
        await pilot.pause()

        # applied immediately (no separate apply step); the kept columns stay
        # in order, then one output column per token of the widest name
        cols = app.pipeline.current().columns
        assert cols[:6] == [
            "employee_id", "Worksite", "Job Class", "Dues Status",
            "Signed Up", "Shift Code",
        ]
        assert cols[6:] == [f"Full Name_{i}" for i in range(1, tokens + 1)]
        assert "Full Name" not in cols
