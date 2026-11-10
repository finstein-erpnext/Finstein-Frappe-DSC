/**
 * DSC Profile — form client script.
 *
 * Adds a "Register Certificate" button that reads the certificate from the
 * token plugged into the local dsc-bridge agent and registers it against this
 * profile. The server (finstein_e_sign.api.agent.register_certificate) computes the
 * SHA-256 fingerprint from the certificate DER and stores it — the fingerprint
 * is NEVER entered by hand. This is the only supported way to populate the
 * Certificate Fingerprint field.
 */

frappe.ui.form.on("DSC Profile", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Register Certificate"), () => {
			register_certificate_from_token(frm);
		});

		if (frm.doc.certificate_fingerprint) {
			frm.dashboard.set_headline(
				__("Certificate registered: {0}", [
					frm.doc.certificate_common_name || frm.doc.certificate_fingerprint.slice(0, 16) + "…",
				])
			);
		}
	},
});

// dsc-bridge agent — same host/port the global signing script uses.
const AGENT_HOST = "127.0.0.1";
const DEFAULT_AGENT_PORT = 4645;

function get_site_token() {
	return window.localStorage.getItem("dsc_site_token") || "";
}

// ---------------------------------------------------------------------------
// Auto-pairing — /v1/certs is only served to a site the bridge is paired with.
// A freshly installed bridge isn't paired yet, so reading certs would 403. We
// pair automatically first (same handshake the signing flow uses): the bridge
// stores a per-site token keyed by this page's origin (window.location.origin),
// so it works on whatever host/port the site is actually served from.
// ---------------------------------------------------------------------------

async function ping_agent() {
	try {
		const r = await fetch(`https://${AGENT_HOST}:${DEFAULT_AGENT_PORT}/v1/status`, {
			method: "GET",
			mode: "cors",
		});
		return r.ok ? await r.json() : null;
	} catch (e) {
		return null;
	}
}

function normalise_site_url(u) {
	if (!u) return "";
	try {
		const p = new URL(u);
		return (p.protocol + "//" + p.host).toLowerCase();
	} catch (e) {
		return String(u).replace(/\/+$/, "").toLowerCase();
	}
}

function is_paired(status) {
	const here = normalise_site_url(window.location.origin);
	const paired = (status && status.paired_sites) || [];
	return paired.some((s) => normalise_site_url(s) === here);
}

async function auto_pair() {
	const codeResp = await new Promise((resolve, reject) => {
		frappe.call({
			method: "finstein_e_sign.api.agent.generate_pairing_code",
			callback: (r) =>
				r && r.message
					? resolve(r.message)
					: reject(new Error(__("Could not generate a pairing code."))),
			error: () => reject(new Error(__("Could not generate a pairing code."))),
		});
	});

	const resp = await fetch(`https://${AGENT_HOST}:${DEFAULT_AGENT_PORT}/v1/pair`, {
		method: "POST",
		mode: "cors",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({
			pairing_code: codeResp.pairing_code,
			site_url: window.location.origin,
		}),
	});
	if (!resp.ok) {
		let detail = "";
		try {
			detail = (await resp.json()).message || "";
		} catch (e) {}
		throw new Error(
			__("Could not pair this computer with the site.") + (detail ? " " + detail : "")
		);
	}
}

// Make sure the bridge is reachable and paired with THIS site before reading
// certificates. Pairs automatically if needed.
async function ensure_paired() {
	const status = await ping_agent();
	if (!status) {
		throw new Error(
			__(
				"Cannot reach the DSC Bridge on this computer. Make sure it is installed and running, then try again."
			)
		);
	}
	if (!is_paired(status)) {
		await auto_pair();
	}
}

async function fetch_token_certs() {
	const url = `https://${AGENT_HOST}:${DEFAULT_AGENT_PORT}/v1/certs`;
	let resp;
	try {
		resp = await fetch(url, {
			method: "GET",
			mode: "cors",
			headers: { "X-DSC-Site-Token": get_site_token() },
		});
	} catch (e) {
		throw new Error(
			__("Cannot reach the dsc-bridge agent at {0}. Is it running and is the token plugged in?", [url])
		);
	}
	if (!resp.ok) {
		throw new Error(__("The agent could not read certificates from the token (HTTP {0}).", [resp.status]));
	}
	const body = await resp.json();
	const certs = (body && body.certs) || [];
	if (!certs.length) {
		throw new Error(__("No certificate found on the connected token."));
	}
	return certs;
}

function register_selected(frm, cert) {
	if (!cert || !cert.cert_der_b64) {
		frappe.msgprint({
			title: __("Cannot register"),
			message: __("The selected certificate did not include its DER data. Update the dsc-bridge agent."),
			indicator: "red",
		});
		return;
	}
	frappe.call({
		method: "finstein_e_sign.api.agent.register_certificate",
		args: {
			profile_name: frm.doc.name,
			cert_der_b64: cert.cert_der_b64,
		},
		freeze: true,
		freeze_message: __("Registering certificate…"),
		callback: (r) => {
			if (!r.exc) {
				frappe.show_alert({
					message: __("Certificate registered for {0}", [r.message.common_name || frm.doc.name]),
					indicator: "green",
				});
				frm.reload_doc();
			}
		},
	});
}

async function register_certificate_from_token(frm) {
	let certs;
	try {
		// Pair this computer with the site first (no-op if already paired), then
		// read the certificates. Without this a fresh bridge returns 403.
		await ensure_paired();
		certs = await fetch_token_certs();
	} catch (e) {
		frappe.msgprint({ title: __("Register Certificate"), message: e.message, indicator: "red" });
		return;
	}

	if (certs.length === 1) {
		register_selected(frm, certs[0]);
		return;
	}

	// Multiple certificates on the token — let the admin choose which to bind.
	const d = new frappe.ui.Dialog({
		title: __("Select certificate to register"),
		fields: [
			{
				fieldname: "cert_idx",
				fieldtype: "Select",
				label: __("Certificate"),
				reqd: 1,
				options: certs.map((c, i) => ({
					label: `${c.subject_cn || c.subject_full || __("Certificate")} — ${c.issuer_cn || ""} (${(c.fingerprint_sha256 || "").slice(0, 12)}…)`,
					value: String(i),
				})),
			},
		],
		primary_action_label: __("Register"),
		primary_action(values) {
			d.hide();
			register_selected(frm, certs[Number(values.cert_idx)]);
		},
	});
	d.show();
}
