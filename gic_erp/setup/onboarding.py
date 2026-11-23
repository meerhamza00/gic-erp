# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""Client onboarding (Milestone 6): turn a fresh site into a ready GICNEXT company.

Called by deploy/server/onboard-client.sh right after `bench new-site`:

    bench --site erp.acme.pk execute gic_erp.setup.onboarding.setup_client_from_env
    (GIC_ONBOARD_COMPANY, GIC_ONBOARD_BLUEPRINT, GIC_ONBOARD_FY_START_MONTH in the environment)

It completes ERPNext's setup wizard for a Pakistani company (PKR, Asia/Karachi, fiscal
year July-June by default), saves the GIC Industry Profile for the blueprint's business
type, and loads the industry blueprint. Safe to run again on the same site and company.

Not whitelisted: only the server (bench execute) can call it.
"""

import datetime
import os
import re

import frappe
from frappe import _

from gic_erp.seed.blueprints import BLUEPRINTS, BUSINESS_TYPE_BLUEPRINT, apply_industry_blueprint

PROFILE = "GIC Industry Profile"
BLUEPRINT_BUSINESS_TYPE = {blueprint: btype for btype, blueprint in BUSINESS_TYPE_BLUEPRINT.items()}
DEFAULT_FY_START_MONTH = 7  # Pakistan's tax year runs July to June
COMPANY_NAME_RE = re.compile(r"^[\w&.,'()\- ]{2,100}$")


def fiscal_year(today: datetime.date | None = None, start_month: int = DEFAULT_FY_START_MONTH):
	"""(start, end) of the fiscal year that contains `today`."""
	today = today or datetime.date.today()
	year = today.year if today.month >= start_month else today.year - 1
	start = datetime.date(year, start_month, 1)
	end = datetime.date(year + 1, start_month, 1) - datetime.timedelta(days=1)
	return start, end


def company_abbr(company_name: str) -> str:
	"""Initials of the words (max 5), e.g. 'Acme Cookware Pvt Ltd' -> 'ACPL'."""
	words = re.findall(r"[A-Za-z0-9]+", company_name)
	abbr = "".join(w[0] for w in words).upper()[:5]
	if len(abbr) < 2:
		abbr = "".join(words).upper()[:3]
	return abbr or "CO"


def validate_inputs(company_name: str, blueprint: str, fy_start_month: int) -> str:
	company_name = (company_name or "").strip()
	if not COMPANY_NAME_RE.match(company_name):
		frappe.throw(
			_("Company name must be 2 to 100 letters, digits, spaces or & . , ' ( ) -"),
			title=_("Invalid Company Name"),
		)
	if blueprint not in BLUEPRINTS:
		frappe.throw(
			_("Blueprint must be one of: {0}").format(", ".join(BLUEPRINTS)), title=_("Unknown Blueprint")
		)
	if not 1 <= int(fy_start_month) <= 12:
		frappe.throw(_("Fiscal year start month must be 1 to 12."), title=_("Invalid Fiscal Year"))
	return company_name


def complete_setup_wizard(company_name: str, fy_start_month: int):
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	start, end = fiscal_year(start_month=fy_start_month)
	setup_complete(
		{
			"currency": "PKR",
			"country": "Pakistan",
			"timezone": "Asia/Karachi",
			"language": "english",
			"full_name": "Administrator",
			# No email: no extra user is created; the client signs in as Administrator.
			"company_name": company_name,
			"company_abbr": company_abbr(company_name),
			"company_tagline": company_name,
			"chart_of_accounts": "Standard",
			"fy_start_date": str(start),
			"fy_end_date": str(end),
		}
	)
	if not frappe.is_setup_complete():
		frappe.throw(_("ERPNext setup did not complete. See the Error Log."), title=_("Setup Failed"))


def save_industry_profile(company_name: str, blueprint: str):
	profile = frappe.get_single(PROFILE)
	profile.business_type = BLUEPRINT_BUSINESS_TYPE[blueprint]
	profile.company = company_name
	profile.save(ignore_permissions=True)


def setup_client(company_name: str, blueprint: str, fy_start_month: int = DEFAULT_FY_START_MONTH) -> dict:
	"""Setup wizard + Industry Profile + blueprint for this site's one company."""
	company_name = validate_inputs(company_name, blueprint, fy_start_month)
	existing = frappe.get_all("Company", pluck="name")
	if existing and company_name not in existing:
		frappe.throw(
			_("This site already has company {0}. One client company per site.").format(existing[0]),
			title=_("Site Already Set Up"),
		)
	if not existing:
		complete_setup_wizard(company_name, int(fy_start_month))

	save_industry_profile(company_name, blueprint)
	seeded = apply_industry_blueprint(company_name, blueprint)
	if not frappe.flags.in_test:
		frappe.db.commit()  # nosemgrep: bench execute does not commit for us

	start, end = fiscal_year(start_month=int(fy_start_month))
	return {
		"company": company_name,
		"abbr": frappe.db.get_value("Company", company_name, "abbr"),
		"business_type": BLUEPRINT_BUSINESS_TYPE[blueprint],
		"blueprint": blueprint,
		"fiscal_year": f"{start} to {end}",
		"created": len(seeded["created"]),
		"already_there": len(seeded["already_there"]),
		"setup_wizard": "skipped (company existed)" if existing else "completed",
	}


def setup_client_from_env() -> dict:
	"""Entry point for onboard-client.sh: inputs come from the environment, so company
	names with spaces or quotes never pass through shell or JSON quoting."""
	return setup_client(
		os.environ.get("GIC_ONBOARD_COMPANY", ""),
		os.environ.get("GIC_ONBOARD_BLUEPRINT", ""),
		int(os.environ.get("GIC_ONBOARD_FY_START_MONTH") or DEFAULT_FY_START_MONTH),
	)
