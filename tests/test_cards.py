"""Unit tests for roi.cards (T04b-data, D-018/D-022).

The committed DeepSeek card must load with the exact verified rates,
both bases must be selectable, and every malformation must raise
CardError (an unparseable card never prices silently).
"""
import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from roi import cards as C
from roi import pricing as P


def _tmp_card(raw: dict) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    with f:
        json.dump(raw, f)
    return Path(f.name)


class LoadCardTest(unittest.TestCase):
    def setUp(self):
        self.card = C.load_card()  # default DeepSeek card, peak basis

    def test_default_peak_rates(self):
        s = self.card.snapshot
        flash = s.prices["deepseek-flash"]
        self.assertEqual(flash.input, Decimal("0.30"))
        self.assertEqual(flash.cache_read, Decimal("0.006"))
        self.assertEqual(flash.output, Decimal("1.20"))
        self.assertEqual(flash.cache_write, Decimal("0"))
        self.assertEqual(flash.reasoning, Decimal("0"))
        pro = s.prices["deepseek-v4-pro"]
        self.assertEqual(pro.input, Decimal("1.32"))
        self.assertEqual(pro.cache_read, Decimal("0.044"))
        self.assertEqual(pro.output, Decimal("3.96"))

    def test_offpeak_basis(self):
        card = C.load_card(basis="off_peak")
        flash = card.snapshot.prices["deepseek-flash"]
        self.assertEqual(flash.input, Decimal("0.15"))
        self.assertEqual(flash.cache_read, Decimal("0.003"))
        self.assertEqual(flash.output, Decimal("0.60"))
        self.assertEqual(card.basis, "off_peak")

    def test_metadata(self):
        self.assertEqual(self.card.default_model, "deepseek-flash")
        self.assertEqual(self.card.snapshot.currency, "USD")
        self.assertEqual(self.card.snapshot.as_of, date(2026, 11, 2))
        self.assertIn("api-docs.deepseek.com", self.card.source)
        self.assertEqual(
            set(self.card.snapshot.prices), {"deepseek-flash", "deepseek-v4-pro"})

    def test_snapshot_prices_end_to_end(self):
        # 1M of each priced bucket at peak flash = 0.30 + 1.20 + 0.006 = 1.506
        bd = P.price_model_usage(
            [("deepseek-flash", {
                "input": 1_000_000, "output": 1_000_000, "cache_read": 1_000_000})],
            self.card.snapshot)
        self.assertEqual(bd.priced, Decimal("1.506000"))
        self.assertEqual(bd.coverage, 1.0)

    def test_unknown_model_stays_unknown(self):
        # Unknown models contribute NOTHING to priced; their tokens are
        # carried in unknown_tokens so the gap stays auditable (coverage),
        # never a silent 0.0 hiding in the total.
        bd = P.price_model_usage([("no-such-model", {"input": 100})], self.card.snapshot)
        self.assertEqual(bd.priced, Decimal("0"))
        self.assertIn("no-such-model", bd.unknown_models)
        self.assertEqual(bd.unknown_tokens.get("input"), 100)


class CardErrorTest(unittest.TestCase):
    def test_bad_basis(self):
        with self.assertRaises(C.CardError):
            C.load_card(basis="midday")

    def test_missing_file(self):
        with self.assertRaises(C.CardError):
            C.load_card(Path("/nonexistent/hermes-roi-card.json"))

    def test_not_json(self):
        p = _tmp_card({})  # write then clobber
        p.write_text("not json {")
        with self.assertRaises(C.CardError):
            C.load_card(p)

    def _raw(self) -> dict:
        return json.loads(C.DEFAULT_CARD_PATH.read_text(encoding="utf-8"))

    def test_missing_models(self):
        raw = self._raw(); del raw["models"]
        with self.assertRaises(C.CardError):
            C.load_card(_tmp_card(raw))

    def test_missing_bucket(self):
        raw = self._raw(); del raw["models"]["deepseek-flash"]["output"]
        with self.assertRaises(C.CardError):
            C.load_card(_tmp_card(raw))

    def test_float_rate_refused(self):
        raw = self._raw()
        raw["models"]["deepseek-flash"]["output"] = {"peak": 0.3, "off_peak": "0.15"}
        with self.assertRaises(C.CardError):
            C.load_card(_tmp_card(raw))

    def test_negative_rate_refused(self):
        raw = self._raw()
        raw["models"]["deepseek-v4-pro"]["input"]["peak"] = "-1.00"
        with self.assertRaises(C.CardError):
            C.load_card(_tmp_card(raw))

    def test_bad_default_model(self):
        raw = self._raw()
        raw["default_benchmark_model"] = "ghost-model"
        with self.assertRaises(C.CardError):
            C.load_card(_tmp_card(raw))

    def test_bad_as_of(self):
        raw = self._raw()
        raw["as_of"] = "Nov 2 2026"
        with self.assertRaises(C.CardError):
            C.load_card(_tmp_card(raw))


if __name__ == "__main__":
    unittest.main()
