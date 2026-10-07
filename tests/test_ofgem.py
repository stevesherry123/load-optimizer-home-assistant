import importlib.util
import json
from datetime import date
from pathlib import Path
import sys
import unittest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "load_optimizer"
    / "optimizer"
    / "ofgem.py"
)
SPEC = importlib.util.spec_from_file_location("integration_ofgem", MODULE_PATH)
ofgem = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ofgem
SPEC.loader.exec_module(ofgem)


def table_source(title, rows):
    options = {
        "data": {"value": rows},
        "options": {"title": {"text": f"<h3>{title}</h3>"}},
    }
    return f"var options = {json.dumps(options)};\nfunction createLayout() {{}}"


class OfgemPriceCapTests(unittest.TestCase):
    def setUp(self):
        self.source = table_source(
            "Electricity standing charges and unit rates paid by Direct Debit, single rate",
            [
                [
                    "Region",
                    "Daily standing charge July to September 2026",
                    "Daily standing charge October to December 2026",
                    "Unit rate July to September 2026",
                    "Unit rate  October to December 2026",
                ],
                [
                    "North Western England",
                    "47.61 pence per day",
                    "45.68 pence per day",
                    "26.13 pence per kWh",
                    "26.49 pence per kWh",
                ],
            ],
        )

    def test_extracts_unique_everviz_embeds(self):
        page = """
        <iframe src="https://app.everviz.com/inject/first/?v=1"></iframe>
        <iframe src="https://app.everviz.com/inject/first/?v=2"></iframe>
        <iframe src="https://app.everviz.com/inject/second/"></iframe>
        """

        self.assertEqual(
            ofgem.everviz_urls(page),
            [
                "https://app.everviz.com/inject/first/",
                "https://app.everviz.com/inject/second/",
            ],
        )

    def test_parses_north_west_direct_debit_periods(self):
        references = ofgem.parse_everviz_references(
            self.source,
            region="North Western England",
            payment_method="direct_debit",
        )

        self.assertEqual(len(references), 2)
        self.assertEqual(references[0].effective_from, date(2026, 7, 1))
        self.assertEqual(references[0].effective_to, date(2026, 10, 1))
        self.assertEqual(references[0].unit_rate_p_per_kwh, 26.13)
        self.assertEqual(references[1].effective_from, date(2026, 10, 1))
        self.assertEqual(references[1].effective_to, date(2027, 1, 1))
        self.assertEqual(references[1].unit_rate_p_per_kwh, 26.49)

    def test_selects_reference_by_effective_date(self):
        references = ofgem.parse_everviz_references(
            self.source,
            region="North Western England",
            payment_method="direct_debit",
        )

        selected = ofgem.reference_for_date(references, date(2026, 10, 7))

        self.assertIsNotNone(selected)
        self.assertEqual(selected.unit_rate_p_per_kwh, 26.49)

    def test_ignores_table_for_another_payment_method(self):
        self.assertEqual(
            ofgem.parse_everviz_references(
                self.source,
                region="North Western England",
                payment_method="standard_credit",
            ),
            [],
        )

    def test_rejects_missing_region(self):
        with self.assertRaisesRegex(ValueError, "no row for region"):
            ofgem.parse_everviz_references(
                self.source,
                region="London",
                payment_method="direct_debit",
            )


if __name__ == "__main__":
    unittest.main()
