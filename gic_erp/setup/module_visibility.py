# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""Hide ERPNext screens a Gujranwala SME does not use.

Two levers, both upgrade-safe (database records only, no core file edits):
1. Workspace.is_hidden on standard workspaces -> removes them from the sidebar for everyone.
2. Module Profile "GIC Standard User" with blocked modules -> assign it to munshi/staff users
   so the blocked modules disappear for them entirely. Admins keep full access.

Frappe re-syncs standard workspaces on migrate, so this also runs from the after_migrate hook.
"""

import frappe

MODULE_PROFILE_NAME = "GIC Standard User"

# Hidden for every business type. Names not present on this site are skipped,
# e.g. Healthcare/Education/Agriculture/Non Profit are separate apps since ERPNext v14.
ALWAYS_HIDDEN_WORKSPACES = (
	"Assets",
	"Quality",
	"Support",
	"Projects",
	"Healthcare",
	"Education",
	"Agriculture",
	"Non Profit",
)
ALWAYS_BLOCKED_MODULES = (
	"Assets",
	"Quality Management",
	"Support",
	"Projects",
	"Maintenance",
	"Telephony",
	"Healthcare",
	"Education",
	"Agriculture",
	"Non Profit",
)

MANUFACTURING_TYPES = ("Light Engineering & Foundry", "Sanitary Ware & Ceramics")

# Hidden only when the business does not manufacture.
NON_MANUFACTURING_HIDDEN_WORKSPACES = ("Manufacturing",)
NON_MANUFACTURING_BLOCKED_MODULES = ("Manufacturing", "Subcontracting")

# Every workspace this module may touch. Anything here that is not in the
# current hide list gets un-hidden, so switching business type is reversible.
MANAGED_WORKSPACES = ALWAYS_HIDDEN_WORKSPACES + NON_MANUFACTURING_HIDDEN_WORKSPACES

# Setup and admin areas. Restricted to System Manager so munshis and owners don't see them
# in the sidebar; admins keep them. Frappe shows a workspace that has roles only to users
# holding one of those roles.
ADMIN_ONLY_WORKSPACES = (
	"Users",
	"Website",
	"Tools",
	"ERPNext Settings",
	"ERPNext Integrations",
	"Integrations",
	"Build",
	"Welcome Workspace",
)
ADMIN_ROLE = "System Manager"


def get_hide_plan(business_type: str) -> tuple[list[str], list[str]]:
	workspaces = list(ALWAYS_HIDDEN_WORKSPACES)
	modules = list(ALWAYS_BLOCKED_MODULES)
	if business_type not in MANUFACTURING_TYPES:
		workspaces += NON_MANUFACTURING_HIDDEN_WORKSPACES
		modules += NON_MANUFACTURING_BLOCKED_MODULES
	return workspaces, modules


def apply_module_visibility(profile) -> dict:
	"""Apply visibility for a GIC Industry Profile document. Returns what was hidden."""
	workspaces, modules = get_hide_plan(profile.business_type)
	hidden = _set_workspace_visibility(set(workspaces))
	blocked = _sync_module_profile(modules)
	restrict_admin_workspaces()
	frappe.clear_cache()
	return {"hidden_workspaces": hidden, "blocked_modules": blocked}


def restrict_admin_workspaces() -> list[str]:
	"""Give each admin workspace the System Manager role. Idempotent.

	Rows are written directly: saving a standard workspace in developer mode would
	export it back into ERPNext's own JSON files. Workspace sync on migrate can drop
	the rows, so after_migrate re-applies this.
	"""
	restricted = []
	for name in frappe.get_all("Workspace", filters={"name": ("in", ADMIN_ONLY_WORKSPACES)}, pluck="name"):
		if not frappe.db.exists("Has Role", {"parenttype": "Workspace", "parent": name, "role": ADMIN_ROLE}):
			frappe.get_doc(
				{
					"doctype": "Has Role",
					"parenttype": "Workspace",
					"parentfield": "roles",
					"parent": name,
					"role": ADMIN_ROLE,
				}
			).db_insert()
		restricted.append(name)
	return restricted


def after_migrate():
	"""Re-apply after migrate, because standard workspace sync can reset is_hidden and roles."""
	if not frappe.db.table_exists("GIC Industry Profile", cached=False):
		return
	restrict_admin_workspaces()
	from gic_erp.setup.branding import apply_branding

	apply_branding()
	business_type = frappe.db.get_single_value("GIC Industry Profile", "business_type")
	if not business_type:
		return
	profile = frappe.get_single("GIC Industry Profile")
	apply_module_visibility(profile)


def _set_workspace_visibility(to_hide: set[str]) -> list[str]:
	existing = set(frappe.get_all("Workspace", filters={"name": ("in", MANAGED_WORKSPACES)}, pluck="name"))
	hidden = []
	for name in sorted(existing):
		should_hide = 1 if name in to_hide else 0
		# db.set_value: standard workspaces are read-only through the UI outside developer mode.
		frappe.db.set_value("Workspace", name, "is_hidden", should_hide, update_modified=False)
		if should_hide:
			hidden.append(name)
	return hidden


def _sync_module_profile(modules: list[str]) -> list[str]:
	existing_modules = set(frappe.get_all("Module Def", filters={"name": ("in", modules)}, pluck="name"))
	to_block = [m for m in modules if m in existing_modules]

	if frappe.db.exists("Module Profile", MODULE_PROFILE_NAME):
		doc = frappe.get_doc("Module Profile", MODULE_PROFILE_NAME)
		current = sorted(row.module for row in doc.block_modules)
		if current == sorted(to_block):
			# Unchanged: skip the save. Module Profile.on_update locks the record and
			# queues a job to update every assigned user, so saving on every profile
			# save / migrate would cause DocumentLockedError on quick repeat saves.
			return to_block
	else:
		doc = frappe.new_doc("Module Profile")
		doc.module_profile_name = MODULE_PROFILE_NAME

	doc.set("block_modules", [{"module": m} for m in to_block])
	doc.flags.ignore_permissions = True
	doc.save()
	return to_block
