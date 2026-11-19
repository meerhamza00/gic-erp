# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt

import re
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document


class GICFBRSettings(Document):
	def validate(self):
		self.ntn_number = re.sub(r"[\s-]", "", self.ntn_number or "")
		if self.ntn_number and not re.fullmatch(r"\d{7}|\d{13}", self.ntn_number):
			frappe.throw(_("NTN must be 7 digits, or a CNIC of 13 digits."), title=_("Invalid NTN / CNIC"))
		if self.fbr_api_url:
			self.fbr_api_url = self.fbr_api_url.strip()
			if urlparse(self.fbr_api_url).scheme != "https":
				frappe.throw(_("FBR API URL must start with https://"), title=_("Invalid URL"))
		if self.enabled and not self.ntn_number:
			frappe.throw(_("Enter your NTN before enabling FBR invoicing."))
		if self.enabled and not self.sandbox_mode:
			if not self.fbr_api_url:
				frappe.throw(_("Enter the FBR API URL before turning Sandbox Mode off."))
			if not self.get_password("pral_bearer_token", raise_exception=False):
				frappe.throw(_("Enter the PRAL Bearer Token before turning Sandbox Mode off."))
