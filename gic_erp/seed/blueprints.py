# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""One-click industry blueprints: starter masters for a new SME in a few minutes.

apply_industry_blueprint(company, blueprint_name) always creates the Pakistani tax
templates, then the masters for one industry. It is idempotent: anything that already
exists (same name) is left untouched and reported as "already there", so running it
twice is safe and never overwrites a client's own edits.

Rates and prices here are starter values for demos and onboarding. The client's
accountant should confirm tax rates, and the client should set real prices.
"""

import frappe
from frappe import _

FOUNDRY = "Foundry & Cookware"
MANDI = "Mandi & Wholesale Trader"
IMPORT_EXPORT = "Importer & Exporter"
SANITARY = "Sanitary Ware & Ceramics"
BLUEPRINTS = (FOUNDRY, MANDI, IMPORT_EXPORT, SANITARY)

# GIC Industry Profile business type -> the blueprint offered by default.
BUSINESS_TYPE_BLUEPRINT = {
	"Light Engineering & Foundry": FOUNDRY,
	"Wholesale & Mandi Trader": MANDI,
	"Importer & Exporter": IMPORT_EXPORT,
	"Sanitary Ware & Ceramics": SANITARY,
}

# (template title, account name, rate %). Withholding 236G / 236H are income tax the
# seller collects from distributors / retailers, added to the bill.
TAX_TEMPLATES = (
	("Pakistan GST 18%", "Sales Tax Payable (GST)", 18),
	("Withholding 236G (0.1%)", "Withholding Tax 236G", 0.1),
	("Withholding 236H (0.5%)", "Withholding Tax 236H", 0.5),
)

MANDI_CUSTOMER_GROUP = "Mandi Credit Customers"
MANDI_CREDIT_LIMIT = 500_000
IMPORT_CURRENCIES = ("USD", "AED", "CNY")
LANDED_COST_ACCOUNTS = ("Customs Duty", "Clearing Agent Fee", "Sea Freight")

RAW = "Raw Material"
PRODUCTS = "Products"


class Seeder:
	"""Creates records once and keeps a list of what it made and what was already there."""

	def __init__(self, company: str):
		self.company = company
		self.abbr = frappe.get_cached_value("Company", company, "abbr")
		self.created: list[str] = []
		self.existing: list[str] = []

	def note(self, label: str, made: bool):
		(self.created if made else self.existing).append(label)

	# ------------------------------------------------------------ accounts and taxes

	def account(self, account_name: str, parent: str, account_type: str, tax_rate: float = 0) -> str:
		name = frappe.db.get_value("Account", {"account_name": account_name, "company": self.company})
		if name:
			self.note(_("Account: {0}").format(name), False)
			return name
		doc = frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": account_name,
				"company": self.company,
				"parent_account": parent,
				"account_type": account_type,
				"tax_rate": tax_rate,
			}
		).insert(ignore_permissions=True)
		self.note(_("Account: {0}").format(doc.name), True)
		return doc.name

	def group_account(self, account_name: str, root_type: str) -> str:
		"""A group account by name, else the first group of that root type."""
		return frappe.db.get_value(
			"Account", {"company": self.company, "account_name": account_name, "is_group": 1}
		) or frappe.db.get_value(
			"Account",
			{"company": self.company, "root_type": root_type, "is_group": 1},
			order_by="lft desc",
		)

	def tax_templates(self):
		parent = self.group_account("Duties and Taxes", "Liability")
		for title, account_name, rate in TAX_TEMPLATES:
			account = self.account(account_name, parent, "Tax", rate)
			name = frappe.db.get_value(
				"Sales Taxes and Charges Template", {"title": title, "company": self.company}
			)
			if name:
				self.note(_("Tax Template: {0}").format(name), False)
				continue
			doc = frappe.get_doc(
				{
					"doctype": "Sales Taxes and Charges Template",
					"title": title,
					"company": self.company,
					"taxes": [
						{
							"charge_type": "On Net Total",
							"account_head": account,
							"description": title,
							"rate": rate,
						}
					],
				}
			).insert(ignore_permissions=True)
			self.note(_("Tax Template: {0}").format(doc.name), True)

	# ------------------------------------------------------------ items

	def item(self, code: str, group: str, stock_uom: str, valuation_rate: float, **extra) -> str:
		if frappe.db.exists("Item", code):
			self.note(_("Item: {0}").format(code), False)
			return code
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": group if frappe.db.exists("Item Group", group) else "All Item Groups",
				"stock_uom": stock_uom,
				"is_stock_item": 1,
				"valuation_rate": valuation_rate,
				**extra,
			}
		).insert(ignore_permissions=True)
		self.note(_("Item: {0}").format(code), True)
		return code

	def bom(self, item_code: str, materials: list[tuple[str, float]]):
		existing = frappe.db.get_value(
			"BOM", {"item": item_code, "company": self.company, "docstatus": 1, "is_active": 1}
		)
		if existing:
			self.note(_("BOM: {0}").format(existing), False)
			return
		doc = frappe.get_doc(
			{
				"doctype": "BOM",
				"item": item_code,
				"company": self.company,
				"quantity": 1,
				"is_default": 1,
				"rm_cost_as_per": "Valuation Rate",
				"items": [{"item_code": code, "qty": qty} for code, qty in materials],
			}
		).insert(ignore_permissions=True)
		doc.submit()
		self.note(_("BOM: {0}").format(doc.name), True)


# ---------------------------------------------------------------- blueprints


def foundry(s: Seeder):
	s.item("Aluminium Ingot", RAW, "Kg", 650)
	s.item("Brass Scrap", RAW, "Kg", 1500)
	s.item("SS Sheet", RAW, "Kg", 550)
	s.item("Non-Stick Karahi 28cm", PRODUCTS, "Nos", 2500, weight_per_unit=1.2, weight_uom="Kg")
	s.item("Pressure Cooker 5L", PRODUCTS, "Nos", 6000, weight_per_unit=2.5, weight_uom="Kg")
	# Sample: one karahi takes 1.2 Kg of aluminium (melt loss is tracked on the Stock Entry).
	s.bom("Non-Stick Karahi 28cm", [("Aluminium Ingot", 1.2)])


def mandi(s: Seeder):
	# Stocked in Kg; bought and sold in Mann (40 Kg) and Bori (50 Kg bag).
	s.item(
		"Super Kernel Basmati Rice",
		PRODUCTS,
		"Kg",
		380,
		sales_uom="Mann",
		purchase_uom="Bori",
		uoms=[
			{"uom": "Kg", "conversion_factor": 1},
			{"uom": "Mann", "conversion_factor": 40},
			{"uom": "Bori", "conversion_factor": 50},
		],
	)
	# Stocked per 1 L pouch; sold by the Petti (carton of 12).
	s.item(
		"Cooking Oil Carton",
		PRODUCTS,
		"Piece",
		550,
		sales_uom="Petti",
		uoms=[{"uom": "Piece", "conversion_factor": 1}, {"uom": "Petti", "conversion_factor": 12}],
	)
	customer_group_credit_limit(s)


def customer_group_credit_limit(s: Seeder):
	"""Mandi customers buy on credit: a default limit for the group, used for new customers."""
	if frappe.db.exists("Customer Group", MANDI_CUSTOMER_GROUP):
		group = frappe.get_doc("Customer Group", MANDI_CUSTOMER_GROUP)
		made = False
	else:
		group = frappe.get_doc(
			{
				"doctype": "Customer Group",
				"customer_group_name": MANDI_CUSTOMER_GROUP,
				"parent_customer_group": frappe.db.get_value("Customer Group", {"is_group": 1, "lft": 1})
				or "All Customer Groups",
				"is_group": 0,
			}
		)
		made = True
	if not any(row.company == s.company for row in group.credit_limits):
		group.append("credit_limits", {"company": s.company, "credit_limit": MANDI_CREDIT_LIMIT})
		made = True
	group.save(ignore_permissions=True)
	s.note(_("Customer Group: {0} (credit limit)").format(MANDI_CUSTOMER_GROUP), made)

	if frappe.db.get_single_value("Selling Settings", "customer_group") != MANDI_CUSTOMER_GROUP:
		frappe.db.set_single_value("Selling Settings", "customer_group", MANDI_CUSTOMER_GROUP)
		s.note(_("Selling Settings: default Customer Group"), True)


def import_export(s: Seeder):
	for currency in IMPORT_CURRENCIES:
		enabled = frappe.db.get_value("Currency", currency, "enabled")
		if not enabled:
			frappe.db.set_value("Currency", currency, "enabled", 1)
		s.note(_("Currency: {0}").format(currency), not enabled)

	valuation_account = frappe.get_cached_value("Company", s.company, "expenses_included_in_valuation")
	parent = (
		frappe.db.get_value("Account", valuation_account, "parent_account") if valuation_account else None
	) or s.group_account("Stock Expenses", "Expense")
	for name in LANDED_COST_ACCOUNTS:
		s.account(name, parent, "Expenses Included In Valuation")


def sanitary(s: Seeder):
	batch = {"has_batch_no": 1, "create_new_batch": 1}
	s.item("Ceramic Wash Basin - A Grade", PRODUCTS, "Nos", 4500, batch_number_series="CWB-A-.#####", **batch)
	s.item("Ceramic Wash Basin - B Grade", PRODUCTS, "Nos", 3200, batch_number_series="CWB-B-.#####", **batch)
	s.item("Brass Bib Cock", PRODUCTS, "Nos", 900, batch_number_series="BBC-.#####", **batch)


BUILDERS = {FOUNDRY: foundry, MANDI: mandi, IMPORT_EXPORT: import_export, SANITARY: sanitary}


@frappe.whitelist()
def apply_industry_blueprint(company: str, blueprint_name: str) -> dict:
	"""Seed tax templates plus one industry's masters for a company. Safe to run again."""
	# Explicit check: frappe.only_for() is skipped during tests, so it could not be tested.
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only a System Manager can load blueprint data."), frappe.PermissionError)
	if blueprint_name not in BUILDERS:
		frappe.throw(
			_("Blueprint must be one of: {0}").format(", ".join(BLUEPRINTS)), title=_("Unknown Blueprint")
		)
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} not found.").format(company or "-"), title=_("Unknown Company"))

	seeder = Seeder(company)
	seeder.tax_templates()
	BUILDERS[blueprint_name](seeder)
	return {
		"blueprint": blueprint_name,
		"company": company,
		"created": seeder.created,
		"already_there": seeder.existing,
	}
