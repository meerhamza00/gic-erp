# MASTER EXECUTION THREAD: GIC-ERP (Gujranwala Plug-and-Play Modular ERP)

> Saved from the pasted plan on 2026-11-19. Move into `frappe-bench/apps/gic_erp/` once the app is scaffolded.
> Overrides from Meer's standing rules: **no git commit without Meer's explicit approval** (rule 2.5 below is "stage + propose commit", not auto-commit).

## 1. PROJECT CONTEXT & GOAL
You are the Lead Frappe/ERPNext Architect building **GIC-ERP** (`gic_erp`), a plug-and-play, modular ERP wrapper built on top of **Frappe Framework v15 & ERPNext v15**.
This platform is developed and managed by the **Gujranwala Incubation Center (GIC)** for Gujranwala's industrial, trading, import, and export community (light engineering, foundries, cookware, sanitary ware, rice/mandi traders, and cross-border exporters).

**Core Philosophy:**
- **Value-as-a-Service (VaaS):** Traditional factory owners and *munshis* reject complex ERPs. The UI must hide 85% of ERPNext's native bloat and expose simple, task-oriented workflows.
- **Modular Plug-and-Play:** A single installation must dynamically configure itself based on the business profile (Manufacturer, Trader, Importer/Exporter, or Ceramics/Sanitary) and toggleable feature flags.

---

## 2. STRICT ARCHITECTURAL & CODING RULES
1. **Zero Core Edits:** NEVER modify files inside `apps/frappe` or `apps/erpnext`. All customizations must live strictly inside `apps/gic_erp`.
2. **Upgrade-Safe Extensions:** Use `hooks.py` (`doc_events`, `override_doctype_class`, `fixtures`, `after_install`), Custom Fields, Property Setters, and Client/Server scripts.
3. **Database & Cache Hygiene:** After creating or altering any DocType, JSON, or hook, immediately run:
   - `bench --site gic-dev.local migrate`
   - `bench --site gic-dev.local clear-cache`
4. **Resilient Background Jobs:** External API calls (WhatsApp webhooks, FBR PRAL API syncs) must run asynchronously via `frappe.enqueue` and log failures to Frappe's `Error Log` so they never block a user from saving or submitting an invoice.
5. **Version Control:** After completing and verifying each Milestone, stage changes inside `apps/gic_erp` and propose a commit message. Commit only after Meer approves.

---

## 3. SEQUENTIAL EXECUTION MILESTONES

Execute **one milestone at a time**. Complete all tasks in the milestone, run migrations/tests, stage for commit, and stop to report status before moving to the next milestone.

---

### MILESTONE 1: Core Modular Switchboard & Fixtures Setup
**Objective:** Create the central configuration engine that turns modules and UI workspaces on/off based on business type.
1. **Create DocType `GIC Industry Profile` (Single DocType, Module: `Gic Erp`):**
   - `business_type` (Select: `Light Engineering & Foundry`, `Wholesale & Mandi Trader`, `Importer & Exporter`, `Sanitary Ware & Ceramics`)
   - `company` (Link: `Company`, mandatory)
   - `enable_fbr_invoicing` (Check, default 0)
   - `enable_whatsapp_alerts` (Check, default 1)
   - `enable_thekedar_payroll` (Check, default 0)
   - `enable_kacha_pakka_mode` (Check, default 1)
   - `enable_scrap_tracking` (Check, default 0)
2. **Controller Logic (`gic_industry_profile.py`):**
   - On `validate` / `on_update`, automatically enforce logical defaults (e.g., if `Light Engineering & Foundry` is selected, auto-enable `enable_scrap_tracking` and `enable_thekedar_payroll`).
   - Dynamically update workspace visibility or user module blocks so irrelevant ERPNext modules (like Healthcare, Education, Agriculture, Non-Profit, Assets, Quality) are hidden from standard users.
