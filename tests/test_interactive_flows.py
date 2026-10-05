"""Interactive pilot tests: drive the actual TUI key flows end to end."""

from datetime import datetime

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

        # n: choose op — first item is "Normalize date(t)imes"; Enter selects it
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
        assert current["Hired Date"].to_list()[0] == datetime(2022, 3, 22)
        assert current["Hired Date"].dtype == pl.Datetime("ms")
        assert not hasattr(app, "pending")  # removed two-step flow

        # u: undo restores the original data
        await pilot.press("u")
        assert app.pipeline.current()["Hired Date"].dtype == pl.String
        assert app.pipeline.current()["Hired Date"].to_list()[0] == "2022-03-22"


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
            "Normalize date(t)imes",
            "Normalize (d)ates",
            "Trim (w)hitespace",
            "(C)ombine columns",
            "(S)plit column",
            "(R)emove columns",
            "Dedu(p)licate rows",
        ]
        # press 'd' — jumps straight into the date-only op's parameters
        await pilot.press("d")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "OpParamsModal"
        assert app.screen.dialog_title == "Normalize (d)ates"
        # 't' — the datetime variant
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert app.screen.dialog_title == "Normalize date(t)imes"
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


async def test_save_with_script_dialog(csv_path, tmp_path):
    """Ticking 'Save sequence of operations?' opens the script naming dialog;
    the script lands at the suggested .ntd path with one line per applied op.
    Unticked (the default) saves only the table."""
    from textual.widgets import Label

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(csv_path)
        await pilot.pause()
        # apply one operation so the log has content
        from normalize_tabular_data.ops import OP_REGISTRY

        app._apply_now(OP_REGISTRY["trim_collapse"], {"columns": ["Notes"]})
        # a header-click rename also lands in the log
        from textual.widgets import DataTable

        table = app.screen.query_one("#preview", DataTable)
        dept = list(table.columns.values())[2]
        app.post_message(DataTable.HeaderSelected(table, dept.key, 2, dept.label))
        await pilot.pause()
        app.screen.name_input.value = "dept_code"
        app.screen.action_ok()
        await pilot.pause()

        # save with the script box ticked
        table_out = tmp_path / "out.csv"
        await pilot.press("s")
        await pilot.pause()
        modal = app.screen
        assert modal.__class__.__name__ == "SaveModal"
        assert modal.save_script.value is False  # default unchecked
        modal.path_input.value = str(table_out)
        modal.save_script.value = True
        modal.action_ok()
        await pilot.pause()

        # second dialog asks for the script name, suggested .ntd
        script_modal = app.screen
        assert script_modal.__class__.__name__ == "ScriptNameModal"
        help_texts = [
            *(l.visual.plain for l in script_modal.query(Label)),
            *(s.visual.plain for s in script_modal.query("Static.help")),
        ]
        assert any(".ntd" in t for t in help_texts)  # help mentions the ext
        suggested = script_modal.path_input.value
        assert suggested == str(tmp_path / "out.ntd")
        # the extension is not the user's to change: anything typed is
        # made to end in .ntd
        script_modal.path_input.value = str(tmp_path / "out.savetxt")
        script_modal.action_ok()
        await pilot.pause()

        assert table_out.exists()
        script_path = tmp_path / "out.ntd"
        assert script_path.exists()
        assert not (tmp_path / "out.savetxt").exists()
        lines = script_path.read_text().strip().split("\n")
        assert lines[0] == "# normalize-tabular-data script"
        assert f'bootstrap(table="{table_out}")' not in "".join(lines)
        op_lines = [l for l in lines if l and not l.startswith("#")]
        assert op_lines == [
            'trim_collapse(columns=["Notes"])',
            'rename_single(column="Dept", new_name="dept_code")',
        ]


async def test_save_without_script_no_dialog(csv_path, tmp_path):
    """Unchecked (default): no second dialog, no script file."""
    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(csv_path)
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        modal = app.screen
        modal.path_input.value = str(tmp_path / "plain.csv")
        modal.action_ok()
        await pilot.pause()
        assert app.screen.__class__.__name__ != "ScriptNameModal"
        assert (tmp_path / "plain.csv").exists()
        assert not (tmp_path / "plain.ntd").exists()


