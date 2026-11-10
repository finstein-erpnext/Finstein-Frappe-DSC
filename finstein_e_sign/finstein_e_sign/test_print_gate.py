"""The Print view sends more query params than core ``download_pdf`` accepts.

``frappe.call`` normally filters a request's form_dict down to the target's signature, but it skips
that filtering for any target declaring ``**kwargs`` — which this override does. So the override
receives ``settings`` / ``_lang`` / ``cmd`` and must not pass them on: core's signature is strict
and raises ``TypeError: download_pdf() got an unexpected keyword argument 'settings'``.

The spy below derives its signature from the real core function, so these tests fail the same way
the live server did rather than against a hand-copied parameter list that could drift.
"""

import functools
import inspect

import frappe
from frappe.tests.utils import FrappeTestCase

from finstein_e_sign.finstein_e_sign import print_gate

# Exactly what frappe/printing/page/print/print.js:646 (render_page) puts on the wire, plus the
# `cmd` the request handler injects.
PRINT_VIEW_PARAMS = {
	"format": None,
	"no_letterhead": "1",
	"letterhead": "No Letterhead",
	"settings": "{}",
	"_lang": "en",
	"cmd": "frappe.utils.print_format.download_pdf",
}

LEAKED_PARAMS = ("settings", "_lang", "cmd")


def _core_signature_spy(recorder):
	"""Stand in for core ``download_pdf``, rejecting anything its real signature would reject."""
	from frappe.utils.print_format import download_pdf as core

	signature = inspect.signature(core)

	# @wraps sets __wrapped__, so inspect.signature — and therefore the frappe.get_newargs call
	# inside _delegate — reports core's real signature rather than this spy's (*args, **kwargs).
	# Without it the spy would itself look like a **kwargs target and defeat the filtering it is
	# here to verify.
	@functools.wraps(core)
	def spy(*args, **kwargs):
		# Raises TypeError on an unexpected keyword — the live failure, reproduced.
		bound = signature.bind(*args, **kwargs)
		recorder.update(bound.arguments)

	return spy


class TestPrintGateForwarding(FrappeTestCase):
	def setUp(self):
		# Each test decides for itself whether a gate applies, so start from a known-clean slate —
		# a rule left behind by another test would silently send the ungated case down the gated
		# branch (or vice versa).
		frappe.db.delete("DSC Rule", {"target_doctype": "ToDo"})
		frappe.clear_cache()

		self.todo = frappe.get_doc(
			{"doctype": "ToDo", "description": "print gate forwarding test"}
		).insert(ignore_permissions=True)

	def _call_through_frappe(self):
		"""Invoke the override the way frappe.handler does, and record what core received."""
		recorder = {}
		spy = _core_signature_spy(recorder)

		import frappe.utils.print_format as print_format_module

		original = print_format_module.download_pdf
		print_format_module.download_pdf = spy
		try:
			frappe.call(
				"finstein_e_sign.finstein_e_sign.print_gate.download_pdf",
				doctype="ToDo",
				name=self.todo.name,
				**PRINT_VIEW_PARAMS,
			)
		finally:
			print_format_module.download_pdf = original

		return recorder

	def test_core_download_pdf_still_rejects_the_print_view_params(self):
		"""Pins the premise. If core ever accepts these, the filtering can be dropped."""
		from frappe.utils.print_format import download_pdf as core

		accepted = inspect.signature(core).parameters
		for param in LEAKED_PARAMS:
			self.assertNotIn(param, accepted)

	def test_ungated_passthrough_filters_unknown_params(self):
		"""No DSC Rule — print_gate.py's first forward site."""
		self.assertFalse(
			frappe.db.exists("DSC Rule", {"target_doctype": "ToDo", "is_enabled": 1}),
			"this test needs the ungated path",
		)

		received = self._call_through_frappe()

		self.assertEqual(received["doctype"], "ToDo")
		self.assertEqual(received["name"], self.todo.name)
		self.assertEqual(received["letterhead"], "No Letterhead")
		self.assertEqual(received["no_letterhead"], "1")
		for param in LEAKED_PARAMS:
			self.assertNotIn(param, received)

	def test_gated_passthrough_filters_unknown_params(self):
		"""DSC Rule present but not mandatory and nothing signed — the second forward site."""
		rule = frappe.get_doc(
			{
				"doctype": "DSC Rule",
				"rule_name": "print gate forwarding test",
				"target_doctype": "ToDo",
				"is_enabled": 1,
				"block_print_until_signed": 1,
				"is_mandatory": 0,
			}
		)
		# The signing fields (profile / print_format / signature_template) are mandatory but
		# irrelevant here — the gate only reads the three flags above.
		rule.insert(ignore_permissions=True, ignore_mandatory=True)

		received = self._call_through_frappe()

		self.assertEqual(received["name"], self.todo.name)
		for param in LEAKED_PARAMS:
			self.assertNotIn(param, received)

	def test_forwards_params_core_does_accept(self):
		"""The **kwargs tolerance must survive the filtering."""
		recorder = {}
		spy = _core_signature_spy(recorder)

		import frappe.utils.print_format as print_format_module

		original = print_format_module.download_pdf
		print_format_module.download_pdf = spy
		try:
			frappe.call(
				"finstein_e_sign.finstein_e_sign.print_gate.download_pdf",
				doctype="ToDo",
				name=self.todo.name,
				language="de",
				pdf_generator="wkhtmltopdf",
				**PRINT_VIEW_PARAMS,
			)
		finally:
			print_format_module.download_pdf = original

		self.assertEqual(recorder["language"], "de")
		self.assertEqual(recorder["pdf_generator"], "wkhtmltopdf")
