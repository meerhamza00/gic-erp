# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""Least-privilege permissions for the two GIC roles on standard ERPNext doctypes.

Applied through frappe.permissions.add_permission, which first copies a doctype's standard
permissions into Custom DocPerm and only then adds ours, so other roles keep their access.

These are deliberately NOT exported as fixtures: a fixture would import only the GIC rows,
and Frappe would then use those rows alone, locking every other role out of Sales Invoice
and friends. Install and patches run apply_gic_permissions() instead.

Trade-off: once a doctype has Custom DocPerm rows, later ERPNext upgrades to that doctype's
standard permissions are not picked up automatically (normal Frappe behaviour).
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

OWNER = "GIC Factory Owner"
MUNSHI = "GIC Munshi User"

OWNER_TXN = (
	"read",
	"write",
	"create",
	"submit",
	"cancel",
	"amend",
	"delete",
	"print",
	"email",
	"report",
	"export",
)
MUNSHI_TXN = ("read", "write", "create", "submit", "print", "email", "report")  # no cancel / amend / delete
MASTER_EDIT = ("read", "write", "create", "report")
READ = ("read", "report")
LOOKUP = ("read",)

# Everyday documents on the GIC Easy Desk.
TRANSACTIONS = ("Sales Invoice", "Quotation", "Payment Entry", "Stock Entry")

# Masters a munshi needs to look up while filling those forms (link fields).
LOOKUP_MASTERS = (
	"Company",
	"Warehouse",
	"UOM",
	"UOM Conversion Factor",
	"Item Group",
	"Item Price",
	"Price List",
	"Currency",
	"Mode of Payment",
	"Account",
	"Cost Center",
	"Fiscal Year",
	"Sales Taxes and Charges Template",
	"Purchase Taxes and Charges Template",
	"Item Tax Template",
	"Tax Category",
	"Stock Entry Type",
	"Customer Group",
	"Supplier Group",
	"Territory",
	"Address",
	"Contact",
	"Payment Terms Template",
	"Terms and Conditions",
	"Letter Head",
	"Print Heading",
	"Brand",
	"Batch",
	"Serial No",
	"BOM",
	"Work Order",
)

# doctype -> {role: ptypes}
PERMISSIONS: dict[str, dict[str, tuple[str, ...]]] = {
	**{dt: {OWNER: OWNER_TXN, MUNSHI: MUNSHI_TXN} for dt in TRANSACTIONS},
	# Thekedar invoices: the owner reviews and pays them; the munshi never touches them.
	"Purchase Invoice": {OWNER: OWNER_TXN},
	"Customer": {OWNER: MASTER_EDIT, MUNSHI: MASTER_EDIT},
	"Supplier": {OWNER: MASTER_EDIT, MUNSHI: MASTER_EDIT},
	"Item": {OWNER: MASTER_EDIT, MUNSHI: READ},
	# "Party Khata" = General Ledger report, which reads GL Entry.
	"GL Entry": {OWNER: READ, MUNSHI: READ},
	**{dt: {OWNER: LOOKUP, MUNSHI: LOOKUP} for dt in LOOKUP_MASTERS},
}

# Reports whose role list is extended (additively, via Custom Role) for the GIC roles.
REPORTS = {"General Ledger": (OWNER, MUNSHI)}


def apply_gic_permissions():
	"""Idempotent. Grants exactly the listed rights; never removes anyone else's."""
	for doctype, roles in PERMISSIONS.items():
		if not frappe.db.exists("DocType", doctype):
			continue  # e.g. a doctype removed in a future ERPNext version
		for role, ptypes in roles.items():
			add_permission(doctype, role, 0)
			for ptype in ptypes:
				update_permission_property(doctype, role, 0, ptype, 1, validate=False)
		frappe.clear_cache(doctype=doctype)

	for report, roles in REPORTS.items():
		_extend_report_roles(report, roles)


def _extend_report_roles(report: str, roles: tuple[str, ...]):
	if not frappe.db.exists("Report", report):
		return
	name = frappe.db.get_value("Custom Role", {"report": report})
	doc = frappe.get_doc("Custom Role", name) if name else frappe.new_doc("Custom Role")
	if not name:
		doc.report = report
		# Custom Role replaces nothing: Frappe adds these to the report's own roles.
		doc.extend(
			"roles",
			[
				{"role": r}
				for r in frappe.get_all("Has Role", {"parent": report, "parenttype": "Report"}, pluck="role")
			],
		)
	have = {r.role for r in doc.roles}
	doc.extend("roles", [{"role": r} for r in roles if r not in have])
	doc.flags.ignore_permissions = True
	doc.save()
