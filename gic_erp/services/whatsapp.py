# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""WhatsApp messages to customers on Sales Invoice and Payment Entry submit.

Delivery goes through a generic webhook (GIC WhatsApp Settings): GICNEXT POSTs JSON
{to, message, reference_doctype, reference_name} with a Bearer token. An n8n workflow or
any gateway turns that into a WhatsApp message, so the provider can change without
touching the ERP.

Sending never blocks a bill: the submit hook only builds the text and queues the job
after the database commit. Failures land in Error Log as "GIC WhatsApp Error".
"""

import re

import frappe
import requests
from frappe import _
from frappe.utils import flt, fmt_money, formatdate

SETTINGS = "GIC WhatsApp Settings"
PROFILE = "GIC Industry Profile"
TIMEOUT_SECONDS = 10
ERROR_TITLE = "GIC WhatsApp Error"


# ---------------------------------------------------------------- sending


def normalize_pk_mobile(number: str | None) -> str | None:
	"""Pakistani mobile -> international digits (923001234567). None if not a PK mobile."""
	digits = re.sub(r"\D", "", number or "")
	if digits.startswith("0092"):
		digits = digits[2:]
	if digits.startswith("03") and len(digits) == 11:
		digits = "92" + digits[1:]
	elif digits.startswith("3") and len(digits) == 10:
		digits = "92" + digits
	return digits if re.fullmatch(r"923\d{9}", digits) else None


def whatsapp_active(event_field: str | None = None) -> bool:
	"""Profile switch AND settings switch (AND the per-event switch, when given)."""
	if not frappe.db.get_single_value(PROFILE, "enable_whatsapp_alerts"):
		return False
	if not frappe.db.get_single_value(SETTINGS, "enabled"):
		return False
	return bool(frappe.db.get_single_value(SETTINGS, event_field)) if event_field else True


def send_whatsapp_message(
	mobile_no: str,
	message_text: str,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	raise_on_error: bool = False,
) -> bool:
	"""POST one message to the gateway. Returns True when the gateway accepted it."""
	try:
		if not whatsapp_active():
			return False
		to = normalize_pk_mobile(mobile_no)
		if not to:
			raise ValueError(f"Not a Pakistani mobile number: {mobile_no!r}")

		settings = frappe.get_single(SETTINGS)
		headers = {"Content-Type": "application/json"}
		token = settings.get_password("api_token", raise_exception=False)
		if token:
			headers["Authorization"] = f"Bearer {token}"

		response = requests.post(
			settings.api_endpoint,
			json={
				"to": to,
				"message": message_text,
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
			},
			headers=headers,
			timeout=TIMEOUT_SECONDS,
		)
		response.raise_for_status()
	except Exception as e:
		# Message only, never the headers: they carry the token.
		frappe.log_error(
			title=ERROR_TITLE,
			message=f"{type(e).__name__}: {e}\nTo: {mobile_no}\nReference: {reference_doctype} {reference_name}",
			reference_doctype=reference_doctype,
			reference_name=reference_name,
		)
		if raise_on_error:
			frappe.throw(_("WhatsApp message not sent: {0}").format(e), title=_("WhatsApp Error"))
		return False

	if reference_doctype and reference_name:
		frappe.get_doc(reference_doctype, reference_name).add_comment(
			"Info", _("WhatsApp message sent to {0}").format(to)
		)
	return True


def _queue(mobile_no: str, message: str, doc):
	frappe.enqueue(
		"gic_erp.services.whatsapp.send_whatsapp_message",
		queue="short",
		enqueue_after_commit=True,
		mobile_no=mobile_no,
		message_text=message,
		reference_doctype=doc.doctype,
		reference_name=doc.name,
	)


# ---------------------------------------------------------------- balances


def customer_khata(customer: str, company: str) -> float:
	"""Customer's total outstanding with this company (all bills minus all payments)."""
	from erpnext.accounts.utils import get_balance_on

	return flt(get_balance_on(party_type="Customer", party=customer, company=company))


def customer_mobile(customer: str, fallback: str | None = None) -> str | None:
	return fallback or frappe.db.get_value("Customer", customer, "mobile_no")


def _money(amount, currency) -> str:
	return fmt_money(flt(amount), currency=currency)


# ---------------------------------------------------------------- messages


def invoice_message(doc, khata: float) -> str:
	"""Urdu block, then English block. Kacha bills are called a memo, not a bill."""
	kacha = doc.get("gic_bill_mode") == "Kacha (Estimate Slip)"
	amount = _money(doc.rounded_total or doc.grand_total, doc.currency)
	due = _money(doc.outstanding_amount, doc.currency)
	total = _money(khata, doc.currency)
	date = formatdate(doc.posting_date)
	ur_label, en_label = ("میمو نمبر", "Memo #") if kacha else ("بل نمبر", "Bill #")
	return "\n".join(
		[
			f"السلام علیکم {doc.customer_name}",
			f"{ur_label}: {doc.name} ({date})",
			f"رقم: {amount}",
			f"اس بل کا بقایا: {due}",
			f"کھاتے کا کل بقایا: {total}",
			"",
			f"Dear {doc.customer_name},",
			f"{en_label} {doc.name} ({date})",
			f"Amount: {amount}",
			f"Due on this bill: {due}",
			f"Total balance (khata): {total}",
			"",
			f"شکریہ / Thank you — {doc.company}",
		]
	)


def payment_message(doc, khata: float, bills_due: float | None) -> str:
	received = _money(doc.paid_amount, doc.paid_from_account_currency or doc.paid_to_account_currency)
	total = _money(khata, doc.paid_to_account_currency)
	date = formatdate(doc.posting_date)
	lines_ur = [
		f"السلام علیکم {doc.party_name}",
		f"رسید نمبر: {doc.name} ({date})",
		f"وصول شدہ رقم: {received}",
	]
	lines_en = [
		f"Dear {doc.party_name},",
		f"Receipt # {doc.name} ({date})",
		f"Amount received: {received}",
	]
	if bills_due is not None:
		due = _money(bills_due, doc.paid_to_account_currency)
		lines_ur.append(f"متعلقہ بلوں کا بقایا: {due}")
		lines_en.append(f"Still due on these bills: {due}")
	lines_ur.append(f"کھاتے کا کل بقایا: {total}")
	lines_en.append(f"Total balance (khata): {total}")
	return "\n".join([*lines_ur, "", *lines_en, "", f"شکریہ / Thank you — {doc.company}"])


# ---------------------------------------------------------------- hooks


def on_sales_invoice_submit(doc, method=None):
	if doc.get("is_return") or not whatsapp_active("send_on_invoice"):
		return
	mobile = customer_mobile(doc.customer, doc.get("contact_mobile"))
	if not normalize_pk_mobile(mobile):
		return  # no usable number: nothing to send, nothing to log
	_queue(mobile, invoice_message(doc, customer_khata(doc.customer, doc.company)), doc)


def on_payment_entry_submit(doc, method=None):
	if doc.payment_type != "Receive" or doc.party_type != "Customer":
		return
	if not whatsapp_active("send_on_payment"):
		return
	mobile = customer_mobile(doc.party, doc.get("contact_mobile"))
	if not normalize_pk_mobile(mobile):
		return
	invoices = [r.reference_name for r in doc.references if r.reference_doctype == "Sales Invoice"]
	bills_due = (
		sum(flt(frappe.db.get_value("Sales Invoice", name, "outstanding_amount")) for name in invoices)
		if invoices
		else None
	)
	_queue(mobile, payment_message(doc, customer_khata(doc.party, doc.company), bills_due), doc)
