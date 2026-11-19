# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""Install-time setup for GIC-ERP. Every function here is idempotent: safe to run again."""

import frappe

from gic_erp.billing.kacha_pakka import ensure_bill_mode_setup
from gic_erp.setup.branding import apply_branding
from gic_erp.setup.custom_fields import ensure_custom_fields
from gic_erp.setup.module_visibility import restrict_admin_workspaces
from gic_erp.setup.permissions import apply_gic_permissions
from gic_erp.setup.ui_simplifier import simplify_forms

EASY_DESK_ROUTE = "/app/gic-easy-desk"

GIC_ROLES = ("GIC Factory Owner", "GIC Munshi User")

# (name, must_be_whole_number). Existing ERPNext UOMs are reused, not duplicated:
# ERPNext ships "Kg" (not "Kilogram"), "Foot" and "Meter" already.
LOCAL_UOMS = (
	("Mann", 0),  # maund, fractional quantities are common (e.g. 2.5 mann)
	("Bori", 1),  # sack; weight varies by item, so it is converted per item, not globally
	("Petti", 1),  # carton/box; contents vary by item, converted per item
	("Dozen", 1),
	("Piece", 1),
	("Kg", 0),
	("Foot", 0),
	("Meter", 0),
)

COUNT_CATEGORY = "Count"

# (category, from_uom, to_uom, value) -> 1 from_uom = value to_uom
UOM_CONVERSIONS = (
	("Mass", "Mann", "Kg", 40),
	(COUNT_CATEGORY, "Dozen", "Piece", 12),
)


def after_install():
	setup_local_defaults()
	setup_manufacturing_and_permissions()
	setup_branding()
	setup_billing()
	setup_fbr()


def setup_local_defaults():
	"""Roles, local units and form decluttering. Called on install and by patch."""
	ensure_roles()
	ensure_uoms()
	ensure_uom_conversions()
	simplify_forms()


def setup_manufacturing_and_permissions():
	"""Foundry fields on Stock Entry and least-privilege GIC role permissions. Install and patch."""
	ensure_roles()  # permissions need the roles to exist
	ensure_custom_fields()
	apply_gic_permissions()


def setup_billing():
	"""Kacha / Pakka bill type field and its tax-field rules. Install and patch."""
	ensure_custom_fields()
	ensure_bill_mode_setup()


def setup_fbr():
	"""FBR sync status, invoice no and QR fields on Sales Invoice. Install and patch."""
	ensure_custom_fields()


def setup_branding():
	"""GICNEXT name, logos, help menu, letterhead; admin areas hidden from GIC roles. Install and patch."""
	apply_branding()
	restrict_admin_workspaces()


def ensure_roles():
	for role_name in GIC_ROLES:
		if frappe.db.exists("Role", role_name):
			role = frappe.get_doc("Role", role_name)
		else:
			role = frappe.new_doc("Role")
			role.role_name = role_name
		role.desk_access = 1
		# Land these users on the simple 5-button desk instead of the full ERPNext home.
		role.home_page = EASY_DESK_ROUTE
		role.flags.ignore_permissions = True
		role.save()


def ensure_uoms():
	for uom_name, whole_number in LOCAL_UOMS:
		if frappe.db.exists("UOM", uom_name):
			# Re-enable if someone disabled it; leave other settings alone.
			frappe.db.set_value("UOM", uom_name, "enabled", 1, update_modified=False)
			continue
		frappe.get_doc(
			{
				"doctype": "UOM",
				"uom_name": uom_name,
				"enabled": 1,
				"must_be_whole_number": whole_number,
			}
		).insert(ignore_permissions=True)


def ensure_uom_conversions():
	# On a fresh site after_install runs BEFORE ERPNext's setup wizard, so even ERPNext's
	# own categories (e.g. "Mass") may not exist yet. Create whatever we need; the wizard
	# skips records that already exist, so this cannot collide with it later.
	for category in {c for c, *_ in UOM_CONVERSIONS}:
		if not frappe.db.exists("UOM Category", category):
			frappe.get_doc({"doctype": "UOM Category", "category_name": category}).insert(
				ignore_permissions=True
			)

	for category, from_uom, to_uom, value in UOM_CONVERSIONS:
		existing = frappe.db.get_value(
			"UOM Conversion Factor", {"from_uom": from_uom, "to_uom": to_uom}, "name"
		)
		if existing:
			frappe.db.set_value("UOM Conversion Factor", existing, {"value": value, "category": category})
			continue
		frappe.get_doc(
			{
				"doctype": "UOM Conversion Factor",
				"category": category,
				"from_uom": from_uom,
				"to_uom": to_uom,
				"value": value,
			}
		).insert(ignore_permissions=True)
