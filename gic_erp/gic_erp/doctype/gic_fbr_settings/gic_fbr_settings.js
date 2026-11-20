// Copyright (c) 2026, Gujranwala Incubation Center and contributors
// For license information, please see license.txt

frappe.ui.form.on("GIC FBR Settings", {
	refresh(frm) {
		frm.set_intro("");
		if (frm.doc.enabled && !frm.doc.sandbox_mode) {
			frm.set_intro(__("Live mode: Pakka bills are sent to FBR on submit."), "orange");
		} else if (frm.doc.enabled) {
			frm.set_intro(
				__("Sandbox mode: FBR replies are simulated. Nothing is sent to FBR."),
				"blue"
			);
		}
	},
});
