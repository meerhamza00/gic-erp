# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""Hide rarely used sections on everyday forms so they fit on one screen for a munshi.

Uses Property Setter records (module "GIC ERP", so they export as fixtures). No core files change.

Safety rule: a section or tab is never hidden if it contains a required field. A hidden
required field would block saving with an error about a field the user cannot see.
Such targets are skipped and reported instead.
"""

import frappe
from frappe import _

MODULE = "GIC ERP"
CONTAINER_TYPES = ("Section Break", "Tab Break")

# Fields or sections to hide on each form. Names that do not exist in this ERPNext
# version are skipped, so an upgrade that renames a field cannot break install.
HIDE_TARGETS: dict[str, tuple[str, ...]] = {
	"Sales Invoice": (
		"project",
		"time_sheet_list",  # Timesheets section (includes the timesheets table)
		"accounting_dimensions_section",
		"terms_section_break",
		"subscription_section",
		"sales_team_section_break",
		"loyalty_points_redemption",
		"more_info",  # holds required debit_to: skipped by the safety rule, kept for the report
	),
	"Purchase Invoice": (
		"project",
		"accounting_dimensions_section",
		"terms_section_break",
		"subscription_section",
	),
	"Payment Entry": (
		"project",
		"accounting_dimensions_section",
		"subscription_section",
	),
}


def _property_setter_name(doctype: str, fieldname: str) -> str:
	return f"{doctype}-{fieldname}-hidden"


def _required_fields_inside(meta, fieldname: str) -> list[str]:
	"""Required, visible fields that sit inside the given section/tab."""
	field = meta.get_field(fieldname)
	if not field or field.fieldtype not in CONTAINER_TYPES:
		return []

	inside, required = False, []
	for f in meta.fields:
		if f.fieldname == fieldname:
			inside = True
			continue
		if not inside:
			continue
		# A section ends at the next section or tab; a tab ends only at the next tab.
		if f.fieldtype == "Tab Break" or (
			field.fieldtype == "Section Break" and f.fieldtype == "Section Break"
		):
			break
		if f.reqd and not f.hidden:
			required.append(f.fieldname)
	return required


def plan_simplification() -> dict[str, dict[str, list]]:
	"""Work out what would be hidden and what is skipped (and why), per doctype."""
	plan = {}
	for doctype, targets in HIDE_TARGETS.items():
		meta = frappe.get_meta(doctype)
		hide, skipped = [], []
		for fieldname in targets:
			field = meta.get_field(fieldname)
			if not field:
				skipped.append((fieldname, "not in this ERPNext version"))
			elif field.reqd:
				skipped.append((fieldname, "required field"))
			elif required := _required_fields_inside(meta, fieldname):
				skipped.append((fieldname, "contains required " + ", ".join(required)))
			else:
				hide.append(fieldname)
		plan[doctype] = {"hide": hide, "skipped": skipped}
	return plan


def simplify_forms() -> dict[str, dict[str, list]]:
	"""Create/refresh the hide Property Setters. Idempotent. Returns the plan applied."""
	plan = plan_simplification()
	for doctype, result in plan.items():
		for fieldname in result["hide"]:
			_upsert_hidden_setter(doctype, fieldname)
		frappe.clear_cache(doctype=doctype)
	return plan


def restore_forms() -> int:
	"""Remove GIC's hide Property Setters, showing the sections again. Returns count removed."""
	removed = 0
	for doctype, targets in HIDE_TARGETS.items():
		for fieldname in targets:
			name = _property_setter_name(doctype, fieldname)
			if frappe.db.exists("Property Setter", {"name": name, "module": MODULE}):
				frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)
				removed += 1
		frappe.clear_cache(doctype=doctype)
	return removed


def _upsert_hidden_setter(doctype: str, fieldname: str):
	name = _property_setter_name(doctype, fieldname)
	if frappe.db.exists("Property Setter", name):
		frappe.db.set_value("Property Setter", name, {"value": "1", "module": MODULE})
		return
	frappe.get_doc(
		{
			"doctype": "Property Setter",
			"doctype_or_field": "DocField",
			"doc_type": doctype,
			"field_name": fieldname,
			"property": "hidden",
			"property_type": "Check",
			"value": "1",
			"module": MODULE,
			"is_system_generated": 0,
		}
	).insert(ignore_permissions=True)


@frappe.whitelist()
def simplify_forms_from_ui():
	"""'Simplify Forms' button on GIC Industry Profile."""
	frappe.only_for("System Manager")
	plan = simplify_forms()
	hidden = sum(len(r["hide"]) for r in plan.values())
	skipped = [
		_("{0}: {1} ({2})").format(dt, field, reason)
		for dt, r in plan.items()
		for field, reason in r["skipped"]
	]
	return {"hidden_count": hidden, "skipped": skipped}
