# Copyright (c) 2026, Gujranwala Incubation Center and contributors
# For license information, please see license.txt
"""Foundry burning loss on Stock Entry.

burning_loss_kg = gross_metal_issued - finished_goods_weight - scrap_recovered
burning_loss_pct = burning_loss_kg / gross_metal_issued * 100

Finished goods are usually counted in pieces (karahis, cookers), so their weight is
derived per row: stock_uom Kg -> stock qty; otherwise Item.weight_per_unit (Kg or Gram).
If any finished row has no known weight, the user enters Finished Goods Weight manually.
"""

import frappe
from frappe import _
from frappe.utils import flt

BURNING_LOSS_ALERT_PCT = 5.0
KG_FACTOR = {"Kg": 1.0, "Kilogram": 1.0, "Gram": 0.001, "Gm": 0.001}
PRECISION = 3


def validate_burning_loss(doc, method=None):
	"""Stock Entry validate hook."""
	if not doc.get("gic_is_foundry_melt"):
		for field in ("gic_burning_loss_qty", "gic_burning_loss_pct"):
			doc.set(field, 0)
		return

	gross = flt(doc.gic_gross_metal_weight, PRECISION)
	scrap = flt(doc.gic_scrap_recovered, PRECISION)

	if gross <= 0:
		frappe.throw(_("Enter the Gross Metal Issued (Kg) for this melt."), title=_("Burning Loss"))
	if scrap < 0 or flt(doc.gic_finished_weight) < 0:
		frappe.throw(_("Weights cannot be negative."), title=_("Burning Loss"))

	auto_weight = finished_goods_weight(doc)
	if auto_weight is not None:
		doc.gic_finished_weight = auto_weight
	elif not flt(doc.gic_finished_weight):
		doc.gic_burning_loss_qty = 0
		doc.gic_burning_loss_pct = 0
		frappe.msgprint(
			_(
				"Burning loss not calculated: some finished items have no weight. "
				"Enter Finished Goods Weight (Kg), or set Weight Per Unit on those Items."
			),
			title=_("Burning Loss"),
			indicator="orange",
		)
		return

	finished = flt(doc.gic_finished_weight, PRECISION)
	loss = flt(gross - finished - scrap, PRECISION)
	if loss < 0:
		frappe.throw(
			_(
				"Finished goods ({0} Kg) plus scrap ({1} Kg) is more than the metal issued ({2} Kg). "
				"Please check the weights."
			).format(finished, scrap, gross),
			title=_("Burning Loss"),
		)

	doc.gic_burning_loss_qty = loss
	doc.gic_burning_loss_pct = flt(loss / gross * 100, 2)

	if doc.gic_burning_loss_pct > BURNING_LOSS_ALERT_PCT:
		frappe.msgprint(
			_("High burning loss: {0}% ({1} Kg). Normal is up to {2}%.").format(
				doc.gic_burning_loss_pct, loss, BURNING_LOSS_ALERT_PCT
			),
			title=_("Burning Loss Alert"),
			indicator="red",
		)


def finished_rows(doc) -> list:
	"""Finished-goods rows: flagged finished items, else incoming non-scrap rows."""
	rows = doc.get("items") or []
	flagged = [r for r in rows if r.get("is_finished_item")]
	if flagged:
		return flagged
	return [r for r in rows if r.get("t_warehouse") and not r.get("is_scrap_item")]


def finished_goods_weight(doc) -> float | None:
	"""Total Kg of finished goods, or None if any finished row's weight is unknown."""
	total = 0.0
	for row in finished_rows(doc):
		row_kg = _row_weight_kg(row)
		if row_kg is None:
			return None
		total += row_kg
	return flt(total, PRECISION)


def _row_weight_kg(row) -> float | None:
	stock_qty = flt(row.get("transfer_qty")) or flt(row.get("qty")) * flt(row.get("conversion_factor") or 1)
	stock_uom = row.get("stock_uom") or frappe.db.get_value("Item", row.item_code, "stock_uom")
	if stock_uom in KG_FACTOR:
		return stock_qty * KG_FACTOR[stock_uom]

	weight, weight_uom = frappe.db.get_value("Item", row.item_code, ["weight_per_unit", "weight_uom"]) or (
		0,
		None,
	)
	if flt(weight) > 0 and weight_uom in KG_FACTOR:
		return stock_qty * flt(weight) * KG_FACTOR[weight_uom]
	return None
