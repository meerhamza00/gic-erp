# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gic_erp.services import fbr_sync
from gic_erp.setup.custom_fields import FBR_FAILED, FBR_NOT_APPLICABLE, FBR_PENDING, FBR_SYNCED, KACHA
from gic_erp.tests.test_kacha_pakka import ITEM, make_invoice, tax_template
from gic_erp.tests.utils import PREFIX, make_customer, make_item

test_ignore = ["Company", "Customer", "Item", "Sales Taxes and Charges Template", "Account"]

NTN = "1234567"
TOKEN = "pral-test-token-not-a-secret"
LIVE_URL = "https://gateway.example.test/di/postinvoicedata"
HS_CODE = "7323.9300"
BUYER = f"{PREFIX} FBR Buyer"
SYNC_JOB = "gic_erp.services.fbr_sync.sync_invoice_to_fbr"


def configure(enabled=1, sandbox=1, profile=1):
	frappe.db.set_single_value("GIC Industry Profile", "enable_fbr_invoicing", profile)
	settings = frappe.get_single("GIC FBR Settings")
	settings.update(
		{
			"enabled": enabled,
			"sandbox_mode": sandbox,
			"ntn_number": NTN,
			"seller_province": "PUNJAB",
			"fbr_api_url": LIVE_URL,
			"pral_bearer_token": TOKEN,
		}
	)
	settings.save(ignore_permissions=True)


def sync_calls(enqueue) -> list:
	"""Only the FBR jobs (the WhatsApp hook may queue its own)."""
	return [c for c in enqueue.call_args_list if c.args and c.args[0] == SYNC_JOB]


def fbr_reply(code="00", invoice_no="7000007DI1747119701593", error=""):
	response = MagicMock()
	response.raise_for_status.return_value = None
	response.json.return_value = {
		"invoiceNumber": invoice_no if code == "00" else None,
		"validationResponse": {
			"statusCode": code,
			"status": "Valid" if code == "00" else "Invalid",
			"error": error,
		},
	}
	return response


