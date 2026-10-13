from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


def test_dashboard_tabs_calculator_and_short_filters():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=60)
    assert not app.exception
    assert len(app.tabs) == 10
    rounding = next(element for element in app.selectbox if element.label == "Lot rounding")
    rounding.select("Nearest lot").run(timeout=60)
    assert not app.exception
    app.sidebar.date_input[0].set_value((date(2024, 1, 2), date(2024, 2, 1))).run(timeout=60)
    assert not app.exception
    assert any("Not enough observations" in element.value for element in app.info)
    app.sidebar.date_input[0].set_value((date(2024, 1, 2), date(2024, 1, 3))).run(timeout=60)
    assert not app.exception
    assert app.warning


@pytest.mark.skipif(not Path("data/2020_2025/master.csv").exists(), reason="History download pending")
def test_extended_dataset_and_cost_controls():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=60)
    app.sidebar.selectbox[0].select("2020–2025 history").run(timeout=60)
    assert not app.exception
    assert any("2020" in element.value and "2025" in element.value for element in app.sidebar.markdown)
    comparison = next(
        element.value for element in app.dataframe if "Trading costs (₹)" in element.value.columns
    )
    before = comparison["Trading costs (₹)"].sum()
    fees = next(element for element in app.sidebar.number_input if element.label.startswith("Fees per"))
    fees.set_value(10.0).run(timeout=60)
    assert not app.exception
    after = next(element.value for element in app.dataframe if "Trading costs (₹)" in element.value.columns)
    assert after["Trading costs (₹)"].sum() > before
