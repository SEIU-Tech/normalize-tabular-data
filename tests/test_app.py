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
        # emulate choosing "Normalize dates" and confirming params via handlers
        app.action_choose_op()
        await pilot.pause()
        app.action_apply()
        # no pending op yet: apply should warn, not crash
        assert app.pipeline is not None
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