async def test_play_script_footer_key_and_gating(csv_path):
    """(P)lay script, (O)peration, (U)ndo, (R)edo and (S)ave are grayed
    out until a file is loaded; pressing p then opens the script picker."""
    from normalize_tabular_data.widgets import MenuFooter, MenuKey

    gated = {
        "play_script": "(P)lay script",
        "choose_op": "(O)peration",
        "undo": "(U)ndo",
        "redo": "(R)edo",
        "save": "(S)ave",
    }

    def footer_key(description: str) -> MenuKey:
        return [
            k
            for k in app.screen.query_one(MenuFooter).query(MenuKey)
            if k.description == description
        ][0]

    app = NormalizeApp()
    async with app.run_test() as pilot:
        for action, description in gated.items():
            assert app.check_action(action, ()) is None
            assert footer_key(description).has_class("-disabled")
        app.load_path(csv_path)
        await pilot.pause()
        await pilot.pause()
        # recomposed after load: re-query via footer_key
        for action, description in gated.items():
            assert app.check_action(action, ()) is True
            assert not footer_key(description).has_class("-disabled")
        # pressing p opens the script picker over a loaded table
        await pilot.press("p")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "ScriptPickerModal"
        # the browse list takes focus so arrows browse and Enter plays
        from textual.widgets import ListView

        assert type(app.focused) is ListView
        await pilot.press("escape")
        await pilot.pause()


async def test_play_script_via_dialog_arrows_and_enter(csv_path, tmp_path):
    """Browse-first picker: the list is focused, arrows highlight (previewing),
    Enter on a script applies it to the open file."""
    from normalize_tabular_data import io

    script = tmp_path / "clean.ntd"
    io.write_script(script, [("trim_collapse", {"columns": ["Dept"]})], {})

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(csv_path)
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        modal = app.screen
        assert type(app.focused).__name__ == "ListView"
        lv = modal.query_one("#opendir")
        # press down until the script entry is highlighted
        target = [it.name for it in lv.children].index(str(script))
        for _ in range(target + 1):  # first down starts the highlight at ".."
            await pilot.press("down")
        await pilot.pause()
        assert modal.preview_text.splitlines()[-1] == 'trim_collapse(columns=["Dept"])'
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "MainScreen"
        assert app.pipeline.current()["Dept"][0] == "Engineering"  # was padded
        assert app.op_log == [("trim_collapse", {"columns": ["Dept"]})]


async def test_play_script_ok_button_applies_highlight(csv_path, tmp_path):
    """OK applies the highlighted script; with nothing script-like selected it
    warns and stays open instead of silently canceling."""
    from normalize_tabular_data import io

    script = tmp_path / "clean.ntd"
    io.write_script(script, [("trim_collapse", {"columns": ["Dept"]})], {})

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(csv_path)
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        modal = app.screen
        lv = modal.query_one("#opendir")
        # nothing selected yet (highlight starts on the parent ".." entry):
        # OK must keep the dialog open
        modal._ok_pressed()
        await pilot.pause()
        assert app.screen is modal

        lv.index = [it.name for it in lv.children].index(str(script))
        await pilot.pause()
        modal._ok_pressed()
        await pilot.pause()
        assert app.screen.__class__.__name__ == "MainScreen"
        assert app.op_log == [("trim_collapse", {"columns": ["Dept"]})]


async def test_play_script_applies_steps_to_open_file(csv_path, tmp_path):
    from normalize_tabular_data import io

    script = tmp_path / "clean.ntd"
    steps = [
        ("trim_collapse", {"columns": ["Dept"]}),
        ("date_normalize", {"column": "Hired Date"}),
    ]
    io.write_script(script, steps, header_fields={"source": str(csv_path)})

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(csv_path)
        await pilot.pause()
        app.play_script_file(script)
        await pilot.pause()
        current = app.pipeline.current()
        assert current["Dept"][0] == "Engineering"  # was "  Engineering "
        assert current["Hired Date"].dtype == pl.Datetime("ms")
        assert current["Hired Date"][0] == datetime(2022, 3, 22)
        # steps recorded in the operation log exactly as written
        assert app.op_log == steps


async def test_play_script_renames_play_back(csv_path, tmp_path):
    """rename_single is not a chooser op but appears in every saved script
    that contains a header-click rename; the player must accept its key."""
    from normalize_tabular_data import io
    from normalize_tabular_data.ops import OP_REGISTRY, PLAY_REGISTRY

    # chooser stays at its six ops; the internal rename op is playback-only
    assert "rename_single" not in OP_REGISTRY
    assert PLAY_REGISTRY["rename_single"] is not None

    script = tmp_path / "with-rename.ntd"
    steps = [("rename_single", {"column": "Dept", "new_name": "dept_code"})]
    io.write_script(script, steps, header_fields={})

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(csv_path)
        await pilot.pause()
        app.play_script_file(script)
        await pilot.pause()
        assert app.pipeline.current().columns == [
            "id",
            "Hired Date",
            "dept_code",
            "Notes",
        ]
        assert app.op_log == steps


