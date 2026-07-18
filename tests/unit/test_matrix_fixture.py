from pathlib import Path

import pdfplumber

FIXTURE = Path("tests/fixtures/onboarding/matrix_target.pdf")

def test_matrix_fixture_has_a_reconstructable_grid():
    assert FIXTURE.exists()
    with pdfplumber.open(FIXTURE) as pdf:
        tables = pdf.pages[0].find_tables()
    assert tables, "fixture must yield at least one table"
    grid = tables[0].extract()
    assert grid[0][:2] == ["No", "Criterion"]
    assert any("Corrosion" in (cell or "") for row in grid for cell in row)
