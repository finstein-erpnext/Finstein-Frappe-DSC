"""
Print Gate — intercepts PDF downloads to enforce signing requirements.

When a DSC Rule has block_print_until_signed=1 for a DocType:
  - If a signed PDF exists → serve the signed version instead
  - If not signed yet and mandatory → block with error
  - Otherwise → pass through to the original Frappe print
"""

import frappe


@frappe.whitelist(allow_guest=True)
def download_pdf(doctype, name, format=None, doc=None, no_letterhead=0, **kwargs):
	"""Override of frappe.utils.print_format.download_pdf.

	Uses **kwargs so this override tolerates Frappe upgrades that add new
	parameters (e.g. pdf_generator, letterhead, language). Forwarding is done by
	:func:`_delegate`, never by splatting **kwargs directly — see its docstring.

	Checks DSC Rules for the document and either:
	1. Substitutes the signed PDF if available
	2. Blocks the download if signing is mandatory but not done
	3. Passes through to original Frappe PDF generation
	"""
	blocking_rule = frappe.db.get_value(
		"DSC Rule",
		filters={
			"target_doctype": doctype,
			"is_enabled": 1,
			"block_print_until_signed": 1,
		},
		fieldname=["name", "is_mandatory"],
		as_dict=True,
	)

	if not blocking_rule:
		return _delegate(doctype, name, format, doc, no_letterhead, kwargs)

	# A DSC gate applies — from here we diverge from Frappe's native handler,
	# which performs its own print/read permission check. Because we may serve
	# the signed File's bytes directly (bypassing that handler), enforce read
	# permission on the *source* document ourselves first. Without this, the
	# allow_guest whitelist would let any unauthenticated caller download a
	# signed PDF just by knowing the doctype + name (IDOR).
	if not frappe.has_permission(doctype, "read", doc=name):
		raise frappe.PermissionError(
			f"You do not have permission to access {doctype} {name}."
		)

	signed_request = frappe.db.get_value(
		"DSC Signing Request",
		filters={
			"source_doctype": doctype,
			"source_name": name,
			"status": "Signed",
		},
		fieldname=["name", "signed_file"],
		as_dict=True,
	)

	if signed_request and signed_request.signed_file:
		file_doc = frappe.get_doc("File", signed_request.signed_file)
		file_content = file_doc.get_content()

		frappe.local.response.filename = file_doc.file_name
		frappe.local.response.filecontent = file_content
		frappe.local.response.type = "download"
		return

	if blocking_rule.is_mandatory:
		frappe.throw(
			f"This {doctype} requires a digital signature before printing. "
			f"Please sign the document first using 'Sign with DSC'.",
			title="Signature Required",
		)

	return _delegate(doctype, name, format, doc, no_letterhead, kwargs)


def _delegate(doctype, name, format, doc, no_letterhead, kwargs):
	"""Hand off to core ``download_pdf``, dropping kwargs it does not declare.

	``frappe.call`` normally filters the request's form_dict down to the target's signature
	(``frappe.get_newargs``, frappe/__init__.py:1752) — but it skips that filtering entirely for
	any target declaring ``**kwargs``, which this override does. So we receive the *whole* form
	dict, and the Print view sends more than core accepts: ``print.js render_page``
	(frappe/printing/page/print/print.js:646) appends ``settings`` and ``_lang``, and the request
	handler adds ``cmd``. Core's ``download_pdf`` has a strict signature and raises
	``TypeError: download_pdf() got an unexpected keyword argument 'settings'`` on any of them.

	Filtering here rather than tightening this override's signature keeps the tolerance the
	``**kwargs`` was added for: ``language`` / ``letterhead`` / ``pdf_generator`` still pass
	through, and parameters a future Frappe adds are forwarded automatically.

	Nothing is lost by dropping the extras — ``settings`` is unused server-side on the
	wkhtmltopdf path, and ``_lang`` is applied to ``frappe.local.lang`` by request handling, not
	by this function's ``language`` argument.
	"""
	from frappe.utils.print_format import download_pdf as _original_download_pdf

	forwarded = frappe.get_newargs(
		_original_download_pdf,
		{"format": format, "doc": doc, "no_letterhead": no_letterhead, **kwargs},
	)

	return _original_download_pdf(doctype, name, **forwarded)
