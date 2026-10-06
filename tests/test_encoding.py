"""Non-UTF-8 encodings: CSV/TSV/JSONL reading transcodes via chardet.
Each fixture lives in tests/data, written natively in its claimed encoding
(ISO 8859-3 Maltese, Windows-1256 Arabic, Shift_JIS-2004 Japanese)."""

from pathlib import Path

import polars as pl

from normalize_tabular_data.io import _decoded_text, detect_format, read_table

DATA = Path(__file__).parent / "data"


def test_latin3_maltese_csv_reads():
    df = read_table(
        DATA / "maltese-latin3.csv", detect_format(DATA / "maltese-latin3.csv")
    )
    assert df.columns == ["Kunjom", "Ilsien", "Dett"]
    # Latin-3-only letters (Ċ Ġ Ħ Ż and lowercases) survive intact
    assert df["Kunjom"].to_list()[0] == "Ċikku"
    assert df["Ilsien"].to_list()[3] == "Il-Qrendi"
    assert df["Dett"].to_list()[1] == "2019-03-01"


def test_cp1256_arabic_csv_reads():
    df = read_table(
        DATA / "arabic-cp1256.csv", detect_format(DATA / "arabic-cp1256.csv")
    )
    assert df.columns == ["الاسم", "المدينة", "التعيين"]
    assert df["الاسم"].to_list()[3] == "سمر خالد"
    assert df["المدينة"].to_list()[5] == "تونس"


def test_shiftjis2004_japanese_csv_reads():
    df = read_table(
        DATA / "japanese-shiftjis2004.csv",
        detect_format(DATA / "japanese-shiftjis2004.csv"),
    )
    assert df.columns == ["氏名", "都市", "入社日"]
    assert df["氏名"].to_list()[2] == "鈴木 一郎"
    assert df["都市"].to_list()[3] == "仙台市"


def test_non_utf8_tsv_reads(tmp_path):
    out = tmp_path / "maltese.tsv"
    raw = (DATA / "maltese-latin3.csv").read_bytes().replace(b",", b"\t")
    out.write_bytes(raw)
    df = read_table(out, "tsv")
    assert df.columns == ["Kunjom", "Ilsien", "Dett"]
    assert df["Ilsien"].to_list()[2] == "Il-Gudja"


def test_non_utf8_ndjson_reads(tmp_path):
    record = (
        '{"اسم": "مصعب", "المسار": "تونس"}\n{"اسم": "سلمي", "المسار": "الرياض"}\n'
    ).encode("cp1256")
    out = tmp_path / "arabic.ndjson"
    out.write_bytes(record)
    df = read_table(out, "jsonl")
    assert df["اسم"].to_list() == ["مصعب", "سلمي"]


def test_utf16_bom_stripped(tmp_path):
    # UTF-16-LE with a BOM: chardet reports "UTF-16" and Python's decoder
    # consumes the BOM; the text must decode clean (not with a leading
    # ﻿ polluting the first column name)
    out = tmp_path / "greek.csv"
    out.write_bytes(b"\xff\xfe" + "Kunjom,Μηνη\nĊikku,Ηράκλειο\n".encode("utf-16-le"))
    df = read_table(out, "csv")
    assert df.columns == ["Kunjom", "Μηνη"]
    assert df["Μηνη"].to_list() == ["Ηράκλειο"]


def test_utf8_file_passes_through_untouched():
    # the sniffer short-circuits on valid UTF-8: the exact bytes come back
    raw = "Kunjom,Ilsien\nĊikku,Ħamrun\n".encode()
    assert _decoded_text(raw) == raw


def test_japanese_fixture_parquet_roundtrip(tmp_path):
    df = read_table(DATA / "japanese-shiftjis2004.csv", "csv")
    out = tmp_path / "japanese.parquet"
    df.write_parquet(out)
    assert pl.read_parquet(out).equals(df)