async def test_play_committed_worksite_script(large_csv_path):
    """The committed sample script applies fully to the committed sample
    table: date parse, trims, whitespace split, two renames."""
    from pathlib import Path

    from normalize_tabular_data import io

    script = Path(__file__).parent / "data" / "worksite.ntd"
    steps = io.read_script(script)

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(large_csv_path)
        await pilot.pause()
        app.play_script_file(script)
        await pilot.pause()
        current = app.pipeline.current()
        assert current.columns == [
            "employee_id",
            "Worksite",
            "Job Class",
            "Dues Status",
            "Signed Up",
            "Shift Code",
            "First Name",
            "Last Name",
        ]
        assert current["Signed Up"].dtype == pl.Datetime("ms")  # empty -> null
        assert current["Signed Up"].to_list()[0] == datetime(2020, 12, 12)
        # the split tokens: first row "Quinn Huang" -> two non-null parts
        assert current["First Name"][0] == "Quinn"
        assert current["Last Name"][0] == "Huang"
        assert app.op_log == steps


async def test_play_script_alert_and_rollback(tmp_path, csv_path):
    """A step that is impossible against the loaded file stops the script
    and undoes every earlier step of the script."""
    from normalize_tabular_data import io

    script = tmp_path / "broken.ntd"
    io.write_script(
        script,
        [
            ("trim_collapse", {"columns": ["Dept"]}),
            (
                "split_column",
                {"column": "NoSuchColumn", "delimiter": "", "max_parts": 2},
            ),
        ],
        header_fields={},
    )

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(csv_path)
        await pilot.pause()
        before = app.pipeline.current()
        app.play_script_file(script)
        await pilot.pause()
        after = app.pipeline.current()
        # steps applied before the bad step were rolled back: Dept untrimmed
        # again and dates still plain strings
        assert before.equals(after)
        assert app.op_log == []


async def test_play_script_unknown_operation_rolls_back(tmp_path, csv_path):
    from normalize_tabular_data import io

    script = tmp_path / "mystery.ntd"
    io.write_script(script, [("frobnicate", {"x": 1})], header_fields={})

    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(csv_path)
        await pilot.pause()
        before = app.pipeline.current()
        app.play_script_file(script)
        await pilot.pause()
        assert app.pipeline.current().equals(before)
        assert app.op_log == []


async def test_play_script_bad_file_reports_not_crashes(tmp_path, csv_path):
    app = NormalizeApp()
    async with app.run_test() as pilot:
        app.load_path(csv_path)
        await pilot.pause()
        before = app.pipeline.current()
        # unreadable / missing script files produce an alert; nothing changes
        await pilot.pause()
        app.play_script_file(tmp_path / "missing.ntd")
        app.play_script_file(tmp_path)  # a directory: read_text fails
        await pilot.pause()
        assert app.pipeline.current().equals(before)
        assert app.op_log == []


async def test_script_picker_previews_highlighted_script(tmp_path):
    """As the browse highlight moves (or a path is typed), the picker dialog
    shows a preview of the selected .ntd script; non-script files clear it."""
    from textual.widgets import Button, Input

    from normalize_tabular_data.app import NormalizeApp
    from normalize_tabular_data.screens import ScriptPickerModal

    script = tmp_path / "crew.ntd"
    body = (
        "# normalize-tabular-data script\n\n"
        'trim_collapse(columns=["Full Name"])\n'
        'date_normalize(column="Signed Up")\n'
    )
    script.write_text(body)
    (tmp_path / "out.csv").write_text("a,b\n1,2\n")

    app = NormalizeApp()
    async with app.run_test(size=(90, 24)) as pilot:
        app.push_screen(ScriptPickerModal(tmp_path), lambda chosen: None)
        await pilot.pause()
        modal = app.screen
        assert modal.__class__.__name__ == "ScriptPickerModal"
        preview = modal.query_one("#script_preview")
        assert modal.preview_text == ""  # nothing highlighted yet
        # the highlighted text paints the composite ($boost over $surface)
        # the box paints behind it — not the terminal's default background
        from textual.color import Color

        boost = Color.parse(app.get_css_variables()["boost"])
        surface = Color.parse(app.get_css_variables()["surface"])
        expected = "#" + "".join(
            f"{round(c * boost.a + b * (1 - boost.a)):02X}"
            for c, b in zip(boost.rgb, surface.rgb)
        )
        assert modal.preview_background == expected == "#272727"

        lv = modal.query_one("#opendir")
        lv.index = [
            i for i, it in enumerate(lv.children) if it.name.endswith("crew.ntd")
        ][0]
        await pilot.pause()
        assert modal.preview_text == body.strip()

        # selecting a non-script file clears the preview
        lv.index = [
            i for i, it in enumerate(lv.children) if it.name.endswith("out.csv")
        ][0]
        await pilot.pause()
        assert modal.preview_text == ""

        # typing a path previews that script too
        modal.query_one("#path_input", Input).value = str(script)
        await pilot.pause()
        assert modal.preview_text == body.strip()

        # the preview does not push OK/Cancel out of the dialog box
        box = modal.query_one("Vertical").region
        for btn in modal.query(Button):
            r = btn.region
            assert r.x >= box.x and r.x + r.width <= box.x + box.width


