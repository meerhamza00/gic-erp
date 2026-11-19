// Copyright (c) 2026, Gujranwala Incubation Center and contributors
// For license information, please see license.txt

frappe.ui.form.on("GIC WhatsApp Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Send Test Message"), () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Save the settings first."));
				return;
			}
			frappe
				.call({
					method: "gic_erp.gic_erp.doctype.gic_whatsapp_settings.gic_whatsapp_settings.send_test_message",
					freeze: true,
					freeze_message: __("Sending..."),
				})
				.then((r) => {
					if (r.message && r.message.sent) {
						frappe.show_alert({ message: __("Test message sent"), indicator: "green" });
					} else {
						frappe.msgprint(__("Not sent: WhatsApp is disabled here or in GIC Industry Profile."));
					}
				});
		});
	},
});