3. **Fixtures Configuration (`hooks.py`):**
   - Configure `fixtures` in `hooks.py` to export `Custom Field`, `Property Setter`, `Role`, and `Workspace` filtered by module/prefix `GIC`.
4. **Verification:** Run `bench migrate`, verify DocType creation, and stage Milestone 1 for commit.

---

### MILESTONE 2: "Munshi-Friendly" Simplified UX & Local Units
**Objective:** Strip away complex ERPNext fields and set up Gujranwala trade units and roles.
1. **Custom Roles (`after_install` in `gic_erp/install.py`):**
   - Programmatically ensure two roles exist: `GIC Factory Owner` and `GIC Munshi User`.
2. **Local Units of Measure (`after_install`):**
   - Add standard local UOMs if not present: `Mann` (40 Kg), `Bori`, `Petti`, `Dozen`, `Kilogram`, `Piece`, `Foot`, `Meter`, plus standard `UOM Conversion Factor` entries (e.g., `1 Mann = 40 Kilogram`).
3. **Simplified Workspace (`GIC Easy Desk`):**
   - Create a clean Workspace JSON/fixture named `GIC Easy Desk` containing ONLY 5 high-visibility shortcut cards:
     1. `Create Bill` -> `Sales Invoice`
     2. `Kacha Estimate` -> `Quotation`
     3. `Receive Udhaar` -> `Payment Entry`
     4. `Stock & Scrap` -> `Stock Entry`
     5. `Party Khata` -> `General Ledger`
4. **Field Decluttering (Property Setters):**
   - Create a setup utility `gic_erp/setup/ui_simplifier.py` (called on `after_install` and via a button on `GIC Industry Profile`) that creates `Property Setter` records to hide non-essential sections on `Sales Invoice`, `Purchase Invoice`, and `Payment Entry` (e.g., `timesheets`, `project`, `accounting_dimensions_section`, `terms_section`, `more_info`) so forms fit cleanly on one screen.
5. **Verification:** Run `bench migrate`, execute the setup script, verify `GIC Easy Desk` loads cleanly, and stage Milestone 2.

---

### MILESTONE 3: Gujranwala Manufacturing Modules (Scrap & Thekedar)
**Objective:** Solve raw-material metal burning loss and piece-rate contractor (*thekedar*) payments.
1. **Foundry Scrap & Burning Loss (`Stock Entry` extensions):**
   - Add Custom Fields to `Stock Entry`:
     - `gic_is_foundry_melt` (Check: "Foundry Melt / Scrap Entry")
     - `gic_gross_metal_weight` (Float: "Gross Metal Issued (Kg)", depends_on `eval:doc.gic_is_foundry_melt==1`)
     - `gic_scrap_recovered` (Float: "Reusable Scrap Recovered (Kg)", depends_on `eval:doc.gic_is_foundry_melt==1`)
     - `gic_burning_loss_qty` (Float, read-only: "Burning Loss (Kg)")
     - `gic_burning_loss_pct` (Percent, read-only: "Burning Loss %")
   - Add a `validate` doc_event hook on `Stock Entry`: when `gic_is_foundry_melt` is checked, calculate `burning_loss_qty = gross_metal_weight - total_finished_qty - scrap_recovered` and `burning_loss_pct`. Display a non-blocking `frappe.msgprint` alert if `burning_loss_pct > 5.0`.
2. **Piece-Rate Contractor DocType (`Thekedar Work Log`):**
   - Create Submittable DocType `Thekedar Work Log` with fields:
     - `contractor` (Link: `Supplier`, mandatory)
     - `posting_date` (Date, default Today, mandatory)
     - `work_order` (Link: `Work Order`, optional)
     - `item_produced` (Link: `Item`, mandatory)
     - `operation_type` (Select: `Casting`, `Machining`, `Polishing`, `Winding`, `Assembling`, `Packing`, `Other`)
     - `quantity_completed` (Float, mandatory)
     - `uom` (Link: `UOM`, default `Piece`)
     - `rate_per_unit` (Currency, mandatory)
     - `total_payable` (Currency, read-only, `quantity_completed * rate_per_unit`)
     - `purchase_invoice` (Link: `Purchase Invoice`, read-only)
   - Controller logic:
     - `validate`: compute `total_payable`.
     - `on_submit`: automatically create a Draft `Purchase Invoice` for the `contractor` with a service line item (`Thekedar Labor Charges`) for `total_payable`, and link the created invoice ID back to `self.purchase_invoice`.
