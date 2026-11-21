"""Unit tests for roi.energy (T04b-data, D-020).

energy = unit price x usage (exact Decimal); net = gross - energy with
an empty setting meaning "not modeled" (net == gross); negative net is
an honest result, not an error.
"""
import unittest
from decimal import Decimal

from roi import energy as E


class EnergyCostTest(unittest.TestCase):
    def test_basic(self):
        # e.g. 0.60 CNY/kWh x 10 kWh = 6.00
        self.assertEqual(
            E.energy_cost(Decimal("0.60"), Decimal("10")), Decimal("6.000000"))

    def test_fractional(self):
        self.assertEqual(
            E.energy_cost(Decimal("0.123456"), Decimal("0.5")),
            Decimal("0.061728"))

    def test_string_inputs(self):
        self.assertEqual(
            E.energy_cost("1.5", "4"), Decimal("6.000000"))

    def test_float_refused(self):
        with self.assertRaises(E.EnergyError):
            E.energy_cost(0.6, Decimal("10"))
        with self.assertRaises(E.EnergyError):
            E.energy_cost(Decimal("0.6"), 10.0)

    def test_negative_refused(self):
        with self.assertRaises(E.EnergyError):
            E.energy_cost(Decimal("-0.6"), Decimal("10"))
        with self.assertRaises(E.EnergyError):
            E.energy_cost(Decimal("0.6"), Decimal("-10"))


class NetSavingsTest(unittest.TestCase):
    def test_empty_setting_means_gross(self):
        self.assertEqual(
            E.net_savings(Decimal("100.123456")), Decimal("100.123456"))

    def test_subtracts_energy(self):
        self.assertEqual(
            E.net_savings(Decimal("100"), Decimal("6.000000")),
            Decimal("94.000000"))

    def test_negative_net_is_allowed(self):
        # energy > gross is honest (verdict layer: no positive trajectory)
        self.assertEqual(
            E.net_savings(Decimal("5"), Decimal("6.000000")),
            Decimal("-1.000000"))

    def test_float_refused(self):
        with self.assertRaises(E.EnergyError):
            E.net_savings(100.0)

    def test_string_inputs(self):
        self.assertEqual(
            E.net_savings("10", "2.5"), Decimal("7.500000"))


if __name__ == "__main__":
    unittest.main()
