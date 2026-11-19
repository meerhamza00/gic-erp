# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from gic_erp.billing.kacha_pakka import KACHA_PRINT_FORMAT, NOT_KACHA, PAKKA_ONLY_FIELDS
from gic_erp.setup.custom_fields import KACHA, PAKKA
from gic_erp.tests.utils import PREFIX, abbr, company, make_customer, make_item

test_ignore = ["Company", "Customer", "Item", "Sales Taxes and Charges Template", "Account"]

ITEM = f"{PREFIX} Service Item"


def tax_template() -> str:
	"""An 18% GST template on a test tax account, created once."""
	account = f"{PREFIX} GST - {abbr()}"
	if not frappe.db.exists("Account", account):
		parent = frappe.db.get_value(
			"Account", {"company": company(), "account_name": "Duties and Taxes", "is_group": 1}
		) or frappe.db.get_value("Account", {"company": company(), "root_type": "Liability", "is_group": 1})
		frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": f"{PREFIX} GST",
				"company": company(),
				"parent_account": parent,
				"account_type": "Tax",
				"tax_rate": 18,
			}
		).insert(ignore_permissions=True)
	title = f"{PREFIX} GST 18%"
	name = frappe.db.get_value("Sales Taxes and Charges Template", {"title": title, "company": company()})
	if not name:
		name = (
			frappe.get_doc(
				{
					"doctype": "Sales Taxes and Charges Template",
					"title": title,
					"company": company(),
					"taxes": [
						{
							"charge_type": "On Net Total",
							"account_head": account,
							"description": "GST 18%",
							"rate": 18,
						}
					],
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
	return name


def make_invoice(mode=PAKKA, taxes_and_charges=None, qty=10, rate=100, submit=False, **kw):
	doc = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": make_customer(),
			"company": company(),
			"gic_bill_mode": mode,
			"taxes_and_charges": taxes_and_charges,
			"items": [{"item_code": ITEM, "qty": qty, "rate": rate}],
			**kw,
		}
	)
	doc.set_missing_values()
	if taxes_and_charges:
		doc.set_taxes()
	doc.insert()
	if submit:
		doc.submit()
	return doc


class TestKachaPakka(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_item(ITEM, is_stock_item=0)
		frappe.db.set_single_value("GIC Industry Profile", "enable_kacha_pakka_mode", 1)

	def test_pakka_keeps_taxes(self):
		doc = make_invoice(PAKKA, tax_template())
		self.assertEqual(len(doc.taxes), 1)
		self.assertEqual(flt(doc.grand_total), 1180)

	def test_kacha_clears_taxes_on_the_server(self):
		doc = make_invoice(KACHA, tax_template())
		self.assertEqual(doc.taxes, [])
		self.assertFalse(doc.taxes_and_charges)
		self.assertEqual(flt(doc.grand_total), 1000)

	def test_kacha_ignores_a_default_tax_template(self):
		template = tax_template()
		frappe.db.set_value("Sales Taxes and Charges Template", template, "is_default", 1)
		try:
			doc = make_invoice(KACHA)
			self.assertEqual(doc.taxes, [])
			self.assertEqual(flt(doc.grand_total), 1000)
		finally:
			frappe.db.set_value("Sales Taxes and Charges Template", template, "is_default", 0)

	def test_blank_mode_defaults_to_pakka(self):
		doc = make_invoice(mode=None)
		self.assertEqual(doc.gic_bill_mode, PAKKA)

	def test_kacha_blocked_when_switched_off(self):
		frappe.db.set_single_value("GIC Industry Profile", "enable_kacha_pakka_mode", 0)
		try:
			self.assertRaises(frappe.ValidationError, make_invoice, KACHA)
		finally:
			frappe.db.set_single_value("GIC Industry Profile", "enable_kacha_pakka_mode", 1)

	def test_kacha_invoice_still_posts_to_the_ledger(self):
		doc = make_invoice(KACHA, submit=True)
		self.assertTrue(frappe.db.exists("GL Entry", {"voucher_no": doc.name, "is_cancelled": 0}))

	def test_tax_fields_hidden_only_on_kacha(self):
		meta = frappe.get_meta("Sales Invoice")
		for fieldname in PAKKA_ONLY_FIELDS:
			self.assertEqual(meta.get_field(fieldname).depends_on, NOT_KACHA, fieldname)

	def test_kacha_slip_prints_memo_without_tax_headers(self):
		doc = make_invoice(KACHA, submit=True)
		html = frappe.get_print("Sales Invoice", doc.name, print_format=KACHA_PRINT_FORMAT, no_letterhead=1)
		self.assertIn("ESTIMATE / DELIVERY MEMO", html)
		self.assertIn(doc.name, html)
		for word in ("NTN", "GST", "Sales Tax Invoice", "STRN"):
			self.assertNotIn(word, html)
