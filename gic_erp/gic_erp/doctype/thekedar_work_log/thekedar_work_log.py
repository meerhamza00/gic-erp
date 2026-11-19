# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

LABOR_ITEM = "Thekedar Labor Charges"


class ThekedarWorkLog(Document):
	def validate(self):
		if flt(self.quantity_completed) <= 0:
			frappe.throw(_("Quantity Completed must be more than zero."))
		if flt(self.rate_per_unit) <= 0:
			frappe.throw(_("Rate Per Unit must be more than zero."))
		self.total_payable = flt(
			flt(self.quantity_completed) * flt(self.rate_per_unit),
			self.precision("total_payable"),
		)

	def on_submit(self):
		if self.purchase_invoice:
			return
		invoice = make_draft_purchase_invoice(self)
		self.db_set("purchase_invoice", invoice.name)
		frappe.msgprint(
			_("Draft Purchase Invoice {0} created for {1}.").format(
				frappe.utils.get_link_to_form("Purchase Invoice", invoice.name),
				frappe.bold(self.contractor_name or self.contractor),
			),
			indicator="green",
			alert=True,
		)

	def on_cancel(self):
		if not self.purchase_invoice:
			return
		docstatus = frappe.db.get_value("Purchase Invoice", self.purchase_invoice, "docstatus")
		if docstatus == 1:
			frappe.throw(
				_("Cancel Purchase Invoice {0} first, then cancel this work log.").format(
					frappe.utils.get_link_to_form("Purchase Invoice", self.purchase_invoice)
				),
				title=_("Invoice Already Submitted"),
			)
		invoice = self.purchase_invoice
		# Unlink first: the invoice cannot be deleted while this log still points at it.
		self.db_set("purchase_invoice", None)
		if docstatus == 0:
			frappe.delete_doc("Purchase Invoice", invoice, ignore_permissions=True)


def make_draft_purchase_invoice(log: ThekedarWorkLog):
	"""Draft Purchase Invoice for the thekedar's labour. Created by the system on submit,
	so the munshi needs no Purchase Invoice permission; the owner reviews and submits it."""
	ensure_labor_item()
	description = _("{0} x {1} {2} @ {3} ({4}) - Work Log {5}").format(
		log.item_produced,
		frappe.format(log.quantity_completed),
		log.uom or "",
		frappe.format(log.rate_per_unit, {"fieldtype": "Currency", "options": log.currency}),
		log.operation_type or _("Labour"),
		log.name,
	)
	invoice = frappe.get_doc(
		{
			"doctype": "Purchase Invoice",
			"supplier": log.contractor,
			"company": log.company,
			"posting_date": log.posting_date,
			"set_posting_time": 1,
			"bill_date": log.posting_date,
			"remarks": description,
			"items": [
				{
					"item_code": LABOR_ITEM,
					"description": description,
					"qty": 1,
					"rate": log.total_payable,
				}
			],
		}
	)
	invoice.flags.ignore_permissions = True
	invoice.set_missing_values()
	invoice.insert()
	return invoice


def ensure_labor_item():
	"""Non-stock service item used on thekedar invoices. Created on first use, because on a
	fresh site the item groups only exist after ERPNext's setup wizard."""
	if frappe.db.exists("Item", LABOR_ITEM):
		return
	item_group = (
		"Services"
		if frappe.db.exists("Item Group", "Services")
		else frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ["in", ["", None]]})
	)
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": LABOR_ITEM,
			"item_name": LABOR_ITEM,
			"item_group": item_group,
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"is_purchase_item": 1,
			"is_sales_item": 0,
			"include_item_in_manufacturing": 0,
			"description": "Piece-rate labour paid to a thekedar.",
		}
	).insert(ignore_permissions=True)
