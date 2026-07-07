"""CHIRPS adapter unit tests."""
from __future__ import annotations

import gzip
import io
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from hali.ingestion.chirps import ChirpsAdapter
from hali.ingestion.models import RawPayload, SourceName


@pytest.fixture
def adapter(mock_pool):
    pool, _ = mock_pool
    return ChirpsAdapter(pool)


def _fake_ftp(files_by_year: dict[int, list[str]], file_bytes: bytes) -> MagicMock:
    ftp = MagicMock()

    def nlst(path: str) -> list[str]:
        year = int(path.rstrip("/").split("/")[-1])
        return files_by_year.get(year, [])

    def retrbinary(cmd: str, callback) -> None:
        callback(file_bytes)

    ftp.nlst.side_effect = nlst
    ftp.retrbinary.side_effect = retrbinary
    return ftp


def _gz(data: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(data)
    return buf.getvalue()


def test_ftp_download_latest_picks_newest_file_at_or_before_cutoff(adapter):
    files = ["chirps-v2.0.2026.06.01.tif.gz", "chirps-v2.0.2026.06.30.tif.gz", "chirps-v2.0.2026.07.10.tif.gz"]
    fake = _fake_ftp({2026: files}, _gz(b"tif-bytes"))
    with (
        patch("hali.ingestion.chirps.ftplib.FTP", return_value=fake),
        patch("hali.ingestion.chirps.utc_now") as mock_now,
    ):
        mock_now.return_value.date.return_value = date(2026, 7, 7)
        result = adapter._ftp_download_latest()
    assert result is not None
    path, found_date = result
    # 07.10 is after the 07.06 cutoff (utc_now - 1 day) so 06.30 must win
    assert found_date == date(2026, 6, 30)


def test_ftp_download_latest_returns_none_when_no_candidates(adapter):
    fake = _fake_ftp({2026: []}, b"")
    with (
        patch("hali.ingestion.chirps.ftplib.FTP", return_value=fake),
        patch("hali.ingestion.chirps.utc_now") as mock_now,
    ):
        mock_now.return_value.date.return_value = date(2026, 1, 2)
        result = adapter._ftp_download_latest()
    assert result is None


def test_validate_rejects_missing_file(adapter):
    raw = RawPayload(source=SourceName.CHIRPS, raw_data={"local_tif_path": "/no/such/file.tif"}, source_event_id="chirps-x")
    assert adapter.validate(raw) is None
