# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from gic_erp.seed import blueprints
from gic_erp.seed.blueprints import apply_industry_blueprint
from gic_erp.tests.utils import abbr, company, make_user

test_ignore = ["Company", "Customer", "Item", "Account", "BOM", "Customer Group"]


class TestIndustryBlueprints(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.default_group = frappe.db.get_single_value("Selling Settings", "customer_group")

	@classmethod
	def tearDownClass(cls):
		frappe.db.set_single_value("Selling Settings", "customer_group", cls.default_group)
		super().tearDownClass()

	def apply_twice(self, blueprint: str) -> dict:
		first = apply_industry_blueprint(company(), blueprint)
		second = apply_industry_blueprint(company(), blueprint)
		self.assertEqual(second["created"], [], f"{blueprint} is not idempotent")
		return first

	def assert_tax_templates(self):
		for title, _account, rate in blueprints.TAX_TEMPLATES:
			name = frappe.db.get_value(
				"Sales Taxes and Charges Template", {"title": title, "company": company()}
			)
			self.assertTrue(name, title)
			self.assertEqual(frappe.get_doc("Sales Taxes and Charges Template", name).taxes[0].rate, rate)

	def test_foundry(self):
		self.apply_twice(blueprints.FOUNDRY)
		self.assert_tax_templates()
		for item in (
			"Aluminium Ingot",
			"Brass Scrap",
			"SS Sheet",
			"Non-Stick Karahi 28cm",
			"Pressure Cooker 5L",
		):
			self.assertTrue(frappe.db.exists("Item", item), item)
		bom = frappe.db.get_value(
			"BOM", {"item": "Non-Stick Karahi 28cm", "company": company(), "docstatus": 1}, "name"
		)
		self.assertTrue(bom)
		self.assertEqual(frappe.get_doc("BOM", bom).items[0].item_code, "Aluminium Ingot")

	def test_mandi(self):
		self.apply_twice(blueprints.MANDI)
		factors = {
			row.uom: row.conversion_factor for row in frappe.get_doc("Item", "Super Kernel Basmati Rice").uoms
		}
		self.assertEqual(factors.get("Mann"), 40)
		self.assertEqual(factors.get("Bori"), 50)
		self.assertTrue(frappe.db.exists("Item", "Cooking Oil Carton"))
		limits = frappe.get_doc("Customer Group", blueprints.MANDI_CUSTOMER_GROUP).credit_limits
		self.assertEqual(
			[(r.company, r.credit_limit) for r in limits], [(company(), blueprints.MANDI_CREDIT_LIMIT)]
		)
		self.assertEqual(
			frappe.db.get_single_value("Selling Settings", "customer_group"), blueprints.MANDI_CUSTOMER_GROUP
		)

	def test_importer_exporter(self):
		self.apply_twice(blueprints.IMPORT_EXPORT)
		for currency in blueprints.IMPORT_CURRENCIES:
			self.assertEqual(frappe.db.get_value("Currency", currency, "enabled"), 1, currency)
		for name in blueprints.LANDED_COST_ACCOUNTS:
			self.assertEqual(
				frappe.db.get_value("Account", f"{name} - {abbr()}", "account_type"),
				"Expenses Included In Valuation",
				name,
			)

	def test_sanitary(self):
		self.apply_twice(blueprints.SANITARY)
		for item in ("Ceramic Wash Basin - A Grade", "Ceramic Wash Basin - B Grade", "Brass Bib Cock"):
			self.assertEqual(frappe.db.get_value("Item", item, "has_batch_no"), 1, item)

	def test_rejects_unknown_blueprint_or_company(self):
		self.assertRaises(frappe.ValidationError, apply_industry_blueprint, company(), "Steel Mill")
		self.assertRaises(frappe.ValidationError, apply_industry_blueprint, "No Such Co", blueprints.FOUNDRY)

	def test_only_system_manager(self):
		user = make_user("gic.munshi.blueprint@example.com", "GIC Munshi User")
		frappe.set_user(user)
		try:
			self.assertRaises(frappe.PermissionError, apply_industry_blueprint, company(), blueprints.FOUNDRY)
		finally:
			frappe.set_user("Administrator")
