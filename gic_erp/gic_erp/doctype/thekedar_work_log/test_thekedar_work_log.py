# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from gic_erp.gic_erp.doctype.thekedar_work_log.thekedar_work_log import LABOR_ITEM
from gic_erp.tests.utils import PREFIX, company, make_item, make_supplier, make_user

# Our tests build their own data. Without this, the Frappe test runner auto-creates (and
# commits) ERPNext's whole _Test fixture chain for every linked doctype.
test_ignore = ["Company", "Supplier", "Item", "UOM", "Work Order", "Purchase Invoice"]

KARAHI = f"{PREFIX} Karahi 28cm"
MUNSHI = "gic-munshi-thekedar@example.com"


def _log(qty=100, rate=12.5, submit=True):
	doc = frappe.get_doc(
		{
			"doctype": "Thekedar Work Log",
			"contractor": make_supplier(),
			"company": company(),
			"item_produced": KARAHI,
			"operation_type": "Polishing",
			"quantity_completed": qty,
			"uom": "Piece",
			"rate_per_unit": rate,
		}
	).insert()
	if submit:
		doc.submit()
	return doc


class TestThekedarWorkLog(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_item(KARAHI, stock_uom="Nos", weight_per_unit=1.2, weight_uom="Kg")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_total_payable_is_qty_times_rate(self):
		doc = _log(qty=100, rate=12.5, submit=False)
		self.assertEqual(doc.total_payable, 1250)

	def test_submit_creates_linked_draft_purchase_invoice(self):
		doc = _log(qty=100, rate=12.5)
		self.assertTrue(doc.purchase_invoice)
		pi = frappe.get_doc("Purchase Invoice", doc.purchase_invoice)
		self.assertEqual(pi.docstatus, 0)
		self.assertEqual(pi.supplier, doc.contractor)
		self.assertEqual(pi.company, doc.company)
		self.assertEqual(len(pi.items), 1)
		self.assertEqual(pi.items[0].item_code, LABOR_ITEM)
		self.assertEqual(pi.grand_total, 1250)
		self.assertIn(doc.name, pi.items[0].description)

	def test_labor_item_is_a_non_stock_service(self):
		_log()
		self.assertEqual(frappe.db.get_value("Item", LABOR_ITEM, "is_stock_item"), 0)

	def test_zero_quantity_or_rate_rejected(self):
		self.assertRaises(frappe.ValidationError, _log, qty=0, submit=False)
		self.assertRaises(frappe.ValidationError, _log, rate=0, submit=False)

	def test_cancel_deletes_draft_invoice(self):
		doc = _log()
		invoice = doc.purchase_invoice
		doc.cancel()
		self.assertFalse(frappe.db.exists("Purchase Invoice", invoice))
		self.assertIsNone(frappe.db.get_value("Thekedar Work Log", doc.name, "purchase_invoice"))

	def test_cancel_blocked_once_invoice_submitted(self):
		doc = _log()
		frappe.get_doc("Purchase Invoice", doc.purchase_invoice).submit()
		doc.reload()
		self.assertRaises(frappe.ValidationError, doc.cancel)

	def test_munshi_can_submit_without_purchase_invoice_rights(self):
		make_user(MUNSHI, "GIC Munshi User")
		frappe.set_user(MUNSHI)
		self.assertFalse(frappe.has_permission("Purchase Invoice", "create"))
		doc = _log(qty=10, rate=50)
		self.assertTrue(doc.purchase_invoice)
		self.assertEqual(frappe.db.get_value("Purchase Invoice", doc.purchase_invoice, "grand_total"), 500)
