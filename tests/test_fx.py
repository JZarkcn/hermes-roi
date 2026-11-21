"""Unit tests for roi.fx (T04b-data, D-019).

The committed Xe snapshot must load with the exact fetched rates, USD
must pass through, unknown currencies must fail loudly (never assume
1:1), and the money path must stay Decimal-only.
"""
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from roi import fx as F


def _tmp_fx(raw: dict) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    with f:
        json.dump(raw, f)
    return Path(f.name)


class LoadFxTableTest(unittest.TestCase):
    def setUp(self):
        self.table = F.load_fx_table()

    def test_snapshot_rates_exact(self):
        self.assertEqual(self.table["CNY"].rate, Decimal("6.64910834"))
        self.assertEqual(self.table["EUR"].rate, Decimal("0.89194653"))
        self.assertEqual(self.table["GBP"].rate, Decimal("0.74534421"))
        self.assertEqual(self.table["CNY"].base, "USD")
        self.assertIn("xe.com", self.table["CNY"].source)
        self.assertEqual(str(self.table["CNY"].as_of), "2026-11-02")

    def test_missing_file(self):
        with self.assertRaises(F.FxError):
            F.load_fx_table(Path("/nonexistent/fx.json"))

    def test_empty_rates(self):
        with self.assertRaises(F.FxError):
            F.load_fx_table(_tmp_fx({"as_of": "2026-11-02", "rates": {}}))

    def test_nonpositive_rate(self):
        with self.assertRaises(F.FxError):
            F.load_fx_table(_tmp_fx(
                {"as_of": "2026-11-02", "rates": {"CNY": "0"}}))

    def test_float_rate_refused(self):
        with self.assertRaises(F.FxError):
            F.load_fx_table(_tmp_fx(
                {"as_of": "2026-11-02", "rates": {"CNY": 6.6491}}))


class ToUsdTest(unittest.TestCase):
    def setUp(self):
        self.table = F.load_fx_table()

    def test_cny_to_usd_divides(self):
        # 100 CNY at 1 USD = 6.64910834 CNY -> 15.039625... USD
        got = F.to_usd(Decimal("100"), "CNY", self.table)
        want = (Decimal("100") / Decimal("6.64910834")).quantize(
            Decimal("0.000001"))
        self.assertEqual(got, want)
        self.assertTrue(Decimal("15.0396") < got < Decimal("15.0397"))

    def test_usd_passthrough(self):
        self.assertEqual(
            F.to_usd(Decimal("12.3456789"), "USD", self.table),
            Decimal("12.345679"))

    def test_case_and_whitespace_insensitive_ccy(self):
        self.assertEqual(
            F.to_usd(Decimal("100"), " cny ", self.table),
            F.to_usd(Decimal("100"), "CNY", self.table))

    def test_unknown_currency_raises(self):
        with self.assertRaises(F.FxError):
            F.to_usd(Decimal("1"), "XYZ", self.table)

    def test_float_amount_refused(self):
        with self.assertRaises(F.FxError):
            F.to_usd(1.5, "USD", self.table)

    def test_negative_amount_refused(self):
        with self.assertRaises(F.FxError):
            F.to_usd(Decimal("-1"), "CNY", self.table)

    def test_wrong_base_raises(self):
        bad = {**self.table, "EUR": F.FxRate(
            base="EUR", quote="EUR", rate=Decimal("1"), as_of=self.table["EUR"].as_of, source="t")}
        with self.assertRaises(F.FxError):
            F.to_usd(Decimal("10"), "EUR", bad)

    def test_roundtrip_within_precision(self):
        # CNY -> USD -> CNY lands back within the 6dp quantize error
        usd = F.to_usd(Decimal("100"), "CNY", self.table)
        back = usd * Decimal("6.64910834")
        self.assertTrue(abs(back - Decimal("100")) < Decimal("0.01"))


if __name__ == "__main__":
    unittest.main()
