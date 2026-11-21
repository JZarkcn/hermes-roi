"""Tests for roi.pricing (T04 acceptance).

Covers: exact Decimal cost math (per-million division only at the end),
ROUND_HALF_UP quantize pins, the 5 disjoint buckets (cache-heavy mix),
unknown-model handling (UnknownPrice marker + coverage, never a silent 0.0),
per-model aggregation, and malformed-input rejection.

Run:  python3 tests/test_pricing.py
"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from roi import pricing as pr  # noqa: E402

D = Decimal


def make_snapshot() -> pr.PriceSnapshot:
    """Deterministic two-model rate card, USD, snapshot date fixed."""
    return pr.PriceSnapshot(
        currency="USD",
        as_of=date(2026, 11, 2),
        prices={
            "m-local": pr.BucketPrices(
                input=D("3.00"), output=D("15.00"),
                cache_read=D("0.30"), cache_write=D("3.75"),
                reasoning=D("0"),
            ),
            "m-cache": pr.BucketPrices(
                input=D("1.00"), output=D("4.00"),
                cache_read=D("0.10"), cache_write=D("1.25"),
            ),
        },
    )


class ComputeCostTest(unittest.TestCase):
    def test_basic_exact(self):
        # 1.5M input @1.00 + 2.5M output @4.00 + 3M cache_read @0.10
        # + 1M cache_write @1.25 + 0.5M reasoning @0 = 1.50+10.00+0.30+1.25
        cost = pr.compute_cost(
            {"input": 1_500_000, "output": 2_500_000,
             "cache_read": 3_000_000, "cache_write": 1_000_000,
             "reasoning": 500_000},
            make_snapshot().prices["m-cache"],
        )
        self.assertEqual(cost, D("13.050000"))
        self.assertIsInstance(cost, Decimal)

    def test_per_million_division_only_at_end(self):
        # 500k tokens @ 0.000002/1M → 500000×0.000002 = 1.0 (exact) → /1e6
        # → 0.000001. No intermediate float, no intermediate division.
        cost = pr.compute_cost({"input": 500_000},
                               pr.BucketPrices(input=D("0.000002"), output=D("0"),
                                               cache_read=D("0"), cache_write=D("0"),
                                               reasoning=D("0")))
        self.assertEqual(cost, D("0.000001"))

    def test_round_half_up_pin(self):
        # 1 token @ 0.5/1M → 0.5/1e6 = exactly 0.0000005 → the half unit.
        # ROUND_HALF_UP (documented) gives 0.000001; HALF_EVEN would give 0.
        cost = pr.compute_cost({"input": 1},
                               pr.BucketPrices(input=D("0.5"), output=D("0"),
                                               cache_read=D("0"), cache_write=D("0"),
                                               reasoning=D("0")))
        self.assertEqual(cost, D("0.000001"))

    def test_missing_bucket_keys_default_zero(self):
        cost = pr.compute_cost({"input": 1_000_000}, make_snapshot().prices["m-cache"])
        self.assertEqual(cost, D("1.000000"))

    def test_unknown_bucket_raises(self):
        with self.assertRaises(pr.PricingError):
            pr.compute_cost({"inp": 10}, make_snapshot().prices["m-cache"])

    def test_negative_tokens_raise(self):
        with self.assertRaises(pr.PricingError):
            pr.compute_cost({"input": -1}, make_snapshot().prices["m-cache"])

    def test_bool_tokens_raise(self):
        with self.assertRaises(pr.PricingError):
            pr.compute_cost({"input": True}, make_snapshot().prices["m-cache"])

    def test_float_price_refused(self):
        with self.assertRaises(pr.PricingError):
            pr.compute_cost({"input": 1},
                            pr.BucketPrices(input=0.5, output=D("0"),  # type: ignore[arg-type]
                                            cache_read=D("0"), cache_write=D("0"),
                                            reasoning=D("0")))


class DisjointBucketsTest(unittest.TestCase):
    """The 5 buckets are disjoint source columns (DATA_CONTRACT §3): each is
    multiplied by exactly one rate, so the sum cannot double-count."""

    def test_cache_heavy_mix_prices_each_bucket_at_its_own_rate(self):
        # cache_read dominates volume at 0.30/1M vs input 3.00/1M:
        # (100×3 + 400×15 + 5_000_000×0.30 + 0 + 1000×0)/1e6
        # = (300 + 6000 + 1_500_000)/1e6 = 1.5063
        cost = pr.compute_cost(
            {"input": 100, "output": 400, "cache_read": 5_000_000,
             "cache_write": 0, "reasoning": 1000},
            make_snapshot().prices["m-local"],
        )
        self.assertEqual(cost, D("1.506300"))

    def test_cache_heavy_mix_not_equal_single_rate(self):
        # Naive "everything at the input rate" would give 15.012 — the
        # per-bucket rule must not reduce to that.
        price = make_snapshot().prices["m-local"]
        cost = pr.compute_cost(
            {"input": 100, "output": 400, "cache_read": 5_000_000,
             "cache_write": 0, "reasoning": 1000}, price)
        naive = D(100 + 400 + 5_000_000 + 0 + 1000) * price.input / D(1_000_000)
        self.assertNotEqual(cost, naive)

    def test_reasoning_not_double_billed_by_default(self):
        # reasoning @ 0 adds nothing; output is billed once, and the
        # reasoning subset inside it is not charged a second time.
        price = make_snapshot().prices["m-local"]
        with_r = pr.compute_cost({"output": 1_000_000, "reasoning": 1_000_000}, price)
        without_r = pr.compute_cost({"output": 1_000_000}, price)
        self.assertEqual(with_r, without_r)
        self.assertEqual(with_r, D("15.000000"))


class PriceModelUsageTest(unittest.TestCase):
    def setUp(self):
        self.snap = make_snapshot()

    def test_price_for_known_and_unknown(self):
        p = self.snap.price_for("m-local")
        self.assertIsInstance(p, pr.BucketPrices)
        u = self.snap.price_for("ghost-model")
        self.assertIs(u, pr.UnknownPrice())
        self.assertEqual(repr(u), "UnknownPrice")

    def test_unknown_model_never_silent_zero(self):
        rows = [
            ("m-local", {"input": 1_000_000}),
            ("ghost", {"input": 9_000_000, "output": 1_000_000}),
        ]
        bd = pr.price_model_usage(rows, self.snap)
        # priced = m-local only: 1M × 3.00 / 1e6 = 3.00 — ghost contributes
        # nothing to the total but is fully accounted for in coverage.
        self.assertEqual(bd.priced, D("3.000000"))
        self.assertEqual(bd.unknown_models, ("ghost",))
        self.assertEqual(bd.unknown_tokens["input"], 9_000_000)
        self.assertEqual(bd.unknown_tokens["output"], 1_000_000)
        self.assertEqual(bd.total_tokens, 11_000_000)
        self.assertEqual(bd.priced_tokens, 1_000_000)
        self.assertEqual(bd.coverage, D(1) / D(11))

    def test_all_unknown_rows(self):
        bd = pr.price_model_usage([("ghost", {"input": 100, "output": 50})],
                                  self.snap)
        self.assertEqual(bd.priced, D("0.000000"))
        self.assertEqual(bd.unknown_models, ("ghost",))
        self.assertEqual(bd.coverage, D(0))
        self.assertEqual(bd.per_model, {})

    def test_per_model_aggregates_multiple_rows(self):
        rows = [
            ("m-local", {"input": 500_000}),
            ("m-local", {"input": 500_000, "output": 1_000_000}),
        ]
        bd = pr.price_model_usage(rows, self.snap)
        # (500k×3 + 500k×3 + 1M×15)/1e6 = 18.00
        self.assertEqual(bd.per_model["m-local"], D("18.000000"))
        self.assertEqual(bd.priced, D("18.000000"))
        # sum(per_model) == priced (no hidden remainder)
        self.assertEqual(sum(bd.per_model.values(), D("0")), bd.priced)

    def test_empty_rows(self):
        bd = pr.price_model_usage([], self.snap)
        self.assertEqual(bd.priced, D("0.000000"))
        self.assertIsNone(bd.coverage)
        self.assertEqual(bd.total_tokens, 0)

    def test_currency_and_date_ride_along(self):
        bd = pr.price_model_usage([("m-local", {"input": 1})], self.snap)
        self.assertEqual(bd.currency, "USD")
        self.assertEqual(bd.as_of, date(2026, 11, 2))

    def test_malformed_row_raises(self):
        with self.assertRaises(pr.PricingError):
            pr.price_model_usage([("m-local", {"bogus": 3})], self.snap)


if __name__ == "__main__":
    unittest.main()
