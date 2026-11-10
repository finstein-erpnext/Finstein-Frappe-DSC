// DSC Settings — adds a "Download DSC Bridge" section so admins/signers can grab
// the one-time bridge installer for their operating system directly from here.
//
// The bridge is the small local agent each signer installs once on their own
// machine so the browser can talk to their USB DSC token. Installers are shipped
// with the app and served from /assets/finstein_e_sign/downloads/.

frappe.ui.form.on("DSC Settings", {
	refresh(frm) {
		const base = "/assets/finstein_e_sign/downloads/";
		const installers = [
			{ label: __("Windows (64-bit)"), file: "dsc-bridge-1.0.0-windows.zip" },
			{ label: __("Windows (32-bit — Hypersecu/HYP2003)"), file: "dsc-bridge-1.0.0-windows-x86.zip" },
			{ label: __("Linux (Ubuntu/Debian .deb)"), file: "dsc-bridge_1.0.0_amd64.deb" },
			{ label: __("Linux (other, .tar.gz)"), file: "dsc-bridge-1.0.0-linux-amd64.tar.gz" },
		];

		installers.forEach((it) => {
			frm.add_custom_button(
				it.label,
				() => window.open(base + it.file, "_blank"),
				__("Download DSC Bridge")
			);
		});

		frm.set_intro(
			__(
				"To sign with a USB DSC token, each signer installs the DSC Bridge once on their own computer. Use <b>Download DSC Bridge</b> above to get the installer for their operating system. After installing, it starts automatically on login — the signer just plugs in the token and clicks “Sign with DSC”."
			),
			"blue"
		);
	},
});
