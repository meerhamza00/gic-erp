# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""Milestone 2: roles, local units, GIC Easy Desk and form decluttering."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from gic_erp.install import EASY_DESK_ROUTE, GIC_ROLES, LOCAL_UOMS, setup_local_defaults
from gic_erp.setup import ui_simplifier
from gic_erp.setup.ui_simplifier import (
	_required_fields_inside,
	plan_simplification,
	restore_forms,
	simplify_forms,
)

EXPECTED_SHORTCUTS = {
	"Create Bill": "Sales Invoice",
	"Kacha Estimate": "Quotation",
	"Receive Udhaar": "Payment Entry",
	"Stock & Scrap": "Stock Entry",
	"Party Khata": "General Ledger",
}


def _is_hidden_by_gic(doctype: str, fieldname: str) -> bool:
	return bool(
		frappe.db.exists(
			"Property Setter",
			{"name": f"{doctype}-{fieldname}-hidden", "module": "GIC ERP", "value": "1"},
		)
	)


class TestRolesAndUnits(FrappeTestCase):
	def test_roles_exist_and_land_on_easy_desk(self):
		for role in GIC_ROLES:
			self.assertEqual(frappe.db.get_value("Role", role, "desk_access"), 1)
			self.assertEqual(frappe.db.get_value("Role", role, "home_page"), EASY_DESK_ROUTE)

	def test_local_uoms_exist_and_enabled(self):
		for uom, _whole in LOCAL_UOMS:
			self.assertEqual(frappe.db.get_value("UOM", uom, "enabled"), 1, uom)
		self.assertEqual(frappe.db.get_value("UOM", "Bori", "must_be_whole_number"), 1)
		self.assertEqual(frappe.db.get_value("UOM", "Mann", "must_be_whole_number"), 0)

	def test_no_duplicate_kilogram_uom(self):
		# ERPNext's "Kg" is reused on purpose; a second "Kilogram" would cause wrong picks.
		self.assertFalse(frappe.db.exists("UOM", "Kilogram"))

	def test_mann_is_40_kg(self):
		self.assertEqual(
			frappe.db.get_value("UOM Conversion Factor", {"from_uom": "Mann", "to_uom": "Kg"}, "value"),
			40,
		)

	def test_dozen_is_12_piece(self):
		self.assertEqual(
			frappe.db.get_value("UOM Conversion Factor", {"from_uom": "Dozen", "to_uom": "Piece"}, "value"),
			12,
		)

	def test_setup_is_idempotent(self):
		setup_local_defaults()
		setup_local_defaults()
		self.assertEqual(frappe.db.count("UOM Conversion Factor", {"from_uom": "Mann", "to_uom": "Kg"}), 1)
		self.assertEqual(frappe.db.count("UOM", {"name": "Mann"}), 1)


class TestEasyDesk(FrappeTestCase):
	def test_workspace_has_exactly_five_shortcuts(self):
		ws = frappe.get_doc("Workspace", "GIC Easy Desk")
		self.assertEqual(ws.module, "GIC ERP")
		self.assertEqual(ws.public, 1)
		self.assertEqual({s.label: s.link_to for s in ws.shortcuts}, EXPECTED_SHORTCUTS)

	def test_every_shortcut_is_placed_on_the_page(self):
		ws = frappe.get_doc("Workspace", "GIC Easy Desk")
		placed = {
			block["data"]["shortcut_name"] for block in json.loads(ws.content) if block["type"] == "shortcut"
		}
		self.assertEqual(placed, set(EXPECTED_SHORTCUTS))

	def test_shortcut_targets_exist(self):
		ws = frappe.get_doc("Workspace", "GIC Easy Desk")
		for s in ws.shortcuts:
			target = "Report" if s.type == "Report" else "DocType"
			self.assertTrue(frappe.db.exists(target, s.link_to), s.link_to)


class TestUISimplifier(FrappeTestCase):
	def tearDown(self):
		simplify_forms()  # leave the site simplified, as installed

	def test_planned_sections_are_hidden(self):
		simplify_forms()
		self.assertTrue(_is_hidden_by_gic("Sales Invoice", "time_sheet_list"))
		self.assertTrue(_is_hidden_by_gic("Sales Invoice", "project"))
		self.assertTrue(_is_hidden_by_gic("Purchase Invoice", "terms_section_break"))
		self.assertTrue(_is_hidden_by_gic("Payment Entry", "accounting_dimensions_section"))
		self.assertEqual(frappe.get_meta("Sales Invoice").get_field("time_sheet_list").hidden, 1)

	def test_section_with_required_field_is_never_hidden(self):
		# Sales Invoice "more_info" holds the required debit_to account.
		self.assertIn("debit_to", _required_fields_inside(frappe.get_meta("Sales Invoice"), "more_info"))
		plan = plan_simplification()["Sales Invoice"]
		self.assertNotIn("more_info", plan["hide"])
		self.assertIn("more_info", [f for f, _ in plan["skipped"]])
		simplify_forms()
		self.assertFalse(_is_hidden_by_gic("Sales Invoice", "more_info"))

	def test_unknown_fields_are_skipped_not_errors(self):
		original = ui_simplifier.HIDE_TARGETS
		try:
			ui_simplifier.HIDE_TARGETS = {"Payment Entry": ("no_such_field_xyz",)}
			plan = plan_simplification()["Payment Entry"]
			self.assertEqual(plan["hide"], [])
			self.assertEqual(plan["skipped"], [("no_such_field_xyz", "not in this ERPNext version")])
		finally:
			ui_simplifier.HIDE_TARGETS = original

	def test_simplify_is_idempotent(self):
		simplify_forms()
		simplify_forms()
		self.assertEqual(frappe.db.count("Property Setter", {"name": "Sales Invoice-project-hidden"}), 1)

	def test_restore_shows_sections_again(self):
		simplify_forms()
		self.assertGreater(restore_forms(), 0)
		self.assertFalse(_is_hidden_by_gic("Sales Invoice", "time_sheet_list"))
		self.assertFalse(frappe.get_meta("Sales Invoice").get_field("time_sheet_list").hidden)
