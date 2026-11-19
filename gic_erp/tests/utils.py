# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""Shared test data. Everything is prefixed "_GIC Test" and created idempotently."""

import frappe

PREFIX = "_GIC Test"


def company() -> str:
	name = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
	if not name:
		raise RuntimeError("Tests need a Company: run ERPNext's setup wizard on the test site.")
	return name


def abbr() -> str:
	return frappe.db.get_value("Company", company(), "abbr")


def warehouse(kind: str = "Stores") -> str:
	return f"{kind} - {abbr()}"


def make_customer(name: str = f"{PREFIX} Customer") -> str:
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
				"territory": frappe.db.get_value("Territory", {"is_group": 0})
				or frappe.db.get_value("Territory", {}),
			}
		).insert(ignore_permissions=True)
	return name


def make_supplier(name: str = f"{PREFIX} Thekedar") -> str:
	if not frappe.db.exists("Supplier", name):
		frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": name,
				"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}),
			}
		).insert(ignore_permissions=True)
	return name


def make_item(
	code: str,
	stock_uom: str = "Nos",
	is_stock_item: int = 1,
	weight_per_unit: float = 0,
	weight_uom: str | None = None,
	valuation_rate: float = 100,
) -> str:
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": frappe.db.get_value("Item Group", {"is_group": 1}),
				"stock_uom": stock_uom,
				"is_stock_item": is_stock_item,
				"valuation_rate": valuation_rate,
				"weight_per_unit": weight_per_unit,
				"weight_uom": weight_uom,
			}
		).insert(ignore_permissions=True)
	return code


def make_user(email: str, *roles: str) -> str:
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.add_roles(*roles)
	frappe.clear_cache(user=email)
	return email
