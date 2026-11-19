# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from gic_erp.setup.module_visibility import apply_module_visibility

# Features each business type needs. Selecting a type switches these ON.
# It never switches anything OFF, so a user can still add extra features.
PROFILE_DEFAULTS: dict[str, tuple[str, ...]] = {
	"Light Engineering & Foundry": ("enable_scrap_tracking", "enable_thekedar_payroll"),
	"Wholesale & Mandi Trader": ("enable_kacha_pakka_mode",),
	"Importer & Exporter": ("enable_fbr_invoicing",),
	"Sanitary Ware & Ceramics": ("enable_scrap_tracking",),
}


class GICIndustryProfile(Document):
	def validate(self):
		self.validate_business_type()
		self.apply_profile_defaults()

	def on_update(self):
		result = apply_module_visibility(self)
		# Write status fields directly so we don't re-trigger on_update.
		self.db_set(
			{
				"last_applied_on": frappe.utils.now_datetime(),
				"hidden_workspaces": ", ".join(result["hidden_workspaces"]) or _("None"),
			},
			update_modified=False,
		)

	def validate_business_type(self):
		if self.business_type not in PROFILE_DEFAULTS:
			frappe.throw(
				_("Business Type must be one of: {0}").format(", ".join(PROFILE_DEFAULTS)),
				title=_("Invalid Business Type"),
			)

	def apply_profile_defaults(self):
		switched_on = []
		for fieldname in PROFILE_DEFAULTS[self.business_type]:
			if not self.get(fieldname):
				self.set(fieldname, 1)
				switched_on.append(self.meta.get_label(fieldname))

		if switched_on:
			frappe.msgprint(
				_("Switched on for {0}: {1}").format(self.business_type, ", ".join(switched_on)),
				indicator="blue",
				alert=True,
			)


@frappe.whitelist()
def reapply_visibility():
	"""Re-run workspace and module visibility from the saved profile (form button)."""
	frappe.only_for("System Manager")
	profile = frappe.get_single("GIC Industry Profile")
	if not profile.business_type:
		frappe.throw(_("Save a Business Type first."))
	profile.on_update()
	return {"hidden_workspaces": frappe.db.get_single_value("GIC Industry Profile", "hidden_workspaces")}
