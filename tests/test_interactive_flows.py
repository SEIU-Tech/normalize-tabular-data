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


async def test_save_via_keys_infer_format_from_extension(csv_path, tmp_path):
    """The save dialog has no format picker: the extension chooses the
    format, and an unsupported extension is rejected with a notice."""

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(csv_path)
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "SaveModal"
        modal = app.screen
        # the permitted extensions are listed as static help text
        help_texts = [s.visual.plain for s in modal.query("Static.help")]
        assert any(".xlsx" in t and ".csv" in t for t in help_texts)

        # an unknown extension is refused and keeps the dialog open
        fake = tmp_path / "out.xyz"
        modal.path_input.value = str(fake)
        modal.action_ok()
        await pilot.pause()
        assert not fake.exists()

        # .tsv infers tsv without any picker
        fake = tmp_path / "out.tsv"
        modal.path_input.value = str(fake)
        modal.action_ok()
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


async def test_op_chooser_hotkeys(sample_csv_path):
    """Ops show their designated hotkey letter highlighted in place,
    e.g. "Normalize (d)ates"; pressing the marked letter picks that
    operation directly."""
    from textual.widgets import Label

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(sample_csv_path)
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        listing = app.screen.query_one("#oplist")
        titles = [item.query_one(Label).visual.plain for item in listing.children]
        assert titles == [
            "Normalize (d)ates",
            "Trim (w)hitespace",
            "Dedu(p)licate rows",
            "(C)ombine columns",
            "(S)plit column",
            "(R)emove columns",
        ]
        # press 'd' — jumps straight into the date op's parameters
        await pilot.press("d")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "OpParamsModal"
        assert app.screen.dialog_title == "Normalize dates"
        await pilot.press("escape")
        await pilot.pause()
        # 'p' — deduplicate
        await pilot.press("o")
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        assert app.screen.dialog_title == "Deduplicate rows"
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        assert app.screen.dialog_title == "Remove columns"


async def test_open_dialog_moves_up_a_directory(sample_data_dir, sample_csv_path):
    """The listing starts with "../" so the user can climb above the start dir,
    then come back down and still pick a file."""
    from textual.widgets import ListView

    app = NormalizeApp()
    async with app.run_test() as pilot:
        await pilot.press("f")
        await pilot.pause()
        modal = app.screen
        assert modal.__class__.__name__ == "OpenFileModal"
        modal._refresh_dir(sample_data_dir)
        await pilot.pause()
        listing = modal.query_one("#opendir", ListView)
        listing.focus()
        await pilot.pause()

        # first entry is always the parent directory
        assert listing.children[0].name == str(sample_data_dir.parent.resolve())

        # select it -> the dialog now lists the parent's contents
        listing.index = 0
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert modal.dir == sample_data_dir.parent.resolve()
        names = {item.name for item in listing.children}
        assert str(sample_data_dir) in names

        # navigate back into tests/data and open the csv from there
        down = [item.name for item in listing.children].index(str(sample_data_dir))
        listing.index = down
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        csv_index = [item.name for item in listing.children].index(str(sample_csv_path))
        listing.index = csv_index
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.pipeline is not None


async def test_combine_columns_dialog_mounts_and_applies(sample_csv_path):
    """Regression: the combine dialog has two text params (separator,
    new_name) — distinct widget ids; it mounts and applies cleanly."""
    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(sample_csv_path)
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        listing = app.screen.query_one("#oplist")
        listing.index = [i.name for i in listing.children].index("combine_columns")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "OpParamsModal"
        # separator field starts blank with the "Separator" shadow text
        assert app.screen.widgets["separator"].value == ""
        assert app.screen.widgets["separator"].placeholder == "Separator"

        app.screen.widgets["columns"].select("Name")
        app.screen.widgets["columns"].select("Zip")
        app.screen.widgets["separator"].value = "-"
        app.screen.widgets["new_name"].value = "name_zip"
        app.screen.action_ok()
        await pilot.pause()

        current = app.pipeline.current()
        assert current["name_zip"].to_list()[0] == "  Alice  Doe-10001"
        assert current.columns[-1] == "name_zip"


async def test_rename_column_via_header_click(sample_csv_path):
    """Clicking a header opens the rename dialog; a new name renames the
    column as a pipeline step (undoable)."""
    from textual.widgets import DataTable

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(sample_csv_path)
        await pilot.pause()
        table = app.screen.query_one("#preview", DataTable)
        dept = list(table.columns.values())[2]  # "Dept"

        def click_header() -> None:
            app.post_message(DataTable.HeaderSelected(table, dept.key, 2, dept.label))

        # simulate clicking the "Dept" header
        click_header()
        await pilot.pause()
        assert app.screen.__class__.__name__ == "RenameColumnModal"
        modal = app.screen
        assert modal.name_input.value == "Dept"

        modal.name_input.value = "dept_code"
        modal.action_ok()
        await pilot.pause()
        cols = app.pipeline.current().columns
        assert cols == ["member_id", "Hired Date", "dept_code", "Name", "Zip"]
        assert "new_name=dept_code" in " ".join(app.pipeline.step_summary())

        # duplicate names are rejected with a notify, not applied
        dept = list(table.columns.values())[2]  # now "dept_code"
        app.post_message(DataTable.HeaderSelected(table, dept.key, 2, dept.label))
        await pilot.pause()
        modal = app.screen
        modal.name_input.value = "Name"
        modal.action_ok()
        await pilot.pause()
        assert app.screen.__class__.__name__ == "MainScreen"
        assert "Name" not in app.pipeline.step_summary()[0]

        # undo restores the original name before the rename
        app.action_undo()
        assert app.pipeline.current().columns == [
            "member_id",
            "Hired Date",
            "Dept",
            "Name",
            "Zip",
        ]


