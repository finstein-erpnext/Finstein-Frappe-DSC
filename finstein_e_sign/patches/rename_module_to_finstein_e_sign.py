# Copyright (c) 2026, Finstein and contributors
"""Repair sites that installed this app under its previous names.

The app was published to the Frappe marketplace as ``finstein_e_sign``. It was
previously shipped as ``e_sign`` (and, on some benches, ``fin_e_sign``) with an
internal module called "Digital signature".

Two things need fixing on a site that installed one of those older builds:

1. The module was renamed to "Finstein E Sign". ``Module Def`` is autonamed on
   ``module_name`` and is unique **per site, across every app**, so the old
   generic name risked colliding with another app on the same bench.

2. ``frappe.installer.add_module_defs()`` only ever *inserts* -- it never
   updates ``app_name`` on a ``Module Def`` that already exists. So after the
   app rename the module still pointed at an app that no longer exists on the
   bench, which breaks ``bench uninstall-app``: it looks modules up with
   ``get_all("Module Def", filters={"app_name": ...})`` and would find none,
   leaving every DSC doctype and table behind.

This runs in ``[pre_model_sync]`` on purpose. ``frappe.model.sync.sync_all()``
runs *between* the two patch phases and imports the doctype JSONs, which now
declare ``"module": "Finstein E Sign"``. Renaming first means the Module Def
already exists when those rows are written, so the DB is never left holding
dangling module links.
"""

import frappe

OLD_MODULE = "Digital signature"
NEW_MODULE = "Finstein E Sign"
OLD_APP_NAMES = ("e_sign", "fin_e_sign")
NEW_APP_NAME = "finstein_e_sign"


def execute():
	if not frappe.db.table_exists("Module Def"):
		return

	_rename_module()
	_fix_module_app_name()
	_fix_installed_apps()
	frappe.clear_cache()


def _rename_module():
	"""Rename the Module Def, letting Frappe cascade the change.

	``module`` is a Link field to Module Def on DocType, Report, Workspace,
	Page, Print Format, Notification, Dashboard Chart and friends, so
	``rename_doc`` repoints all of them for us.

	We rename rather than delete-and-recreate deliberately: ``ModuleDef.on_trash``
	calls ``delete_folder()`` and strips the module from ``modules.txt`` when
	developer_mode is on, which would delete source files off disk.
	"""
	if not frappe.db.exists("Module Def", OLD_MODULE):
		return

	if frappe.db.exists("Module Def", NEW_MODULE):
		# A previous partial run already created the new row. Repoint anything
		# still referencing the old module, then drop the stale row.
		for doctype in _module_linked_doctypes():
			frappe.db.set_value(
				doctype,
				{"module": OLD_MODULE},
				"module",
				NEW_MODULE,
				update_modified=False,
			)
		frappe.delete_doc("Module Def", OLD_MODULE, force=True, ignore_permissions=True)
		return

	frappe.rename_doc(
		"Module Def",
		OLD_MODULE,
		NEW_MODULE,
		force=True,
		ignore_permissions=True,
		show_alert=False,
	)


def _fix_module_app_name():
	"""Point the module at the current app name (see note 2 in the docstring)."""
	if not frappe.db.exists("Module Def", NEW_MODULE):
		return

	if frappe.db.get_value("Module Def", NEW_MODULE, "app_name") != NEW_APP_NAME:
		frappe.db.set_value(
			"Module Def", NEW_MODULE, "app_name", NEW_APP_NAME, update_modified=False
		)


def _fix_installed_apps():
	"""Replace any old app name in the site's installed_apps registry.

	Normally this is already correct, because a site whose installed_apps still
	says ``e_sign`` cannot import the app at all and so would never reach this
	patch. It is repaired defensively for sites that were half-migrated by hand.
	"""
	import json

	installed = json.loads(frappe.db.get_global("installed_apps") or "[]")
	if not any(old in installed for old in OLD_APP_NAMES):
		return

	repaired = [NEW_APP_NAME if app in OLD_APP_NAMES else app for app in installed]
	# Collapse a duplicate if both the old and the new name were present.
	deduped = list(dict.fromkeys(repaired))
	frappe.db.set_global("installed_apps", json.dumps(deduped))


def _module_linked_doctypes():
	"""DocTypes with a Link field pointing at Module Def, that actually exist."""
	rows = frappe.get_all(
		"DocField",
		filters={"fieldtype": "Link", "options": "Module Def", "fieldname": "module"},
		fields=["parent"],
		pluck="parent",
	)
	seen = []
	for dt in dict.fromkeys(rows):
		if frappe.db.table_exists(dt):
			seen.append(dt)
	return seen
