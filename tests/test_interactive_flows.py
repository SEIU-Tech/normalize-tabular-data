"""Interactive pilot tests: drive the actual TUI key flows end to end."""

import polars as pl
import pytest

from normalize_tabular_data.app import NormalizeApp

pytestmark = pytest.mark.asyncio


async def test_open_via_keys_and_apply_dates_via_keys(csv_path):
    app = NormalizeApp()
    async with app.run_test() as pilot:
        # o: open dialog, type the path, Enter
        await pilot.press("o")
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
        await pilot.press("n")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "OpChooserModal"
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "OpParamsModal"
        # confirm the parameter dialog (preselected date column validates fine)
        app.screen.action_ok()
        await pilot.pause()
        assert app.pending is not None and app.pending[0].key == "date_normalize"

        # a: apply the pending op
        await pilot.press("a")
        await pilot.pause()
        current = app.pipeline.current()
        assert current["Hired Date"].dtype == pl.Datetime("ns")
        assert app.pending is None

        # u: undo restores the original data
        await pilot.press("u")
        assert app.pipeline.current()["Hired Date"].dtype == pl.String


async def test_escape_cancels_open_modal(csv_path):
    app = NormalizeApp()
    async with app.run_test() as pilot:
        await pilot.press("o")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "OpenFileModal"
        await pilot.press("escape")
        await pilot.pause()
        assert app.pipeline is None
        assert app.screen.__class__.__name__ == "MainScreen"


async def test_quit_binding(csv_path):
    app = NormalizeApp()
    async with app.run_test() as pilot:
        await pilot.press("o")
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
        target = tmp_path / "out.takken"
        fake = tmp_path / "out.tsv"
        app.screen.path_input.value = str(fake)
        app.screen.fmt_choice.value = "tsv"
        app.screen.action_ok()
        await pilot.pause()
        assert fake.exists()
        df = pl.read_csv(fake, separator="\t")
        assert df.height == 4
