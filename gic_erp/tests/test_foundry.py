# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""Milestone 3: foundry burning loss on Stock Entry."""

import frappe
from frappe.tests.utils import FrappeTestCase

from gic_erp.manufacturing.foundry import BURNING_LOSS_ALERT_PCT, validate_burning_loss
from gic_erp.tests.utils import PREFIX, company, make_item, warehouse

INGOT = f"{PREFIX} Aluminium Ingot"  # stocked in Kg
KARAHI = f"{PREFIX} Karahi 28cm"  # pieces, 1.2 Kg each
NO_WEIGHT = f"{PREFIX} Unweighed Part"  # pieces, no weight set


def _melt(rows, gross, scrap=0.0, finished_weight=0.0):
	doc = frappe.new_doc("Stock Entry")
	doc.company = company()
	doc.gic_is_foundry_melt = 1
	doc.gic_gross_metal_weight = gross
	doc.gic_scrap_recovered = scrap
	doc.gic_finished_weight = finished_weight
	for item_code, qty, uom in rows:
		doc.append(
			"items",
			{
				"item_code": item_code,
				"qty": qty,
				"transfer_qty": qty,
				"conversion_factor": 1,
				"stock_uom": uom,
				"t_warehouse": warehouse("Finished Goods"),
			},
		)
	return doc


def _messages() -> str:
	return " ".join(str(m) for m in frappe.local.message_log)


class TestFoundryBurningLoss(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_item(INGOT, stock_uom="Kg")
		make_item(KARAHI, stock_uom="Nos", weight_per_unit=1.2, weight_uom="Kg")
		make_item(NO_WEIGHT, stock_uom="Nos")

	def setUp(self):
		frappe.local.message_log = []

	def test_loss_from_kg_items(self):
		doc = _melt([(INGOT, 96, "Kg")], gross=100, scrap=1)
		validate_burning_loss(doc)
		self.assertEqual(doc.gic_finished_weight, 96)
		self.assertEqual(doc.gic_burning_loss_qty, 3)
		self.assertEqual(doc.gic_burning_loss_pct, 3)
		self.assertNotIn("High burning loss", _messages())

	def test_loss_from_piece_items_uses_weight_per_unit(self):
		doc = _melt([(KARAHI, 10, "Nos")], gross=15, scrap=1)  # 10 x 1.2 = 12 Kg
		validate_burning_loss(doc)
		self.assertAlmostEqual(doc.gic_finished_weight, 12)
		self.assertAlmostEqual(doc.gic_burning_loss_qty, 2)
		self.assertAlmostEqual(doc.gic_burning_loss_pct, 13.33)

	def test_high_loss_alerts_without_blocking(self):
		doc = _melt([(KARAHI, 10, "Nos")], gross=15, scrap=1)
		validate_burning_loss(doc)  # must not raise
		self.assertGreater(doc.gic_burning_loss_pct, BURNING_LOSS_ALERT_PCT)
		self.assertIn("High burning loss", _messages())

	def test_unknown_weight_skips_calculation_and_asks(self):
		doc = _melt([(NO_WEIGHT, 5, "Nos")], gross=10)
		validate_burning_loss(doc)
		self.assertEqual(doc.gic_burning_loss_qty, 0)
		self.assertIn("Finished Goods Weight", _messages())

	def test_manual_finished_weight_is_used_when_unknown(self):
		doc = _melt([(NO_WEIGHT, 5, "Nos")], gross=10, finished_weight=9)
		validate_burning_loss(doc)
		self.assertEqual(doc.gic_burning_loss_qty, 1)
		self.assertEqual(doc.gic_burning_loss_pct, 10)

	def test_output_more_than_input_is_rejected(self):
		doc = _melt([(INGOT, 99, "Kg")], gross=100, scrap=5)
		self.assertRaises(frappe.ValidationError, validate_burning_loss, doc)

	def test_missing_gross_weight_is_rejected(self):
		doc = _melt([(INGOT, 10, "Kg")], gross=0)
		self.assertRaises(frappe.ValidationError, validate_burning_loss, doc)

	def test_non_melt_entry_is_untouched(self):
		doc = _melt([(INGOT, 10, "Kg")], gross=0)
		doc.gic_is_foundry_melt = 0
		validate_burning_loss(doc)
		self.assertEqual(doc.gic_burning_loss_qty, 0)

	def test_hook_runs_on_real_stock_entry_save(self):
		doc = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": company(),
				"gic_is_foundry_melt": 1,
				"gic_gross_metal_weight": 15,
				"gic_scrap_recovered": 1,
				"items": [
					{
						"item_code": KARAHI,
						"qty": 10,
						"basic_rate": 500,
						"t_warehouse": warehouse("Finished Goods"),
					}
				],
			}
		).insert()
		self.assertAlmostEqual(doc.gic_burning_loss_qty, 2)
		self.assertAlmostEqual(doc.gic_burning_loss_pct, 13.33)
