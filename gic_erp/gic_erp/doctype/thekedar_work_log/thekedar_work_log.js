// Copyright (c) 2026, Gujranwala Incubation Center and contributors
// For license information, please see license.txt

frappe.ui.form.on("Thekedar Work Log", {
	setup(frm) {
		frm.set_query("contractor", () => ({ filters: { disabled: 0 } }));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
	},

	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.purchase_invoice) {
			frm.add_custom_button(__("Open Purchase Invoice"), () =>
				frappe.set_route("Form", "Purchase Invoice", frm.doc.purchase_invoice)
			);
		}
	},

	quantity_completed: calculate_total,
	rate_per_unit: calculate_total,
});

function calculate_total(frm) {
	frm.set_value(
		"total_payable",
		flt(frm.doc.quantity_completed) * flt(frm.doc.rate_per_unit)
	);
}
