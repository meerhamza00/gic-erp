# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt

import os

import frappe
from frappe.desk.desktop import get_workspace_sidebar_items
from frappe.tests.utils import FrappeTestCase

from gic_erp.setup import branding
from gic_erp.setup.module_visibility import ADMIN_ONLY_WORKSPACES, ADMIN_ROLE, restrict_admin_workspaces
from gic_erp.tests.utils import company, make_user

test_ignore = ["Company"]

MUNSHI = "gic-branding-munshi@example.com"
OWNER = "gic-branding-owner@example.com"


def _sidebar_for(user: str) -> list[str]:
	frappe.set_user(user)
	try:
		return [p["name"] for p in get_workspace_sidebar_items()["pages"]]
	finally:
		frappe.set_user("Administrator")


class TestBranding(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		branding.apply_branding()
		restrict_admin_workspaces()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_product_name_is_gicnext(self):
		self.assertEqual(frappe.db.get_single_value("System Settings", "app_name"), "GICNEXT")
		self.assertEqual(frappe.db.get_single_value("Website Settings", "app_name"), "GICNEXT")

	def test_logos_and_favicon_point_at_gic_assets(self):
		from frappe.core.doctype.navbar_settings.navbar_settings import get_app_logo

		self.assertEqual(get_app_logo(), branding.LOGO)
		self.assertEqual(frappe.db.get_single_value("Website Settings", "favicon"), branding.FAVICON)
		for path in (branding.LOGO, branding.FAVICON, branding.SPLASH):
			file = frappe.get_app_path("gic_erp", "public", path.split("/assets/gic_erp/")[1])
			self.assertTrue(os.path.exists(file), file)

	def test_vendor_help_links_hidden_not_deleted(self):
		items = {i.item_label: i.hidden for i in frappe.get_single("Navbar Settings").help_dropdown}
		for label in branding.HIDDEN_HELP_ITEMS:
			if label in items:
				self.assertEqual(items[label], 1, label)
		self.assertEqual(items.get("About"), 0)

	def test_erpnext_email_footer_disabled(self):
		self.assertEqual(frappe.utils.cint(frappe.db.get_default("disable_standard_email_footer")), 1)

	def test_english_labels_say_gicnext(self):
		from frappe.translate import get_all_translations

		frappe.clear_cache()  # drops the merged translations cache
		translations = get_all_translations("en")
		self.assertEqual(translations.get("ERPNext Settings"), "GICNEXT Settings")
		self.assertEqual(translations.get("ERPNext"), "GICNEXT")

	def test_letter_head_shows_client_company_and_gicnext_credit(self):
		lh = frappe.get_doc("Letter Head", branding.LETTER_HEAD_NAME)
		header = frappe.render_template(lh.content, {"doc": frappe._dict(company=company())})
		footer = frappe.render_template(lh.footer, {"doc": frappe._dict(company=company())})
		self.assertIn(frappe.db.get_value("Company", company(), "company_name"), header)
		self.assertNotIn("gic_logo", header)  # the bill belongs to the client, not GIC
		self.assertIn("NEXT", footer)

	def test_letter_head_renders_without_company(self):
		lh = frappe.get_doc("Letter Head", branding.LETTER_HEAD_NAME)
		frappe.render_template(lh.content, {"doc": frappe._dict(company=None)})

	def test_apply_branding_is_idempotent(self):
		before = frappe.db.get_value("Letter Head", branding.LETTER_HEAD_NAME, "modified")
		branding.apply_branding()
		self.assertEqual(frappe.db.get_value("Letter Head", branding.LETTER_HEAD_NAME, "modified"), before)
		self.assertEqual(frappe.db.count("Letter Head", {"name": branding.LETTER_HEAD_NAME}), 1)


class TestAdminWorkspaces(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		restrict_admin_workspaces()
		make_user(MUNSHI, "GIC Munshi User")
		make_user(OWNER, "GIC Factory Owner")

	def test_munshi_and_owner_do_not_see_admin_areas(self):
		existing = set(frappe.get_all("Workspace", {"name": ("in", ADMIN_ONLY_WORKSPACES)}, pluck="name"))
		self.assertTrue(existing, "expected some admin workspaces on the site")
		for user in (MUNSHI, OWNER):
			sidebar = set(_sidebar_for(user))
			self.assertFalse(sidebar & existing, f"{user} sees {sidebar & existing}")
			self.assertIn("GIC Easy Desk", sidebar)

	def test_admin_keeps_admin_areas(self):
		self.assertIn("Build", [p["name"] for p in get_workspace_sidebar_items()["pages"]])

	def test_restriction_is_idempotent(self):
		restrict_admin_workspaces()
		restrict_admin_workspaces()
		for name in frappe.get_all("Workspace", {"name": ("in", ADMIN_ONLY_WORKSPACES)}, pluck="name"):
			self.assertEqual(
				frappe.db.count("Has Role", {"parenttype": "Workspace", "parent": name, "role": ADMIN_ROLE}),
				1,
				name,
			)
