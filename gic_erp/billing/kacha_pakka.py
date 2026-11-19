# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""Kacha / Pakka billing on Sales Invoice.

Pakka (Tax Invoice): the normal ERPNext invoice with taxes.
Kacha (Estimate Slip): an estimate / delivery memo with no sales tax lines. It is still a
real Sales Invoice: it posts to the ledger, updates stock and the customer's khata, and
shows in every report (filter by Bill Type). Whether sales tax applies to a sale is the
business's and its accountant's call; this only controls what is charged and printed.

Taxes are cleared on the server (before_validate), not just in the browser, so imports,
the API and old browser tabs follow the same rule.
"""

import frappe
from frappe import _

from gic_erp.setup.custom_fields import KACHA, MODULE, PAKKA

PROFILE = "GIC Industry Profile"
NOT_KACHA = f"eval:doc.gic_bill_mode!='{KACHA}'"

# Sales Invoice fields shown only on Pakka bills. depends_on Property Setters, so the
# standard fields themselves are untouched.
PAKKA_ONLY_FIELDS = (
	"taxes_section",  # tax template, tax category (also shipping rule, incoterm)
	"section_break_40",  # taxes table
	"section_break_43",  # total taxes
	"sec_tax_breakup",
	"tax_id",
	"company_tax_id",
)

KACHA_PRINT_FORMAT = "GIC Kacha Slip"


def kacha_enabled() -> bool:
	return bool(frappe.db.get_single_value(PROFILE, "enable_kacha_pakka_mode"))


def is_kacha(doc) -> bool:
	return doc.get("gic_bill_mode") == KACHA


def before_validate(doc, method=None):
	"""Sales Invoice hook. Runs before ERPNext's own validate calculates totals."""
	if not doc.get("gic_bill_mode"):
		doc.gic_bill_mode = PAKKA
	if is_kacha(doc) and not kacha_enabled():
		frappe.throw(
			_("Kacha bills are switched off in GIC Industry Profile. Use Pakka (Tax Invoice)."),
			title=_("Kacha Billing Off"),
		)
	if is_kacha(doc):
		clear_taxes(doc)


def validate(doc, method=None):
	"""Safety net: ERPNext can re-apply a default tax template during validate."""
	if is_kacha(doc) and doc.get("taxes"):
		clear_taxes(doc)
		doc.calculate_taxes_and_totals()


def clear_taxes(doc):
	doc.taxes_and_charges = None
	doc.tax_category = None
	doc.set("taxes", [])


def ensure_bill_mode_setup():
	"""Property Setters hiding tax fields on Kacha bills. Idempotent."""
	for fieldname in PAKKA_ONLY_FIELDS:
		if not frappe.get_meta("Sales Invoice").get_field(fieldname):
			continue  # renamed or removed in a future ERPNext version
		name = f"Sales Invoice-{fieldname}-depends_on"
		values = {
			"doctype_or_field": "DocField",
			"doc_type": "Sales Invoice",
			"field_name": fieldname,
			"property": "depends_on",
			"property_type": "Data",
			"value": NOT_KACHA,
			"module": MODULE,
		}
		if frappe.db.exists("Property Setter", name):
			frappe.db.set_value("Property Setter", name, values)
		else:
			frappe.get_doc({"doctype": "Property Setter", "is_system_generated": 0, **values}).insert(
				ignore_permissions=True
			)
	frappe.clear_cache(doctype="Sales Invoice")