async def test_op_chooser_leaves_data_visible(large_csv_path):
    """The op chooser docks over the sidebar area only: the preview table is
    not covered, so data rows stay visible in the main pane."""
    from textual.containers import Vertical
    from textual.widgets import DataTable

    app = NormalizeApp()
    async with app.run_test(size=(90, 24)) as pilot:
        app.load_path(large_csv_path)
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "OpChooserModal"
        box = app.screen.query_one(Vertical)
        table = [s for s in app.screen_stack if type(s).__name__ == "MainScreen"][
            0
        ].query_one("#preview", DataTable)
        box_region = box.region
        table_region = table.region
        # the dialog box ends before the table begins
        assert box_region.x + box_region.width <= table_region.x
        # 100-row sample shows its preview rows without any overlap
        _, preview_rows = table_region.size
        assert preview_rows >= 5
        # OK/Cancel buttons render fully inside the narrow dialog box
        from textual.widgets import Button

        for btn in app.screen.query(Button):
            r = btn.region
            assert r.x >= box_region.x
            assert r.x + r.width <= box_region.x + box_region.width - 2


async def test_op_params_modal_docks_in_sidebar(large_csv_path):
    """The parameter dialog docks over the sidebar too, and OK/Cancel fit."""
    from textual.containers import Vertical
    from textual.widgets import Button, DataTable

    app = NormalizeApp()
    async with app.run_test(size=(90, 24)) as pilot:
        app.load_path(large_csv_path)
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        listing = app.screen.query_one("#oplist")
        listing.index = [i.name for i in listing.children].index("split_column")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "OpParamsModal"
        box = app.screen.query_one(Vertical)
        box_region = box.region
        table = [s for s in app.screen_stack if type(s).__name__ == "MainScreen"][
            0
        ].query_one("#preview", DataTable)

        # dialog box lives inside the sidebar strip; nothing covers the table
        assert box_region.x + box_region.width <= table.region.x
        # every button lies fully inside the dialog box (minus padding)
        for btn in app.screen.query(Button):
            r = btn.region
            assert r.x >= box_region.x
            assert r.x + r.width <= box_region.x + box_region.width - 2


async def test_open_100_row_file_via_dialog(large_csv_path):
    """Second committed sample: 100 rows, different columns than employees.csv."""
    from textual.widgets import DataTable

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(large_csv_path)
        await pilot.pause()

        expected = [
            "employee_id",
            "Full Name",
            "Worksite",
            "Job Class",
            "Dues Status",
            "Signed Up",
            "Shift Code",
        ]
        assert app.pipeline.current().columns == expected
        assert app.pipeline.current().height == 100

        # full preview rendered (100 < PREVIEW_ROWS cap)
        table = app.screen.query_one("#preview", DataTable)
        assert (table.row_count, len(table.columns)) == (100, 7)
        # every distinct worksite phrase from the file is visible somewhere
        first_col = app.pipeline.current()["Worksite"].to_list()
        assert set(first_col) >= {
            "Hospital A",
            "Hospital B",
            "Logistics Yard",
            "Residence Hall",
        }


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
            "employee_id",
            "Worksite",
            "Job Class",
            "Dues Status",
            "Signed Up",
            "Shift Code",
        ]
        assert cols[6:] == [f"Full Name_{i}" for i in range(1, tokens + 1)]
        assert "Full Name" not in cols


async def test_left_right_scroll_by_whole_column(large_csv_path):
    """Left/Right snap the preview to column start boundaries: one column
    per press, not one character."""
    from normalize_tabular_data.app import PreviewTable

    app = NormalizeApp()
    # narrow pane so the table overflows horizontally (sidebar takes 39 cols)
    async with app.run_test(size=(70, 20)) as pilot:
        app.load_path(large_csv_path)
        await pilot.pause()
        table = app.screen.query_one("#preview", PreviewTable)
        table.focus()
        await pilot.pause()

        offsets = table._column_offsets()
        assert table.max_scroll_x > offsets[2]  # enough room to scroll

        await pilot.press("right")
        await pilot.pause()
        assert table.scroll_x == offsets[1]
        await pilot.press("right")
        await pilot.press("right")
        await pilot.pause()
        assert table.scroll_x == offsets[3]

        await pilot.press("left")
        await pilot.pause()
        assert table.scroll_x == offsets[2]
        # left past the start clamps at zero
        await pilot.press("left")
        await pilot.press("left")
        await pilot.press("left")
        await pilot.press("left")
        await pilot.pause()
        assert table.scroll_x == 0.0
