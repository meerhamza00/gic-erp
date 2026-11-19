# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""Milestone 4: Kacha / Pakka bill type on Sales Invoice for existing sites."""

from gic_erp.install import setup_billing


def execute():
	setup_billing()
