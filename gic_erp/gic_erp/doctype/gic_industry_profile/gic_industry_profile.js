// Copyright (c) 2026, Gujranwala Incubation Center and contributors
// For license information, please see license.txt

// Business Type -> blueprint offered first (same map as gic_erp/seed/blueprints.py).
const GIC_BLUEPRINTS = {
	"Light Engineering & Foundry": "Foundry & Cookware",
	"Wholesale & Mandi Trader": "Mandi & Wholesale Trader",
	"Importer & Exporter": "Importer & Exporter",
	"Sanitary Ware & Ceramics": "Sanitary Ware & Ceramics",
};

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

		frm.add_custom_button(__("Load Industry Blueprint Data"), () => gic_blueprint_dialog(frm));

		frm.add_custom_button(__("Simplify Forms"), () => {
			frappe.call({
				method: "gic_erp.setup.ui_simplifier.simplify_forms_from_ui",
				freeze: true,
				freeze_message: __("Simplifying Sales Invoice, Purchase Invoice and Payment Entry..."),
				callback(r) {
					if (r.exc || !r.message) return;
					const { hidden_count, skipped } = r.message;
					let message = __("{0} sections hidden. Reload any open forms to see the change.", [
						hidden_count,
					]);
					if (skipped.length) {
						message +=
							"<br><br>" +
							__("Kept visible:") +
							"<ul>" +
							skipped.map((s) => `<li>${frappe.utils.escape_html(s)}</li>`).join("") +
							"</ul>";
					}
					frappe.msgprint({ title: __("Forms Simplified"), message, indicator: "green" });
				},
				error() {
					frappe.msgprint({
						title: __("Could not simplify forms"),
						message: __("Check the Error Log, then try again."),
						indicator: "red",
					});
				},
			});
		});
	},
});

function gic_blueprint_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Load Industry Blueprint Data"),
		fields: [
			{
				fieldname: "blueprint_name",
				label: __("Blueprint"),
				fieldtype: "Select",
				options: Object.values(GIC_BLUEPRINTS),
				default: GIC_BLUEPRINTS[frm.doc.business_type],
				reqd: 1,
			},
			{
				fieldname: "company",
				label: __("Company"),
				fieldtype: "Link",
				options: "Company",
				default: frm.doc.company,
				reqd: 1,
			},
			{
				fieldname: "help",
				fieldtype: "HTML",
				options: `<p class="text-muted">${__(
					"Adds Pakistani tax templates and starter items, accounts and settings for this industry. Anything that already exists is left as it is, so it is safe to run again."
				)}</p>`,
			},
		],
		primary_action_label: __("Load"),
		primary_action(values) {
			dialog.hide();
			frappe
				.call({
					method: "gic_erp.seed.blueprints.apply_industry_blueprint",
					args: values,
					freeze: true,
					freeze_message: __("Loading {0}...", [values.blueprint_name]),
				})
				.then((r) => {
					if (!r.message) return;
					const { created, already_there } = r.message;
					const list = (rows) =>
						rows.length
							? "<ul>" + rows.map((x) => `<li>${frappe.utils.escape_html(x)}</li>`).join("") + "</ul>"
							: `<p class="text-muted">${__("None")}</p>`;
					frappe.msgprint({
						title: __("{0} loaded", [values.blueprint_name]),
						message: `<b>${__("Created")} (${created.length})</b>${list(created)}<b>${__(
							"Already there"
						)} (${already_there.length})</b>${list(already_there)}`,
						indicator: "green",
						wide: true,
					});
				});
		},
	});
	dialog.show();
}
