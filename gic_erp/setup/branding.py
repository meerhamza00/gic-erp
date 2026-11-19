# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""GICNEXT product branding: name, logos, favicon, help menu, email footer, letterhead.

Everything is stored in standard settings records or shipped as app assets and hooks,
so ERPNext and Frappe files stay untouched and upgrades keep working. Idempotent: runs
on install, from a patch, and after every migrate.
"""

import frappe

PRODUCT_NAME = "GICNEXT"
ASSETS = "/assets/gic_erp/images"
LOGO = f"{ASSETS}/gicnext-logo.png"
FAVICON = f"{ASSETS}/gicnext-favicon.png"
SPLASH = f"{ASSETS}/gicnext-splash.png"

# Help-menu links that point users at Frappe/ERPNext websites. Hidden, never deleted:
# Navbar Settings refuses deletion of standard items.
HIDDEN_HELP_ITEMS = ("Documentation", "User Forum", "Frappe School", "Report an Issue", "Frappe Support")

LETTER_HEAD_NAME = "GICNEXT Standard"


def apply_branding():
	_set_product_name_and_logos()
	_hide_vendor_help_links()
	# Drops ERPNext's "Sent via ERPNext" line from outgoing emails.
	frappe.db.set_default("disable_standard_email_footer", 1)
	ensure_letter_head()
	frappe.clear_cache()


def _set_product_name_and_logos():
	# set_single_value: avoids running the settings' full validate/on_update for a few fields.
	frappe.db.set_single_value("System Settings", "app_name", PRODUCT_NAME)
	frappe.db.set_single_value(
		"Website Settings",
		{"app_name": PRODUCT_NAME, "favicon": FAVICON, "splash_image": SPLASH},
	)
	# Navbar logo. Website Settings.app_logo stays empty so this one is used everywhere.
	frappe.db.set_single_value("Navbar Settings", "app_logo", LOGO)


def _hide_vendor_help_links():
	navbar = frappe.get_single("Navbar Settings")
	changed = False
	for item in navbar.help_dropdown:
		if item.item_label in HIDDEN_HELP_ITEMS and not item.hidden:
			item.hidden = 1
			changed = True
	if changed:
		navbar.flags.ignore_permissions = True
		navbar.save()


def ensure_letter_head():
	"""Default letterhead for invoices and estimates.

	Shows the SME's own company (taken from the printed document), never the GIC logo:
	the bill belongs to the client. GICNEXT appears only as a small footer credit.
	"""
	values = {
		"letter_head_name": LETTER_HEAD_NAME,
		"source": "HTML",
		"footer_source": "HTML",
		"content": LETTER_HEAD_HTML,
		"footer": LETTER_FOOT_HTML,
	}
	if frappe.db.exists("Letter Head", LETTER_HEAD_NAME):
		doc = frappe.get_doc("Letter Head", LETTER_HEAD_NAME)
		if doc.content == LETTER_HEAD_HTML and doc.footer == LETTER_FOOT_HTML:
			return doc.name
		doc.update(values)
	else:
		doc = frappe.get_doc({"doctype": "Letter Head", **values})
		# Become the default only if the site has none, so a client's own letterhead wins.
		doc.is_default = 0 if frappe.db.exists("Letter Head", {"is_default": 1}) else 1
	doc.flags.ignore_permissions = True
	doc.save()
	return doc.name


# Written in the form Frappe's HTML sanitizer stores (single-quoted style attributes),
# so the unchanged check in ensure_letter_head() holds.
# Rendered with the printed document as `doc`. Only Company fields are read, so it also
# works for documents without a customer (e.g. Stock Entry).
LETTER_HEAD_HTML = """\
{%- set co = frappe.db.get_value("Company", doc.company,
	["company_name", "phone_no", "email", "tax_id", "website"], as_dict=True) if doc and doc.company else None -%}
<div style='font-family: "Plus Jakarta Sans", Arial, sans-serif; border-top: 4px solid #1C119C;
	border-image: linear-gradient(90deg, #1C119C, #088516) 1; padding-top: 10px;'>
	<div style="font-size: 20px; font-weight: 800; color: #1C119C;">
		{{ co.company_name if co else (doc.company if doc else "") }}
	</div>
	{%- if co %}
	<div style="font-size: 10px; color: #64748B; margin-top: 2px;">
		{{ [("Phone: " ~ co.phone_no) if co.phone_no else "", co.email or "", co.website or "",
			("NTN: " ~ co.tax_id) if co.tax_id else ""] | select | join("  ·  ") }}
	</div>
	{%- endif %}
</div>
"""

LETTER_FOOT_HTML = """\
<div style='font-family: "Plus Jakarta Sans", Arial, sans-serif; font-size: 8px; color: #94A3B8;
	text-align: right; border-top: 0.5px solid #E2E8F0; padding-top: 4px;'>
	Powered by <b style="color: #088516;">GIC</b><b style="color: #1C119C;">NEXT</b>
	· Gujranwala Incubation Center
</div>
"""
