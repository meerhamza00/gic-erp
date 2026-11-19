# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""Custom Fields GIC adds to ERPNext doctypes. All carry module "GIC ERP" so they export as fixtures."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "GIC ERP"
MELT = "eval:doc.gic_is_foundry_melt==1"


def _f(**df) -> dict:
	return {"module": MODULE, **df}


CUSTOM_FIELDS: dict[str, list[dict]] = {
	"Stock Entry": [
		_f(
			fieldname="gic_foundry_section",
			label="Foundry Melt / Burning Loss",
			fieldtype="Section Break",
			insert_after="items",
			collapsible=1,
		),
		_f(
			fieldname="gic_is_foundry_melt",
			label="Foundry Melt / Scrap Entry",
			fieldtype="Check",
			insert_after="gic_foundry_section",
			description="Tick for a melt: enter metal issued and scrap recovered to get burning loss.",
		),
		_f(
			fieldname="gic_gross_metal_weight",
			label="Gross Metal Issued (Kg)",
			fieldtype="Float",
			insert_after="gic_is_foundry_melt",
			depends_on=MELT,
			mandatory_depends_on=MELT,
		),
		_f(
			fieldname="gic_finished_weight",
			label="Finished Goods Weight (Kg)",
			fieldtype="Float",
			insert_after="gic_gross_metal_weight",
			depends_on=MELT,
			description="Filled automatically when finished items are stocked in Kg or have a weight per unit. Otherwise enter it.",
		),
		_f(
			fieldname="gic_scrap_recovered",
			label="Reusable Scrap Recovered (Kg)",
			fieldtype="Float",
			insert_after="gic_finished_weight",
			depends_on=MELT,
		),
		_f(
			fieldname="gic_foundry_col",
			fieldtype="Column Break",
			insert_after="gic_scrap_recovered",
		),
		_f(
			fieldname="gic_burning_loss_qty",
			label="Burning Loss (Kg)",
			fieldtype="Float",
			insert_after="gic_foundry_col",
			read_only=1,
			depends_on=MELT,
		),
		_f(
			fieldname="gic_burning_loss_pct",
			label="Burning Loss %",
			fieldtype="Percent",
			insert_after="gic_burning_loss_qty",
			read_only=1,
			depends_on=MELT,
		),
	],
}


def ensure_custom_fields():
	"""Idempotent: creates missing fields and updates changed ones."""
	create_custom_fields(CUSTOM_FIELDS, update=True)