async def test_toasts_sit_bottom_left_clear_of_pane_borders(sample_csv_path):
    """Notify toasts are relocated bottom-left, nudged one column and one
    row inward from the screen corner, and lifted above the panes' bottom
    border row (app CSS: ToastRack margin-bottom 2 + left align + 1 col
    padding). The infobox is outlined in the severity color, not a left
    bar, and paints a background of its own (an accent tint over the
    theme background, $infobox-bg) — unlike the panes' cool slate."""
    from textual.color import Color
    from textual.widgets._toast import Toast, ToastRack

    app = NormalizeApp()
    # notifications must be enabled for run_test or no ToastRack is mounted
    async with app.run_test(size=(100, 30), notifications=True) as pilot:
        app.load_path(sample_csv_path)
        # pause enough for the "Loaded ..." toast to display
        await pilot.pause(0.5)
        await pilot.pause()
        toast = app.screen.query_one(Toast)
        region = toast.region
        # one column in from the left edge, and entirely clear of the
        # panes' shared bottom border row (just above the footer, at h-2)
        assert region.x == 1
        assert region.y + region.height <= app.size.height - 2
        # pin the CSS: bottom margin 2 (default 1 rode on the border row)
        rack = app.screen.get_child_by_type(ToastRack)
        assert rack.styles.margin.bottom == 2
        assert rack.styles.align == ("left", "bottom")
        assert rack.styles.padding.left == 1
        assert app.screen.query_one("ToastHolder").styles.align_horizontal == "left"
        # outline on all four edges in the severity color — no left bar
        border = toast.styles.border
        assert all(edge is not None for edge in border)
        assert border.top[1] == border.right[1] == border.bottom[1] == border.left[1]
        # self-owned background: accent 18% over the theme background,
        # distinct from every pane's look (background / surface / panel)
        variables = app.get_css_variables()
        expected = Color.blend(
            Color.parse(variables["background"]),
            Color.parse(variables["accent"]),
            0.18,
        ).hex
        assert toast.styles.background.hex == expected
        pane_colors = {variables[name] for name in ("background", "surface", "panel")}
        assert toast.styles.background.hex not in pane_colors


async def test_palette_hides_quit_and_screenshot():
    """The command palette keeps its remaining system commands but no
    longer offers Quit (owned by the footer's (Q) key) or Screenshot."""
    app = NormalizeApp()
    async with app.run_test() as pilot:
        titles = [c.title for c in app.get_system_commands(app.screen)]
        assert "Quit" not in titles and "Screenshot" not in titles
        assert "Theme" in titles  # the untouched commands survive


