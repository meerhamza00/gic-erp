// Copyright (c) 2026, Gujranwala Incubation Center and contributors
// For license information, please see license.txt

frappe.ui.form.on("GIC Industry Profile", {
	refresh(frm) {
		if (!frm.doc.business_type) {
			frm.dashboard.set_headline(
				__("Choose your Business Type and Company, then Save to set up GIC-ERP.")
			);
			return;
		}

		frm.add_custom_button(__("Re-apply Screen Visibility"), () => {
			frappe.call({
				method: "gic_erp.gic_erp.doctype.gic_industry_profile.gic_industry_profile.reapply_visibility",
				freeze: true,
				freeze_message: __("Applying..."),
				callback(r) {
					if (r.exc) return;
					frappe.show_alert({ message: __("Screen visibility applied"), indicator: "green" });
					frm.reload_doc();
				},
				error() {
					frappe.msgprint({
						title: __("Could not apply"),
						message: __("Check the Error Log, then try again."),
						indicator: "red",
					});
				},
			});
		});
	},
});
