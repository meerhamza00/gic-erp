// Copyright (c) 2026, Gujranwala Incubation Center and contributors
// For license information, please see license.txt
// Kacha / Pakka billing on Sales Invoice. The server enforces the same rules
// (gic_erp/billing/kacha_pakka.py); this keeps the screen in step while typing.

const GIC_KACHA = "Kacha (Estimate Slip)";
const GIC_KACHA_PRINT_FORMAT = "GIC Kacha Slip";

frappe.ui.form.on("Sales Invoice", {
	onload(frm) {
		frappe.db
			.get_single_value("GIC Industry Profile", "enable_kacha_pakka_mode")
			.then((enabled) => {
				frm.gic_kacha_enabled = !!enabled;
				frm.toggle_display("gic_bill_mode", frm.gic_kacha_enabled);
			})
			.catch(() => frm.toggle_display("gic_bill_mode", false));
	},

	refresh(frm) {
		if (frm.gic_kacha_enabled !== undefined) {
			frm.toggle_display("gic_bill_mode", frm.gic_kacha_enabled);
		}
		gic_fbr_retry_button(frm);
		if (!frm.is_new() && frm.doc.gic_bill_mode === GIC_KACHA) {
			frm.add_custom_button(__("Print Kacha Slip"), () => gic_print_kacha_slip(frm));
			// show_message appends on every refresh, so add the notice only once.
			if (!frm.layout.message.find(".gic-kacha-notice").length) {
				frm.dashboard.set_headline(
					`<div class="gic-kacha-notice">${__(
						"Kacha bill: estimate / delivery memo, no sales tax."
					)}</div>`,
					"orange"
				);
			}
		}
	},

	gic_bill_mode(frm) {
		if (frm.doc.gic_bill_mode !== GIC_KACHA) {
			return;
		}
		const had_taxes = (frm.doc.taxes || []).length > 0 || frm.doc.taxes_and_charges;
		frm.set_value("taxes_and_charges", "");
		frm.set_value("tax_category", "");
		frm.clear_table("taxes");
		frm.refresh_field("taxes");
		frm.cscript.calculate_taxes_and_totals();
		if (had_taxes) {
			frappe.show_alert({
				message: __("Taxes removed for Kacha bill"),
				indicator: "orange",
			});
		}
	},
});

function gic_print_kacha_slip(frm) {
	const params = new URLSearchParams({
		doctype: frm.doc.doctype,
		name: frm.doc.name,
		format: GIC_KACHA_PRINT_FORMAT,
		no_letterhead: 1,
		trigger_print: 1,
	});
	window.open(`/printview?${params.toString()}`, "_blank");
}

function gic_fbr_retry_button(frm) {
	const status = frm.doc.gic_fbr_sync_status;
	if (frm.doc.docstatus !== 1 || !["Pending", "Failed"].includes(status)) {
		return;
	}
	frm.add_custom_button(__("Retry FBR Sync"), () => {
		frappe
			.call({
				method: "gic_erp.services.fbr_sync.retry_fbr_sync",
				args: { docname: frm.doc.name },
				freeze: true,
				freeze_message: __("Sending to FBR queue..."),
			})
			.then(() => {
				frappe.show_alert({
					message: __("Queued for FBR. Reload in a few seconds to see the result."),
					indicator: "blue",
				});
				frm.reload_doc();
			});
	});
}
