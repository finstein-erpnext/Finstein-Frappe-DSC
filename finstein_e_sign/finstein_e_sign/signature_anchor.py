"""Dynamic DSC signature placeholder for print formats.

Instead of pinning the signature to a fixed x/y box on the DSC Signature
Template, a print-format author can drop a placeholder wherever the signature
should appear:

    {{ dsc_signature_anchor(width=220, height=90) }}

It renders an invisible, space-reserving marker that flows with the document —
so on a Sales Invoice with a variable number of line items the signature moves
to the right place automatically, exactly like the GST e-invoice QR code. At
signing time the engine finds the marker in the rendered PDF (locate_signature_
anchor) and stamps the signature there instead of at fixed coordinates.

Backward compatible: if a print format has no anchor, signing falls back to the
Signature Template's fixed coordinates (unchanged behaviour).
"""

import re
from io import BytesIO

import frappe
from markupsafe import Markup

# The marker carries the requested box size so the signing engine can read it
# back out of the rendered PDF: @@DSC_SIG_ANCHOR:<width>:<height>@@ (PDF points).
_ANCHOR_RE = re.compile(r"@@DSC_SIG_ANCHOR:(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)@@")


def dsc_signature_anchor(width=200, height=80):
	"""Jinja helper: reserve a dynamic DSC signature box in a print format.

	`width` / `height` are in PDF points (1pt = 1/72 inch), matching pyHanko's
	box units. Returns HTML that reserves that space in the document flow and
	embeds an invisible position marker for the signing engine to find.
	"""
	try:
		width = float(width)
		height = float(height)
	except (TypeError, ValueError):
		width, height = 200.0, 80.0

	marker = f"@@DSC_SIG_ANCHOR:{width:g}:{height:g}@@"
	# `pt` units so the reserved space matches the PDF-point box exactly. The
	# marker text is transparent + 1pt so it never shows and never grows the box.
	html = (
		f'<div class="dsc-signature-anchor" '
		f'style="width:{width:g}pt;height:{height:g}pt;position:relative;overflow:hidden;">'
		f'<span style="color:transparent;font-size:1pt;line-height:1pt;white-space:nowrap;">'
		f'{marker}</span>'
		f'</div>'
	)
	return Markup(html)


def locate_signature_anchor(pdf_bytes):
	"""Find the signature anchor marker in a rendered PDF.

	Returns a dict {page (0-based), x, top, width, height} in PDF points (origin
	bottom-left, matching pyHanko's box), or None if there is no anchor or
	pdfminer is unavailable. Never raises — the caller falls back to fixed
	placement on None.
	"""
	try:
		from pdfminer.high_level import extract_pages
		from pdfminer.layout import LTTextContainer
	except Exception:
		# pdfminer.six not installed — silently fall back to fixed placement.
		return None

	try:
		for page_index, layout in enumerate(extract_pages(BytesIO(pdf_bytes))):
			for element in layout:
				if not isinstance(element, LTTextContainer):
					continue
				for line in element:
					get_text = getattr(line, "get_text", None)
					if not callable(get_text):
						continue
					match = _ANCHOR_RE.search(get_text())
					if not match:
						continue
					width = float(match.group(1))
					height = float(match.group(2))
					# bbox = (x0, y0, x1, y1); y1 is the top of the marker,
					# which sits at the top of the reserved region.
					x0, _y0, _x1, y1 = line.bbox
					return {
						"page": page_index,
						"x": x0,
						"top": y1,
						"width": width,
						"height": height,
					}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "DSC signature anchor scan failed")
		return None
	return None