async def test_command_menu_searches_nothing_and_is_positioned():
    """ctrl+p opens the command menu: no search field anywhere, 3 rows of
    air above the drop-down, and the box centered with 5-space margins."""
    from textual.command import CommandList, CommandPalette

    app = NormalizeApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.press("ctrl+p")
        # the menu reveals its box only once its command-gather worker
        # finishes (-ready); wait for the popup to become visible
        for _ in range(12):
            await pilot.pause(0.25)
        pal = app.screen
        assert CommandPalette.is_open(app)
        # nothing focused: typing cannot pour into a (hidden) search field
        assert pal.focused is None
        strips = app.screen._compositor.render_strips()
        paint = "".join(s.text for s in strips)
        assert "🔎" not in paint  # search icon gone
        # no entering-field line above the margin rows
        assert not any("▔" in s.text[5:95] for s in strips[:3])
        # 3 rows of air: first command row is y=4 (rows 0..2 are the air)
        assert "Keys" in strips[4].text[5:50]
        # the drop-down keyline spans the center box, x=5..94: 5 blank
        # columns at both edges
        rowidx = next(i for i, s in enumerate(strips[:12]) if "▁" in s.text[5:95])
        columns = [x for x, ch in enumerate(strips[rowidx].text) if ch == "▁"]
        assert columns == [*range(5, 95)]
        # keyboard: Enter runs the highlighted ("Keys") command, the menu
        # closes and help lands on the main screen
        cl = pal.query_one(CommandList)
        cl.highlighted = 0  # "Keys"
        await pilot.pause()
        await pilot.press("enter")
        for _ in range(8):
            await pilot.pause(0.25)
        assert not CommandPalette.is_open(app)


async def test_initial_file_command_line(sample_csv_path):
    """NormalizeApp(initial_file=...) loads the table at startup — the
    optional FILE given on the command line."""
    from textual.widgets import DataTable

    app = NormalizeApp(initial_file=sample_csv_path)
    async with app.run_test() as pilot:
        for _ in range(4):
            await pilot.pause(0.25)
        await pilot.pause()
        assert app.pipeline is not None
        assert app.path == sample_csv_path
        table = app.screen.query_one(DataTable)
        assert table.row_count == app.pipeline.current().height
        # footer menus enabled right away (no manual open needed)
        assert app.check_action("choose_op", ()) is True


async def test_initial_file_missing_stays_graceful(tmp_path):
    """A command-line file that cannot be read alerts instead of crashing
    the TUI, which remains on the main screen with nothing loaded."""
    from textual.widgets import DataTable

    app = NormalizeApp(initial_file=tmp_path / "nonexistent.csv")
    async with app.run_test() as pilot:
        for _ in range(4):
            await pilot.pause(0.25)
        assert app.pipeline is None
        assert app.screen.query_one(DataTable).row_count == 0
        # still fully usable: the open dialog comes up
        await pilot.press("f")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "OpenFileModal"


async def test_initial_script_plays_after_load(tmp_path, csv_path):
    """With --script named on the command line, the .ntd file is played on
    the auto-opened table right away — the steps act as if the user had
    pressed P and picked the script."""
    from textual.widgets import DataTable

    script = tmp_path / "tidy.ntd"
    script.write_text(
        "# normalize-tabular-data script\n"
        'trim_collapse(columns=["Dept", "Notes"])\n'
        'date_normalize(column="Hired Date")\n'
    )
    app = NormalizeApp(initial_file=csv_path, initial_script=script)
    async with app.run_test() as pilot:
        for _ in range(5):
            await pilot.pause(0.25)
        await pilot.pause()
        current = app.pipeline.current()
        assert current["Dept"].to_list()[0] == "Engineering"  # was "  Engineering "
        assert current["Hired Date"].dtype == pl.Datetime("ms")
        assert current["Hired Date"].to_list()[0] == datetime(2022, 3, 22)
        # both steps landed in the op log, in play order
        assert app.op_log == [
            ("trim_collapse", {"columns": ["Dept", "Notes"]}),
            ("date_normalize", {"column": "Hired Date"}),
        ]
        assert app.screen.query_one(DataTable).row_count == 4


async def test_initial_script_failure_rolls_back_gracefully(tmp_path, csv_path):
    """A command-line script whose steps cannot run against the file alerts
    and rolls back — the loaded table is untouched, the TUI stays on it."""
    from textual.widgets import DataTable

    script = tmp_path / "broken.ntd"
    script.write_text(
        'trim_collapse(columns=["Dept"])\n'
        'trim_collapse(columns=["No Such Column"])\n'
        'rename_single(column="Dept", new_name="Department")\n'
    )
    app = NormalizeApp(initial_file=csv_path, initial_script=script)
    async with app.run_test() as pilot:
        for _ in range(5):
            await pilot.pause(0.25)
        await pilot.pause()
        # step 2 is impossible: both steps rolled back, log untouched
        assert app.op_log == []
        assert app.pipeline.applied == []
        assert app.pipeline.current()["Dept"].to_list()[0] == "  Engineering "
        # everything still works: undo is a no-op, the dialog opens
        await pilot.press("u")
        await pilot.pause()
        assert app.screen.query_one(DataTable).row_count == 4
        await pilot.press("o")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "OpChooserModal"
