# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""FBR Digital Invoicing (PRAL) for Pakka sales invoices.

On submit, a Pakka bill is marked Pending and a background job sends it to FBR. The job
maps the invoice to PRAL's Digital Invoicing JSON, gets FBR's invoice number back, makes
the QR code FBR requires on the printed bill, and marks the bill Synced (or Failed).

Sandbox Mode (the default) never calls FBR: it returns a simulated reply with a
"SANDBOX-" invoice number, so the whole flow can be tested safely. Live mode POSTs to
the URL in GIC FBR Settings with the PRAL Bearer token. Field names follow PRAL's
Digital Invoicing API; confirm them against your PRAL onboarding documents before
going live.

Sending never blocks a bill: failures go to Error Log as "GIC FBR Sync Error" and the
bill shows Failed with a "Retry FBR Sync" button.
"""

import io
import re
import time

import frappe
import requests
from frappe import _
from frappe.utils import flt, getdate, strip_html

from gic_erp.setup.custom_fields import (
	FBR_FAILED,
	FBR_PENDING,
	FBR_SYNCED,
	PAKKA,
)

SETTINGS = "GIC FBR Settings"
PROFILE = "GIC Industry Profile"
ERROR_TITLE = "GIC FBR Sync Error"
TIMEOUT_SECONDS = 30
FBR_OK = "00"
SANDBOX_PREFIX = "SANDBOX-"
DEFAULT_SALE_TYPE = "Goods at standard rate (default)"

# Tax rows that are income tax withheld (236G / 236H), not sales tax. They are not part
# of the FBR sales tax amount.
WITHHOLDING_PATTERN = re.compile(r"withholding|\b236[gh]\b", re.IGNORECASE)

# ERPNext UOM -> FBR UoM description. Anything else is sent as it is.
FBR_UOM = {
	"Nos": "Numbers, pieces, units",
	"Piece": "Numbers, pieces, units",
	"Unit": "Numbers, pieces, units",
	"Kg": "KG",
	"Dozen": "Dozen",
	"Meter": "Meter",
	"Litre": "Liter",
}


# ---------------------------------------------------------------- switches


def fbr_active() -> bool:
	"""Profile switch AND settings switch."""
	if not frappe.db.get_single_value(PROFILE, "enable_fbr_invoicing"):
		return False
	return bool(frappe.db.get_single_value(SETTINGS, "enabled"))


def needs_fbr(doc) -> bool:
	return doc.get("gic_bill_mode") == PAKKA and not doc.get("is_return") and fbr_active()


# ---------------------------------------------------------------- hook


def on_sales_invoice_submit(doc, method=None):
	"""Sales Invoice on_submit: queue the FBR sync for Pakka bills only."""
	if not needs_fbr(doc):
		return
	doc.db_set("gic_fbr_sync_status", FBR_PENDING, update_modified=False)
	_queue(doc.name)


def _queue(docname: str):
	frappe.enqueue(
		"gic_erp.services.fbr_sync.sync_invoice_to_fbr",
		queue="default",
		timeout=120,
		enqueue_after_commit=True,
		docname=docname,
	)


@frappe.whitelist()
def retry_fbr_sync(docname: str):
	"""'Retry FBR Sync' button on a Pending or Failed bill. Queues the job again."""
	doc = frappe.get_doc("Sales Invoice", docname)
	doc.check_permission("submit")
	if doc.docstatus != 1:
		frappe.throw(_("Submit the invoice first."))
	if doc.gic_fbr_sync_status == FBR_SYNCED:
		frappe.throw(_("This invoice is already synced with FBR."))
	if not needs_fbr(doc):
		frappe.throw(_("FBR invoicing is off, or this is not a Pakka (Tax Invoice) bill."))
	doc.db_set("gic_fbr_sync_status", FBR_PENDING, update_modified=False)
	_queue(doc.name)
	return {"status": FBR_PENDING}


# ---------------------------------------------------------------- the job


def sync_invoice_to_fbr(docname: str) -> str:
	"""Send one Sales Invoice to FBR (or the sandbox). Returns the final sync status."""
	doc = frappe.get_doc("Sales Invoice", docname)
	if doc.gic_fbr_sync_status == FBR_SYNCED:
		return FBR_SYNCED
	settings = frappe.get_single(SETTINGS)

	try:
		payload = build_payload(doc, settings)
		reply = sandbox_reply(settings) if settings.sandbox_mode else post_to_fbr(payload, settings)
		invoice_no = check_reply(reply)
		qr_url = attach_qr_code(doc, invoice_no)
	except Exception as e:
		# Message only, never the headers: they carry the token.
		frappe.log_error(
			title=ERROR_TITLE,
			message=f"{type(e).__name__}: {e}\nInvoice: {docname}",
			reference_doctype="Sales Invoice",
			reference_name=docname,
		)
		doc.db_set("gic_fbr_sync_status", FBR_FAILED, update_modified=False)
		doc.add_comment("Info", _("FBR sync failed: {0}").format(e))
		return FBR_FAILED

	doc.db_set(
		{
			"gic_fbr_sync_status": FBR_SYNCED,
			"gic_fbr_invoice_no": invoice_no,
			"gic_fbr_qr_image": qr_url,
		},
		update_modified=False,
	)
	mode = _("sandbox") if settings.sandbox_mode else _("live")
	doc.add_comment("Info", _("Synced with FBR ({0}). FBR Invoice No: {1}").format(mode, invoice_no))
	return FBR_SYNCED


# ---------------------------------------------------------------- payload


def build_payload(doc, settings) -> dict:
	"""Sales Invoice -> PRAL Digital Invoicing JSON."""
	if not settings.ntn_number:
		raise ValueError("Seller NTN is missing in GIC FBR Settings")
	rate = sales_tax_rate(doc)
	buyer_ntn = re.sub(r"[\s-]", "", frappe.db.get_value("Customer", doc.customer, "tax_id") or "")
	province = settings.seller_province or "PUNJAB"

	return {
		"invoiceType": "Sale Invoice",
		"invoiceDate": str(getdate(doc.posting_date)),
		"sellerNTNCNIC": settings.ntn_number,
		"sellerBusinessName": doc.company,
		"sellerProvince": province,
		"sellerAddress": _plain(doc.get("company_address_display")) or doc.company,
		"buyerNTNCNIC": buyer_ntn,
		"buyerBusinessName": doc.customer_name,
		"buyerProvince": _buyer_province(doc) or province,
		"buyerAddress": _plain(doc.get("address_display")),
		"buyerRegistrationType": "Registered" if buyer_ntn else "Unregistered",
		"invoiceRefNo": "",
		"items": [_item(row, rate) for row in doc.items],
	}


def _item(row, rate: float) -> dict:
	value = flt(row.net_amount or row.amount, 2)
	tax = flt(value * rate / 100, 2)
	uom = row.stock_uom or row.uom
	return {
		"hsCode": frappe.db.get_value("Item", row.item_code, "customs_tariff_number") or "",
		"productDescription": row.item_name,
		"rate": f"{rate:g}%",
		"uoM": FBR_UOM.get(uom, uom),
		"quantity": flt(row.stock_qty or row.qty, 4),
		"totalValues": flt(value + tax, 2),
		"valueSalesExcludingST": value,
		"fixedNotifiedValueOrRetailPrice": 0,
		"salesTaxApplicable": tax,
		"salesTaxWithheldAtSource": 0,
		"extraTax": "",
		"furtherTax": 0,
		"sroScheduleNo": "",
		"fedPayable": 0,
		"discount": 0,
		"saleType": DEFAULT_SALE_TYPE,
		"sroItemSerialNo": "",
	}


def sales_tax_rate(doc) -> float:
	"""Sum of 'On Net Total' sales tax rates on the bill, leaving out withholding rows."""
	return flt(
		sum(
			flt(t.rate)
			for t in doc.get("taxes") or []
			if t.charge_type == "On Net Total"
			and not WITHHOLDING_PATTERN.search(f"{t.description or ''} {t.account_head or ''}")
		),
		2,
	)


def _plain(html: str | None) -> str:
	return re.sub(r"\s+", " ", strip_html((html or "").replace("<br>", ", "))).strip(" ,")


def _buyer_province(doc) -> str | None:
	if not doc.get("customer_address"):
		return None
	state = (frappe.db.get_value("Address", doc.customer_address, "state") or "").upper()
	options = frappe.get_meta(SETTINGS).get_field("seller_province").options.split("\n")
	return state if state in options else None


# ---------------------------------------------------------------- FBR reply


def sandbox_reply(settings) -> dict:
	"""What a valid FBR reply looks like, with a clearly fake invoice number."""
	invoice_no = f"{SANDBOX_PREFIX}{settings.ntn_number}DI{int(time.time() * 1000)}"
	return {
		"invoiceNumber": invoice_no,
		"dated": frappe.utils.now(),
		"validationResponse": {"statusCode": FBR_OK, "status": "Valid", "error": ""},
	}


def post_to_fbr(payload: dict, settings) -> dict:
	token = settings.get_password("pral_bearer_token", raise_exception=False)
	if not token:
		raise ValueError("PRAL Bearer Token is missing in GIC FBR Settings")
	response = requests.post(
		settings.fbr_api_url,
		json=payload,
		headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
		timeout=TIMEOUT_SECONDS,
	)
	response.raise_for_status()
	return response.json()


def check_reply(reply: dict) -> str:
	"""FBR invoice number from a valid reply; raises with FBR's own errors otherwise."""
	validation = reply.get("validationResponse") or {}
	if validation.get("statusCode") != FBR_OK:
		errors = [validation.get("error")] + [
			s.get("error") for s in validation.get("invoiceStatuses") or [] if s.get("error")
		]
		raise ValueError(
			"FBR rejected the invoice: " + ("; ".join(e for e in errors if e) or "no reason given")
		)
	invoice_no = reply.get("invoiceNumber")
	if not invoice_no:
		raise ValueError("FBR reply has no invoice number")
	return invoice_no


# ---------------------------------------------------------------- QR code


def attach_qr_code(doc, invoice_no: str) -> str:
	"""PNG QR of the FBR invoice number, attached to the bill. Returns the file URL.

	Public file: it only encodes the FBR invoice number, which is printed on the bill
	anyway, and PDF printing cannot load private images.
	"""
	import pyqrcode  # ships with Frappe (used for 2FA), so no extra dependency

	buffer = io.BytesIO()
	pyqrcode.create(invoice_no, error="M").png(buffer, scale=6, quiet_zone=2)
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"fbr-qr-{doc.name}.png",
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
			"attached_to_field": "gic_fbr_qr_image",
			"is_private": 0,
			"content": buffer.getvalue(),
		}
	).insert(ignore_permissions=True)
	return file.file_url
