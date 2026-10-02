"""normalize-tabular-data: TUI for normalizing tabular data with polars."""

__version__ = "0.1.0"


def main() -> None:
    try:
        from normalize_tabular_data.app import NormalizeApp
    except ImportError as exc:  # helpful message if an optional engine is missing
        import sys

        print(
            f"normalize-tabular-data is missing a dependency ({exc}).\n"
            "Reinstall with: uv tool install --force --reinstall normalize-tabular-data",
            file=sys.stderr,
        )
        raise SystemExit(1)
    NormalizeApp().run()
