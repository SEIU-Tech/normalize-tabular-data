import polars as pl
import pytest
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture
def sample_csv_path() -> Path:
    """Committed sample file used to validate the open dialog end to end."""
    return DATA_DIR / "employees.csv"


@pytest.fixture
def sample_data_dir() -> Path:
    return DATA_DIR


@pytest.fixture
def large_csv_path() -> Path:
    """Second committed sample: 100 rows, different schema (worksite data)."""
    return DATA_DIR / "worksite.csv"


SAMPLE_DATA = {
    "id": ["1", "2", "3", "4"],
    "Hired Date": ["2022-03-22", "Mar 1, 2019", "", "Sept 5 2021"],
    "Dept": ["  Engineering ", "Ops", "Engineering  &  Support", "Ops"],
    "Notes": ["", " ", "Alice  Doe", ""],
}


@pytest.fixture
def sample_df() -> pl.DataFrame:
    return pl.DataFrame(SAMPLE_DATA)


@pytest.fixture
def csv_path(tmp_path):
    p = tmp_path / "sample.csv"
    pl.DataFrame(SAMPLE_DATA).write_csv(p)
    return p


@pytest.fixture
def xlsx_path(tmp_path):
    p = tmp_path / "sample.xlsx"
    pl.DataFrame(SAMPLE_DATA).write_excel(p)
    return p


@pytest.fixture
def jsonl_path(tmp_path):
    p = tmp_path / "sample.jsonl"
    pl.DataFrame(SAMPLE_DATA).write_ndjson(p)
    return p


@pytest.fixture
def parquet_path(tmp_path):
    p = tmp_path / "sample.parquet"
    pl.DataFrame(SAMPLE_DATA).write_parquet(p)
    return p