class TestFBRSync(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.db.set_single_value("GIC Industry Profile", "enable_kacha_pakka_mode", 1)
		if not frappe.db.exists("Customs Tariff Number", HS_CODE):
			frappe.get_doc({"doctype": "Customs Tariff Number", "tariff_number": HS_CODE}).insert(
				ignore_permissions=True
			)
		make_item(ITEM, is_stock_item=0)
		frappe.db.set_value("Item", ITEM, "customs_tariff_number", HS_CODE)
		frappe.db.set_value("Customer", make_customer(BUYER), "tax_id", "7654321")

	def setUp(self):
		configure()

	def tearDown(self):
		# Other test modules submit invoices too: leave FBR switched off for them.
		configure(enabled=0, profile=0)

	def submitted(self, mode=None, **kw):
		with patch("gic_erp.services.fbr_sync.frappe.enqueue") as enqueue:
			doc = make_invoice(mode or fbr_sync.PAKKA, submit=True, customer=BUYER, **kw)
		return doc, enqueue

	def test_payload_maps_items_tax_and_buyer(self):
		doc, _ = self.submitted(taxes_and_charges=tax_template())
		payload = fbr_sync.build_payload(doc, frappe.get_single("GIC FBR Settings"))
		self.assertEqual(payload["invoiceType"], "Sale Invoice")
		self.assertEqual(payload["sellerNTNCNIC"], NTN)
		self.assertEqual(payload["buyerNTNCNIC"], "7654321")
		self.assertEqual(payload["buyerRegistrationType"], "Registered")
		item = payload["items"][0]
		self.assertEqual(item["hsCode"], HS_CODE)
		self.assertEqual(item["rate"], "18%")
		self.assertEqual(item["quantity"], 10)
		self.assertEqual(item["valueSalesExcludingST"], 1000)
		self.assertEqual(item["salesTaxApplicable"], 180)
		self.assertEqual(item["totalValues"], 1180)

	def test_withholding_rows_are_not_sales_tax(self):
		doc = frappe._dict(
			taxes=[
				frappe._dict(charge_type="On Net Total", rate=18, description="GST 18%", account_head="GST"),
				frappe._dict(
					charge_type="On Net Total",
					rate=0.5,
					description="Withholding 236H (0.5%)",
					account_head="WHT",
				),
				frappe._dict(charge_type="Actual", rate=0, description="Freight", account_head="Freight"),
			]
		)
		self.assertEqual(fbr_sync.sales_tax_rate(doc), 18)

	def test_pakka_submit_queues_sync_and_marks_pending(self):
		doc, enqueue = self.submitted()
		calls = sync_calls(enqueue)
		self.assertEqual(len(calls), 1)
		self.assertEqual(calls[0].kwargs["docname"], doc.name)
		self.assertTrue(calls[0].kwargs["enqueue_after_commit"])
		self.assertEqual(frappe.db.get_value("Sales Invoice", doc.name, "gic_fbr_sync_status"), FBR_PENDING)

	def test_kacha_and_switched_off_are_not_sent(self):
		doc, enqueue = self.submitted(KACHA)
		self.assertFalse(sync_calls(enqueue))
		self.assertEqual(doc.gic_fbr_sync_status, FBR_NOT_APPLICABLE)
		configure(enabled=0)
		_, enqueue = self.submitted()
		self.assertFalse(sync_calls(enqueue))
		configure(profile=0)
		_, enqueue = self.submitted()
		self.assertFalse(sync_calls(enqueue))

	@patch("gic_erp.services.fbr_sync.requests.post")
	def test_sandbox_sync_attaches_qr_and_marks_synced(self, post):
		doc, _ = self.submitted()
		self.assertEqual(fbr_sync.sync_invoice_to_fbr(doc.name), FBR_SYNCED)
		post.assert_not_called()
		doc.reload()
		self.assertEqual(doc.gic_fbr_sync_status, FBR_SYNCED)
		self.assertTrue(doc.gic_fbr_invoice_no.startswith(f"SANDBOX-{NTN}DI"))
		file = frappe.get_doc("File", {"file_url": doc.gic_fbr_qr_image})
		self.assertEqual(file.attached_to_name, doc.name)
		self.assertEqual(file.attached_to_field, "gic_fbr_qr_image")
		self.assertTrue(file.get_content().startswith(b"\x89PNG"))
		# A second run does nothing: already synced.
		self.assertEqual(fbr_sync.sync_invoice_to_fbr(doc.name), FBR_SYNCED)
		self.assertEqual(
			frappe.db.count("File", {"attached_to_name": doc.name, "attached_to_field": "gic_fbr_qr_image"}),
			1,
		)

	@patch("gic_erp.services.fbr_sync.requests.post")
	def test_live_mode_posts_with_bearer_token(self, post):
		configure(sandbox=0)
		post.return_value = fbr_reply()
		doc, _ = self.submitted()
		self.assertEqual(fbr_sync.sync_invoice_to_fbr(doc.name), FBR_SYNCED)
		self.assertEqual(post.call_args.args[0], LIVE_URL)
		self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], f"Bearer {TOKEN}")
		self.assertEqual(post.call_args.kwargs["timeout"], fbr_sync.TIMEOUT_SECONDS)
		self.assertEqual(post.call_args.kwargs["json"]["items"][0]["hsCode"], HS_CODE)
		self.assertEqual(
			frappe.db.get_value("Sales Invoice", doc.name, "gic_fbr_invoice_no"), "7000007DI1747119701593"
		)

	@patch("gic_erp.services.fbr_sync.requests.post")
	def test_rejection_marks_failed_and_logs_without_token(self, post):
		configure(sandbox=0)
		post.return_value = fbr_reply(code="0052", error="Invalid HS Code")
		doc, _ = self.submitted()
		self.assertEqual(fbr_sync.sync_invoice_to_fbr(doc.name), FBR_FAILED)
		self.assertEqual(frappe.db.get_value("Sales Invoice", doc.name, "gic_fbr_sync_status"), FBR_FAILED)
		log = frappe.get_all(
			"Error Log",
			{"method": fbr_sync.ERROR_TITLE, "reference_name": doc.name},
			["error"],
			limit=1,
		)[0]
		self.assertIn("Invalid HS Code", log.error)
		self.assertNotIn(TOKEN, log.error)

	@patch("gic_erp.services.fbr_sync.requests.post")
	def test_retry_requeues_a_failed_bill(self, post):
		configure(sandbox=0)
		post.return_value = fbr_reply(code="0052", error="Invalid HS Code")
		doc, _ = self.submitted()
		fbr_sync.sync_invoice_to_fbr(doc.name)
		with patch("gic_erp.services.fbr_sync.frappe.enqueue") as enqueue:
			fbr_sync.retry_fbr_sync(doc.name)
		self.assertEqual(len(sync_calls(enqueue)), 1)
		self.assertEqual(frappe.db.get_value("Sales Invoice", doc.name, "gic_fbr_sync_status"), FBR_PENDING)

	def test_settings_validation(self):
		settings = frappe.get_single("GIC FBR Settings")
		settings.ntn_number = "12345"
		self.assertRaises(frappe.ValidationError, settings.save)
		settings.reload()
		settings.fbr_api_url = "http://insecure.example.test"
		self.assertRaises(frappe.ValidationError, settings.save)
		settings.reload()
		settings.ntn_number = "12345-6789012-3"  # CNIC with dashes is accepted and cleaned
		settings.save()
		self.assertEqual(settings.ntn_number, "1234567890123")