3. **Verification:** Run `bench migrate`, write a unit test in `test_thekedar_work_log.py` verifying draft `Purchase Invoice` generation, run `bench --site gic-dev.local run-tests --app gic_erp`, and stage Milestone 3.

---

### MILESTONE 4: "Kacha / Pakka" Dual-Billing & WhatsApp Engine
**Objective:** Support informal estimates alongside formal tax bills and automate WhatsApp customer notifications.
1. **Kacha / Pakka Mode (`Sales Invoice` extensions):**
   - Add Custom Field `gic_bill_mode` (Select: `Pakka (Tax Invoice)` / `Kacha (Estimate Slip)`, default `Pakka (Tax Invoice)`).
   - Add Client Script / Property Setter logic: when `Kacha (Estimate Slip)` is selected, clear `taxes_and_charges` table automatically and hide FBR tax fields.
   - Create a custom Print Format `GIC Kacha Slip` (HTML/Jinja) that prints a clean, compact thermal/A5 estimate slip labeled **"ESTIMATE / DELIVERY MEMO"** without GST/NTN headers.
2. **WhatsApp Automation Engine:**
   - Create Single DocType `GIC WhatsApp Settings`:
     - `enabled` (Check)
     - `api_endpoint` (Data, e.g., local WhatsApp gateway URL)
     - `api_token` (Password)
     - `send_on_invoice` (Check, default 1)
     - `send_on_payment` (Check, default 1)
   - Create `gic_erp/services/whatsapp.py`:
     - Write `send_whatsapp_message(mobile_no, message_text, reference_doctype, reference_name)` using `requests.post` with a 10-second timeout.
     - Catch all exceptions and log them via `frappe.log_error(title="GIC WhatsApp Error")`.
   - Hook `on_submit` on `Sales Invoice` and `Payment Entry` to enqueue `send_whatsapp_message` via `frappe.enqueue` with formatted Urdu/English bilingual summary text (Customer Name, Bill/Receipt #, Amount, and Remaining Balance).
3. **Verification:** Run `bench migrate`, test print format rendering and mocked enqueue execution, and stage Milestone 4.

---

### MILESTONE 5: FBR Digital Invoicing Connector & Industry Blueprints
**Objective:** Enable 1-click FBR compliance and 5-minute preset seeding for new SME onboarding.
1. **FBR Digital Invoicing Scaffold:**
   - Create Single DocType `GIC FBR Settings`:
     - `enabled` (Check)
     - `sandbox_mode` (Check, default 1)
     - `ntn_number` (Data)
     - `strn_number` (Data)
     - `pos_id` (Data)
     - `pral_bearer_token` (Password)
     - `fbr_api_url` (Data, default `https://fbr.gov.pk`)
   - Add Custom Fields on `Sales Invoice`:
     - `gic_fbr_invoice_no` (Data, read-only)
     - `gic_fbr_qr_image` (Attach Image, read-only)
     - `gic_fbr_sync_status` (Select: `Not Applicable`, `Pending`, `Synced`, `Failed`, default `Not Applicable`)
   - Create `gic_erp/services/fbr_sync.py`:
     - Build `sync_invoice_to_fbr(docname)` that maps `Sales Invoice` items (including HS Code if present, quantities, tax rate, and buyer NTN/CNIC) into FBR's JSON payload structure.
     - In `sandbox_mode`, simulate a valid FBR response returning a mock `InvoiceNumber`, generate a PNG QR code using the `qrcode` Python library, attach it to `gic_fbr_qr_image`, and mark status `Synced`.
     - Trigger via `frappe.enqueue` on `Sales Invoice` `on_submit` ONLY when `gic_bill_mode == 'Pakka (Tax Invoice)'` and `GIC FBR Settings.enabled == 1`.
2. **One-Click Industry Blueprint Seeder (`gic_erp/seed/blueprints.py`):**
   - Create a `@frappe.whitelist()` method `apply_industry_blueprint(company, blueprint_name)` that idempotently creates:
     - Pakistani Tax Templates: `Pakistan GST 18%`, `Withholding 236G (0.1%)`, `Withholding 236H (0.5%)`.
     - Blueprint A (`Foundry & Cookware`): Raw materials (`Aluminium Ingot`, `Brass Scrap`, `SS Sheet`), Finished Goods (`Non-Stick Karahi 28cm`, `Pressure Cooker 5L`), and sample BOM.
     - Blueprint B (`Mandi & Wholesale Trader`): Multi-UOM items (`Super Kernel Basmati Rice` in `Mann` and `Bori`, `Cooking Oil Carton`), customer credit limit defaults.
     - Blueprint C (`Importer & Exporter`): Enables multi-currency (`USD`, `AED`, `CNY`), creates `Landed Cost` expense accounts (`Customs Duty`, `Clearing Agent Fee`, `Sea Freight`).
     - Blueprint D (`Sanitary Ware & Ceramics`): Batch-tracked items (`Ceramic Wash Basin - A Grade`, `Ceramic Wash Basin - B Grade`, `Brass Bib Cock`).
   - Add a "Load Industry Blueprint Data" button directly on the `GIC Industry Profile` form that calls this method.
3. **Verification:** Run `bench migrate`, test `apply_industry_blueprint` for all 4 blueprints on `gic-dev.local`, verify QR code attachment in FBR sandbox mode, and stage Milestone 5.

---

### MILESTONE 6: Multi-Tenant Production Deployment & Onboarding Script
**Objective:** Package the platform so GIC can spin up isolated SME instances in under 5 minutes.
1. Create a `deployment/` directory inside `apps/gic_erp/` containing:
   - `onboard_client.sh`: An executable bash script accepting `<site_domain> <company_name> <blueprint_name> <admin_password>` that:
     1. Runs `bench new-site <site_domain> --install-app erpnext --install-app gic_erp`
     2. Executes `bench --site <site_domain> execute gic_erp.seed.blueprints.apply_industry_blueprint`
     3. Enables scheduler (`bench --site <site_domain> enable-scheduler`)
   - `DEPLOYMENT_GUIDE.md`: Concise instructions for hosting multi-tenant sites on Ubuntu VPS with Nginx, Supervisor, Redis, MariaDB, and Let's Encrypt SSL.
2. **Verification:** Validate bash script syntax (`bash -n deployment/onboard_client.sh`), export all fixtures (`bench --site gic-dev.local export-fixtures`), and stage the final Milestone 6 commit.

**Delivered (2026-11-20), adapted to the Docker production model (ADR 0001):**
- `deploy/server/onboard-client.sh <domain> "<company>" "<blueprint>"` instead of
  `deployment/onboard_client.sh`. The Administrator password is generated, shown once and
  saved root-only, never passed as an argument. It also completes the ERPNext setup wizard
  (PKR, Asia/Karachi, fiscal year July to June), which the blueprint needs, saves the GIC
  Industry Profile, and adds the domain to Traefik (Let's Encrypt). `--resume` finishes a
  run that stopped half way.
- Logic in `gic_erp/setup/onboarding.py`, tested in `test_onboarding.py`; the CI deploy
  rehearsal onboards its test site with the real script on every image build.
- `DEPLOYMENT_GUIDE.md` became `docs/DEVOPS.md` (Docker + Traefik replace Nginx and Supervisor).
