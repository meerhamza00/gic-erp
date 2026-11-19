# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""Custom Fields GIC adds to ERPNext doctypes. All carry module "GIC ERP" so they export as fixtures."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "GIC ERP"
MELT = "eval:doc.gic_is_foundry_melt==1"


def _f(**df) -> dict:
	return {"module": MODULE, **df}


PAKKA = "Pakka (Tax Invoice)"
KACHA = "Kacha (Estimate Slip)"

FBR_NOT_APPLICABLE = "Not Applicable"
FBR_PENDING = "Pending"
FBR_SYNCED = "Synced"
FBR_FAILED = "Failed"
FBR_STATUSES = (FBR_NOT_APPLICABLE, FBR_PENDING, FBR_SYNCED, FBR_FAILED)
FBR_SHOWN = f"eval:doc.gic_fbr_sync_status && doc.gic_fbr_sync_status!='{FBR_NOT_APPLICABLE}'"

CUSTOM_FIELDS: dict[str, list[dict]] = {
	"Sales Invoice": [
		_f(
			fieldname="gic_bill_mode",
			label="Bill Type",
			fieldtype="Select",
			options=f"{PAKKA}\n{KACHA}",
			default=PAKKA,
			insert_after="customer",
			in_list_view=1,
			in_standard_filter=1,
			print_hide=1,
			no_copy=0,
			description="Kacha: estimate / delivery memo without sales tax. It still posts to the books.",
		),
		# FBR Digital Invoicing (Milestone 5). Filled by gic_erp.services.fbr_sync after submit.
		_f(
			fieldname="gic_fbr_section",
			label="FBR Digital Invoice",
			fieldtype="Section Break",
			insert_after="other_charges_calculation",
			collapsible=1,
			depends_on=FBR_SHOWN,
		),
		_f(
			fieldname="gic_fbr_sync_status",
			label="FBR Sync Status",
			fieldtype="Select",
			options="\n".join(FBR_STATUSES),
			default=FBR_NOT_APPLICABLE,
			insert_after="gic_fbr_section",
			read_only=1,
			allow_on_submit=1,
			no_copy=1,
			in_standard_filter=1,
			print_hide=1,
		),
		_f(
			fieldname="gic_fbr_invoice_no",
			label="FBR Invoice No",
			fieldtype="Data",
			insert_after="gic_fbr_sync_status",
			read_only=1,
			allow_on_submit=1,
			no_copy=1,
		),
		_f(
			fieldname="gic_fbr_col",
			fieldtype="Column Break",
			insert_after="gic_fbr_invoice_no",
		),
		_f(
			fieldname="gic_fbr_qr_image",
			label="FBR QR Code",
			fieldtype="Attach Image",
			insert_after="gic_fbr_col",
			read_only=1,
			allow_on_submit=1,
			no_copy=1,
			hidden=1,
		),
		_f(
			# Shows the QR picture on the form and in prints (the Attach field shows only its path).
			fieldname="gic_fbr_qr_preview",
			label="FBR QR Code",
			fieldtype="Image",
			options="gic_fbr_qr_image",
			insert_after="gic_fbr_qr_image",
			depends_on="eval:doc.gic_fbr_qr_image",
		),
	],
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
