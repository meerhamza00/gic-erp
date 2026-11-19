# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from gic_erp.setup.module_visibility import MODULE_PROFILE_NAME

FLAGS = (
	"enable_fbr_invoicing",
	"enable_whatsapp_alerts",
	"enable_thekedar_payroll",
	"enable_kacha_pakka_mode",
	"enable_scrap_tracking",
)


def _company() -> str:
	company = frappe.db.get_value("Company", {}, "name")
	if not company:
		raise RuntimeError("Tests need at least one Company on the site.")
	return company


def _save_profile(business_type: str, **flags):
	doc = frappe.get_single("GIC Industry Profile")
	doc.business_type = business_type
	doc.company = _company()
	for f in FLAGS:
		doc.set(f, flags.get(f, 0))
	doc.save()
	return frappe.get_single("GIC Industry Profile")


def _blocked_modules() -> set[str]:
	return set(frappe.get_all("Block Module", filters={"parent": MODULE_PROFILE_NAME}, pluck="module"))


def _is_hidden(workspace: str) -> int | None:
	return frappe.db.get_value("Workspace", workspace, "is_hidden")


class TestGICIndustryProfile(FrappeTestCase):
	def test_foundry_switches_on_scrap_and_thekedar(self):
		doc = _save_profile("Light Engineering & Foundry")
		self.assertEqual(doc.enable_scrap_tracking, 1)
		self.assertEqual(doc.enable_thekedar_payroll, 1)
		self.assertEqual(doc.enable_fbr_invoicing, 0)

	def test_defaults_never_switch_features_off(self):
		doc = _save_profile("Wholesale & Mandi Trader", enable_fbr_invoicing=1)
		self.assertEqual(doc.enable_fbr_invoicing, 1)
		self.assertEqual(doc.enable_kacha_pakka_mode, 1)

	def test_importer_switches_on_fbr(self):
		doc = _save_profile("Importer & Exporter")
		self.assertEqual(doc.enable_fbr_invoicing, 1)

	def test_invalid_business_type_rejected(self):
		doc = frappe.get_single("GIC Industry Profile")
		doc.business_type = "Bakery"
		doc.company = _company()
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_trader_hides_manufacturing_and_blocks_modules(self):
		doc = _save_profile("Wholesale & Mandi Trader")
		blocked = _blocked_modules()
		self.assertIn("Assets", blocked)
		self.assertIn("Manufacturing", blocked)
		if frappe.db.exists("Workspace", "Manufacturing"):
			self.assertEqual(_is_hidden("Manufacturing"), 1)
		self.assertTrue(doc.last_applied_on)

	def test_switching_to_foundry_unhides_manufacturing(self):
		_save_profile("Wholesale & Mandi Trader")
		_save_profile("Light Engineering & Foundry")
		blocked = _blocked_modules()
		self.assertNotIn("Manufacturing", blocked)
		self.assertIn("Assets", blocked)
		if frappe.db.exists("Workspace", "Manufacturing"):
			self.assertEqual(_is_hidden("Manufacturing"), 0)
		if frappe.db.exists("Workspace", "Assets"):
			self.assertEqual(_is_hidden("Assets"), 1)

	def test_repeat_save_does_not_resave_module_profile(self):
		# Regression: Module Profile.on_update locks the record and queues a user-update
		# job. Re-saving it on every profile save caused DocumentLockedError.
		_save_profile("Importer & Exporter")
		before = frappe.db.get_value("Module Profile", MODULE_PROFILE_NAME, "modified")
		_save_profile("Importer & Exporter")
		after = frappe.db.get_value("Module Profile", MODULE_PROFILE_NAME, "modified")
		self.assertEqual(before, after)

	def test_regular_user_sidebar_excludes_hidden_workspaces(self):
		# Workspace Managers still receive hidden pages (the desk CSS hides them), so check
		# what an ordinary staff user actually gets from the sidebar API.
		from frappe.desk.desktop import get_workspace_sidebar_items

		_save_profile("Wholesale & Mandi Trader")
		email = "gic-sidebar-check@example.com"
		if not frappe.db.exists("User", email):
			user = frappe.get_doc(
				{"doctype": "User", "email": email, "first_name": "Sidebar", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
			user.add_roles("Accounts User", "Stock User", "GIC Munshi User")

		try:
			frappe.set_user(email)
			names = [p["name"] for p in get_workspace_sidebar_items()["pages"]]
		finally:
			frappe.set_user("Administrator")

		self.assertIn("GIC Easy Desk", names)
		for hidden in ("Assets", "Manufacturing", "Projects", "Quality", "Support"):
			self.assertNotIn(hidden, names)
