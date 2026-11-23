# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt

import datetime
import os
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gic_erp.seed import blueprints
from gic_erp.setup import onboarding
from gic_erp.tests.utils import company

test_ignore = ["Company", "Customer", "Item", "Account", "BOM", "Customer Group"]
SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "server" / "onboard-client.sh"
PROFILE_FIELDS = (
	"business_type",
	"company",
	"enable_fbr_invoicing",
	"enable_kacha_pakka_mode",
	"enable_thekedar_payroll",
	"enable_scrap_tracking",
)


class TestOnboardingHelpers(FrappeTestCase):
	def test_fiscal_year_july_to_june(self):
		self.assertEqual(
			onboarding.fiscal_year(datetime.date(2026, 11, 20)),
			(datetime.date(2026, 7, 1), datetime.date(2027, 6, 30)),
		)
		self.assertEqual(
			onboarding.fiscal_year(datetime.date(2026, 3, 1)),
			(datetime.date(2025, 7, 1), datetime.date(2026, 6, 30)),
		)

	def test_fiscal_year_calendar(self):
		self.assertEqual(
			onboarding.fiscal_year(datetime.date(2026, 11, 20), start_month=1),
			(datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)),
		)

	def test_company_abbr(self):
		self.assertEqual(onboarding.company_abbr("Acme Cookware Pvt Ltd"), "ACPL")
		self.assertEqual(onboarding.company_abbr("Al-Noor Rice Traders & Co"), "ANRTC")
		self.assertEqual(onboarding.company_abbr("Zed"), "ZED")

	def test_every_blueprint_has_a_business_type(self):
		for blueprint in blueprints.BLUEPRINTS:
			self.assertIn(blueprint, onboarding.BLUEPRINT_BUSINESS_TYPE)

	def test_shell_script_lists_every_blueprint(self):
		# onboard-client.sh checks the blueprint before it creates a site; keep the lists in step.
		text = SCRIPT.read_text()
		for blueprint in blueprints.BLUEPRINTS:
			self.assertIn(f'"{blueprint}"', text, f"{blueprint} missing from {SCRIPT.name}")


class TestSetupClient(FrappeTestCase):
	"""Runs on the test site, which already has the test company from before_tests."""

	def setUp(self):
		profile = frappe.get_single(onboarding.PROFILE)
		self.saved_profile = {f: profile.get(f) for f in PROFILE_FIELDS}
		self.default_group = frappe.db.get_single_value("Selling Settings", "customer_group")

	def tearDown(self):
		profile = frappe.get_single(onboarding.PROFILE)
		profile.update(self.saved_profile)
		if profile.business_type:
			profile.save(ignore_permissions=True)
		frappe.db.set_single_value("Selling Settings", "customer_group", self.default_group)

	def test_rejects_bad_inputs(self):
		for name, blueprint, month in (
			("", blueprints.FOUNDRY, 7),
			("<script>", blueprints.FOUNDRY, 7),
			("A" * 101, blueprints.FOUNDRY, 7),
			(company(), "Bakery", 7),
			(company(), blueprints.FOUNDRY, 13),
		):
			with self.subTest(name=name[:20], blueprint=blueprint, month=month):
				self.assertRaises(frappe.ValidationError, onboarding.setup_client, name, blueprint, month)

	def test_refuses_a_second_company(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			onboarding.setup_client("Another Client Ltd", blueprints.FOUNDRY)
		self.assertIn("already has company", str(ctx.exception))
		self.assertFalse(frappe.db.exists("Company", "Another Client Ltd"))

	def test_rerun_on_same_company_skips_wizard(self):
		with patch.object(onboarding, "complete_setup_wizard") as wizard:
			result = onboarding.setup_client(company(), blueprints.MANDI)
		wizard.assert_not_called()
		self.assertEqual(result["setup_wizard"], "skipped (company existed)")
		self.assertEqual(result["business_type"], "Wholesale & Mandi Trader")
		profile = frappe.get_single(onboarding.PROFILE)
		self.assertEqual(profile.business_type, "Wholesale & Mandi Trader")
		self.assertEqual(profile.company, company())
		self.assertTrue(profile.enable_kacha_pakka_mode)
		self.assertTrue(frappe.db.exists("Item", "Super Kernel Basmati Rice"))

	def test_new_site_runs_wizard_with_pakistani_defaults(self):
		with (
			patch.object(onboarding.frappe, "get_all", return_value=[]),
			patch("frappe.desk.page.setup_wizard.setup_wizard.setup_complete") as setup_complete,
			patch.object(onboarding.frappe, "is_setup_complete", return_value=True),
			patch.object(onboarding, "save_industry_profile"),
			patch.object(
				onboarding, "apply_industry_blueprint", return_value={"created": [1], "already_there": []}
			),
		):
			result = onboarding.setup_client("Acme Cookware Pvt Ltd", blueprints.FOUNDRY)
		args = setup_complete.call_args.args[0]
		self.assertEqual(
			(args["currency"], args["country"], args["timezone"]), ("PKR", "Pakistan", "Asia/Karachi")
		)
		self.assertEqual(args["company_abbr"], "ACPL")
		self.assertNotIn("email", args)
		self.assertTrue(args["fy_start_date"].endswith("-07-01"))
		self.assertTrue(args["fy_end_date"].endswith("-06-30"))
		self.assertEqual(result["setup_wizard"], "completed")

	def test_wizard_failure_is_reported(self):
		with (
			patch("frappe.desk.page.setup_wizard.setup_wizard.setup_complete"),
			patch.object(onboarding.frappe, "is_setup_complete", return_value=False),
		):
			self.assertRaises(frappe.ValidationError, onboarding.complete_setup_wizard, "Acme Ltd", 7)

	def test_from_env(self):
		env = {
			"GIC_ONBOARD_COMPANY": company(),
			"GIC_ONBOARD_BLUEPRINT": blueprints.SANITARY,
			"GIC_ONBOARD_FY_START_MONTH": "7",
		}
		with patch.dict(os.environ, env):
			result = onboarding.setup_client_from_env()
		self.assertEqual(result["blueprint"], blueprints.SANITARY)
