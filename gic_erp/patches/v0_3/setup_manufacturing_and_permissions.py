# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""Milestone 3: foundry fields on Stock Entry and GIC role permissions for existing sites."""

from gic_erp.install import setup_manufacturing_and_permissions


def execute():
	setup_manufacturing_and_permissions()
