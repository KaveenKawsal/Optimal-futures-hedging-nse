from datetime import date

import pytest

from fetch_history import archive_url, fetch_one, normalise


def test_archive_format_switch():
    assert "/2024/JUL/fo05JUL2024" in archive_url(date(2024, 7, 5), "futures")
    assert "BhavCopy_NSE_FO_0_0_0_20240708" in archive_url(date(2024, 7, 8), "futures")


def test_udiff_lot_size_comes_from_each_contract_row():
    text = "TradDt,FinInstrmTp,TckrSymb,XpryDt,ClsPric,NewBrdLotQty\n2024-12-31,IDF,NIFTY,2025-01-30,23500,25\n2024-12-31,IDF,NIFTY,2025-02-27,23600,75\n"
    result = normalise(text, "futures")
    assert result.Lot_Size.tolist() == [25, 75]


def test_non_positive_source_prices_are_rejected():
    text = "Index Name,Index Date,Closing Index Value\nNIFTY 50,02-01-2020,0\n"
    with pytest.raises(ValueError, match="non-positive"):
        normalise(text, "spot")


def test_missing_archive_html_is_recorded_without_becoming_prices(tmp_path, monkeypatch):
    monkeypatch.setattr("fetch_history.local_archive", lambda *args: None)

    class Response:
        status_code = 200
        content = b"<html><title>File not found</title></html>"
        headers = {"Content-Type": "text/html"}
        url = "https://www.niftyindices.com/errorpage.aspx"

        def raise_for_status(self):
            pass

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    frame, metadata = fetch_one(Session(), date(2020, 1, 4), "spot", tmp_path, 1)
    assert frame is None
    assert metadata["status"] == "unavailable_html"
    assert len(metadata["source_sha256"]) == 64
    assert not list(tmp_path.glob("*.csv"))


def test_download_session_date_must_match_request(tmp_path, monkeypatch):
    monkeypatch.setattr("fetch_history.local_archive", lambda *args: None)

    class Response:
        status_code = 200
        content = b"Index Name,Index Date,Closing Index Value\nNIFTY 50,03-01-2020,12000\n"
        headers = {"Content-Type": "text/csv"}

        def raise_for_status(self):
            pass

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    with pytest.raises(ValueError, match="dates do not match"):
        fetch_one(Session(), date(2020, 1, 2), "spot", tmp_path, 1)
