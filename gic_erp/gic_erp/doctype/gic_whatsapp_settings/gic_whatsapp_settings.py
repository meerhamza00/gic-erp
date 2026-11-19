# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt

from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document


class GICWhatsAppSettings(Document):
	def validate(self):
		if self.api_endpoint:
			self.api_endpoint = self.api_endpoint.strip()
			url = urlparse(self.api_endpoint)
			if url.scheme not in ("http", "https") or not url.netloc:
				frappe.throw(_("Gateway URL must start with https:// or http://"), title=_("Invalid URL"))
		if self.enabled and not self.api_endpoint:
			frappe.throw(_("Enter the Gateway URL before enabling WhatsApp."))


@frappe.whitelist()
def send_test_message():
	"""'Send Test Message' button. Sends now (not queued) so the admin sees the result."""
	frappe.only_for("System Manager")
	from gic_erp.services.whatsapp import send_whatsapp_message

	settings = frappe.get_single("GIC WhatsApp Settings")
	if not settings.test_mobile:
		frappe.throw(_("Enter a Test Mobile No and save first."))
	ok = send_whatsapp_message(
		settings.test_mobile,
		_("GICNEXT test message. WhatsApp alerts are working."),
		raise_on_error=True,
	)
	return {"sent": ok}
