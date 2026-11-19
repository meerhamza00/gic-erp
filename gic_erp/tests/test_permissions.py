# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""Milestone 3: least-privilege GIC roles, tested with real users doing real work."""

import frappe
from frappe.tests.utils import FrappeTestCase

from gic_erp.setup.permissions import apply_gic_permissions
from gic_erp.tests.utils import PREFIX, company, make_customer, make_item, make_user, warehouse

MUNSHI = "gic-munshi-perm@example.com"
OWNER = "gic-owner-perm@example.com"
ACCOUNTS_USER = "gic-accounts-perm@example.com"
SERVICE = f"{PREFIX} Casting Service"
STOCK_ITEM = f"{PREFIX} Brass Scrap"


def _sales_invoice(rate=1000):
	return frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": make_customer(),
			"company": company(),
			"items": [{"item_code": SERVICE, "qty": 2, "rate": rate}],
		}
	).insert()


class TestGICPermissions(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_item(SERVICE, is_stock_item=0)
		make_item(STOCK_ITEM, stock_uom="Kg")
		make_customer()
		make_user(MUNSHI, "GIC Munshi User")
		make_user(OWNER, "GIC Factory Owner")
		make_user(ACCOUNTS_USER, "Accounts User")

	def tearDown(self):
		frappe.set_user("Administrator")

	# --- munshi: can do the daily work -------------------------------------------------

	def test_munshi_creates_and_submits_sales_invoice(self):
		frappe.set_user(MUNSHI)
		si = _sales_invoice()
		si.submit()
		self.assertEqual(si.docstatus, 1)
		self.assertEqual(si.grand_total, 2000)

	def test_munshi_receives_payment_against_invoice(self):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		frappe.set_user(MUNSHI)
		si = _sales_invoice()
		si.submit()
		pe = get_payment_entry("Sales Invoice", si.name)
		pe.reference_no = "CASH"
		pe.reference_date = frappe.utils.today()
		pe.insert()
		pe.submit()
		self.assertEqual(pe.docstatus, 1)
		self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount"), 0)

	def test_munshi_creates_and_submits_stock_entry(self):
		frappe.set_user(MUNSHI)
		se = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": company(),
				"items": [
					{"item_code": STOCK_ITEM, "qty": 40, "basic_rate": 900, "t_warehouse": warehouse()}
				],
			}
		).insert()
		se.submit()
		self.assertEqual(se.docstatus, 1)

	def test_munshi_creates_quotation_and_customer(self):
		frappe.set_user(MUNSHI)
		self.assertTrue(frappe.has_permission("Customer", "create"))
		qtn = frappe.get_doc(
			{
				"doctype": "Quotation",
				"party_name": make_customer(),
				"company": company(),
				"items": [{"item_code": SERVICE, "qty": 1, "rate": 500}],
			}
		).insert()
		self.assertEqual(qtn.docstatus, 0)

	def test_munshi_can_open_party_khata(self):
		frappe.set_user(MUNSHI)
		self.assertTrue(frappe.get_doc("Report", "General Ledger").is_permitted())

	# --- munshi: cannot do owner things ------------------------------------------------

	def test_munshi_cannot_cancel_or_delete_invoices(self):
		frappe.set_user(MUNSHI)
		si = _sales_invoice()
		si.submit()
		self.assertFalse(frappe.has_permission("Sales Invoice", "cancel", si))
		self.assertFalse(frappe.has_permission("Sales Invoice", "delete"))
		self.assertRaises(frappe.PermissionError, si.cancel)

	def test_munshi_has_no_purchase_invoice_or_settings_access(self):
		frappe.set_user(MUNSHI)
		self.assertFalse(frappe.has_permission("Purchase Invoice", "read"))
		self.assertFalse(frappe.has_permission("GIC Industry Profile", "write"))
		self.assertFalse(frappe.has_permission("Item", "create"))

	# --- owner -------------------------------------------------------------------------

	def test_owner_can_cancel_invoice(self):
		frappe.set_user(OWNER)
		si = _sales_invoice()
		si.submit()
		si.cancel()
		self.assertEqual(si.docstatus, 2)

	def test_owner_can_manage_purchase_invoices_and_items(self):
		frappe.set_user(OWNER)
		self.assertTrue(frappe.has_permission("Purchase Invoice", "submit"))
		self.assertTrue(frappe.has_permission("Item", "create"))

	# --- nobody else loses access (the Custom DocPerm trap) ---------------------------

	def test_standard_roles_keep_their_access(self):
		apply_gic_permissions()
		frappe.set_user(ACCOUNTS_USER)
		for doctype in ("Sales Invoice", "Payment Entry", "Purchase Invoice", "Customer"):
			self.assertTrue(frappe.has_permission(doctype, "read"), doctype)
		self.assertTrue(frappe.has_permission("Sales Invoice", "submit"))

	def test_apply_is_idempotent(self):
		apply_gic_permissions()
		apply_gic_permissions()
		self.assertEqual(
			frappe.db.count(
				"Custom DocPerm", {"parent": "Sales Invoice", "role": "GIC Munshi User", "permlevel": 0}
			),
			1,
		)
		self.assertEqual(frappe.db.count("Custom Role", {"report": "General Ledger"}), 1)
