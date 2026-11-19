# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt

from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests.utils import FrappeTestCase

from gic_erp.services import whatsapp
from gic_erp.setup.custom_fields import KACHA
from gic_erp.tests.test_kacha_pakka import ITEM, make_invoice
from gic_erp.tests.utils import make_customer, make_item

test_ignore = ["Company", "Customer", "Item", "Sales Taxes and Charges Template", "Account"]

ENDPOINT = "https://gateway.example.test/hook"
TOKEN = "test-token-not-a-secret"
MOBILE = "0300-1234567"


def configure(enabled=1, on_invoice=1, on_payment=1, profile=1):
	frappe.db.set_single_value("GIC Industry Profile", "enable_whatsapp_alerts", profile)
	settings = frappe.get_single("GIC WhatsApp Settings")
	settings.update(
		{
			"enabled": enabled,
			"api_endpoint": ENDPOINT,
			"api_token": TOKEN,
			"send_on_invoice": on_invoice,
			"send_on_payment": on_payment,
		}
	)
	settings.save(ignore_permissions=True)


def ok_response():
	response = MagicMock()
	response.raise_for_status.return_value = None
	return response


class TestWhatsAppSend(FrappeTestCase):
	def setUp(self):
		configure()

	def test_normalize_pk_mobile(self):
		cases = {
			"03001234567": "923001234567",
			"0300-1234567": "923001234567",
			"+92 300 1234567": "923001234567",
			"00923001234567": "923001234567",
			"3001234567": "923001234567",
			"042-35761234": None,  # landline
			"": None,
			None: None,
		}
		for given, expected in cases.items():
			self.assertEqual(whatsapp.normalize_pk_mobile(given), expected, given)

	@patch("gic_erp.services.whatsapp.requests.post")
	def test_posts_json_with_bearer_token_and_timeout(self, post):
		post.return_value = ok_response()
		self.assertTrue(whatsapp.send_whatsapp_message(MOBILE, "Salam"))
		_, kwargs = post.call_args
		self.assertEqual(post.call_args.args[0], ENDPOINT)
		self.assertEqual(kwargs["json"]["to"], "923001234567")
		self.assertEqual(kwargs["json"]["message"], "Salam")
		self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {TOKEN}")
		self.assertEqual(kwargs["timeout"], 10)

	@patch("gic_erp.services.whatsapp.requests.post")
	def test_failure_is_logged_without_the_token(self, post):
		post.side_effect = requests.Timeout("gateway slow")
		before = frappe.db.count("Error Log", {"method": whatsapp.ERROR_TITLE})
		self.assertFalse(whatsapp.send_whatsapp_message(MOBILE, "Salam"))
		logs = frappe.get_all(
			"Error Log", {"method": whatsapp.ERROR_TITLE}, ["error"], order_by="creation desc", limit=1
		)
		self.assertEqual(frappe.db.count("Error Log", {"method": whatsapp.ERROR_TITLE}), before + 1)
		self.assertIn("gateway slow", logs[0].error)
		self.assertNotIn(TOKEN, logs[0].error)

	@patch("gic_erp.services.whatsapp.requests.post")
	def test_http_error_counts_as_failure(self, post):
		response = ok_response()
		response.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")
		post.return_value = response
		self.assertFalse(whatsapp.send_whatsapp_message(MOBILE, "Salam"))

	@patch("gic_erp.services.whatsapp.requests.post")
	def test_nothing_sent_when_switched_off(self, post):
		configure(enabled=0)
		self.assertFalse(whatsapp.send_whatsapp_message(MOBILE, "Salam"))
		configure(profile=0)
		self.assertFalse(whatsapp.send_whatsapp_message(MOBILE, "Salam"))
		post.assert_not_called()

	@patch("gic_erp.services.whatsapp.requests.post")
	def test_bad_number_logged_not_sent(self, post):
		self.assertFalse(whatsapp.send_whatsapp_message("12345", "Salam"))
		post.assert_not_called()

	def test_settings_reject_non_http_url(self):
		settings = frappe.get_single("GIC WhatsApp Settings")
		settings.api_endpoint = "ftp://example.test"
		self.assertRaises(frappe.ValidationError, settings.save)


class TestWhatsAppHooks(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_item(ITEM, is_stock_item=0)
		frappe.db.set_value("Customer", make_customer(), "mobile_no", MOBILE)
		frappe.db.set_single_value("GIC Industry Profile", "enable_kacha_pakka_mode", 1)

	def setUp(self):
		configure()

	@patch("gic_erp.services.whatsapp.frappe.enqueue")
	def test_invoice_submit_queues_bilingual_message_after_commit(self, enqueue):
		doc = make_invoice(submit=True)
		enqueue.assert_called_once()
		kwargs = enqueue.call_args.kwargs
		self.assertTrue(kwargs["enqueue_after_commit"])
		self.assertEqual(kwargs["reference_name"], doc.name)
		message = kwargs["message_text"]
		for part in (doc.name, "Bill #", "بل نمبر", "Due on this bill", "Total balance (khata)", "1,000"):
			self.assertIn(part, message)

	@patch("gic_erp.services.whatsapp.frappe.enqueue")
	def test_kacha_message_says_memo(self, enqueue):
		make_invoice(KACHA, submit=True)
		message = enqueue.call_args.kwargs["message_text"]
		self.assertIn("Memo #", message)
		self.assertNotIn("Bill #", message)

	@patch("gic_erp.services.whatsapp.frappe.enqueue")
	def test_not_queued_when_invoice_alerts_off(self, enqueue):
		configure(on_invoice=0)
		make_invoice(submit=True)
		enqueue.assert_not_called()

	@patch("gic_erp.services.whatsapp.frappe.enqueue")
	def test_payment_queues_receipt_with_remaining_due(self, enqueue):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		invoice = make_invoice(submit=True)
		enqueue.reset_mock()
		payment = get_payment_entry("Sales Invoice", invoice.name)
		payment.paid_amount = payment.received_amount = 400
		payment.references[0].allocated_amount = 400
		payment.reference_no, payment.reference_date = "TEST-1", payment.posting_date
		payment.insert()
		payment.submit()
		enqueue.assert_called_once()
		message = enqueue.call_args.kwargs["message_text"]
		for part in (payment.name, "Amount received", "400", "Still due on these bills", "600"):
			self.assertIn(part, message)

	@patch("gic_erp.services.whatsapp.frappe.enqueue")
	def test_customer_without_mobile_is_skipped(self, enqueue):
		customer = make_customer(f"{make_customer()} No Mobile")
		frappe.db.set_value("Customer", customer, "mobile_no", None)
		make_invoice(submit=True, customer=customer)
		enqueue.assert_not_called()
