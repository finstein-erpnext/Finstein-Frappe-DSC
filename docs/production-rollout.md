# DSC Signing — Production Rollout Guide

How to publish the e-signing feature to production/UAT so any user can sign with
one click. Two parts: **the server** (done once by you) and **each signer's
machine** (a guided one-time install).

---

## Part 1 — Server (do once per environment)

1. **Deploy the app code** (contains the port fix, per-session PIN, and the
   in-app bridge download):
   ```bash
   cd frappe-bench
   # pull the latest finstein_e_sign app, then:
   bench build --app finstein_e_sign
   bench --site <your-site> clear-cache
   bench restart
   ```
   No DB migration is needed — the changes are code only.

2. **Serve the site over real HTTPS** (valid domain + TLS, e.g. Let's Encrypt).
   This is required: the signing flow captures geolocation, which browsers only
   allow on HTTPS. A proper HTTPS domain also removes any port-related issues.

3. **Confirm the bridge installers are served.** They ship inside the app at
   `finstein_e_sign/public/downloads/` and are reachable at:
   - `https://<your-site>/assets/finstein_e_sign/downloads/dsc-bridge-1.0.0-windows.zip`
   - `https://<your-site>/assets/finstein_e_sign/downloads/dsc-bridge_1.0.0_amd64.deb`
   - `https://<your-site>/assets/finstein_e_sign/downloads/dsc-bridge-1.0.0-linux-amd64.tar.gz`

That's the whole server side. The port/PIN fixes now apply to **every** user
automatically — they don't install anything for those.

---

## Part 2 — Each signer's machine (guided, one-time)

A USB DSC token can only be reached by software on the **same computer** as the
browser (browser security). So each signer installs the small **DSC Bridge**
once. The app makes this self-service:

- When a user clicks **Sign with DSC** and the bridge isn't installed, a popup
  offers the **right installer for their OS** (auto-detected).
- Admins can also hand it out from **DSC Settings → Download DSC Bridge**.

### Windows signer
1. Download `dsc-bridge-1.0.0-windows.zip`, extract it.
2. Double-click **install.bat** → approve the admin prompt.
   (Windows SmartScreen may warn "unknown publisher" → *More info → Run anyway*.
   Removed permanently only by code-signing — see Optional below.)
3. The token driver installs itself on Windows (or from the CA if prompted).
4. Plug in the token → click **Sign with DSC** → enter PIN once per session.

### Linux signer
1. `sudo apt install ./dsc-bridge_1.0.0_amd64.deb` (pulls in dependencies).
   Other distros: use the `.tar.gz` + `./install.sh`.
2. Install the token's PKCS#11 driver from the CA (e.g. Hypersecu `libcastle.so`).
3. Plug in the token → click **Sign with DSC** → enter PIN once per session.

After the one-time install the bridge **auto-starts on every login** — signers
never start it by hand.

---

## What each person experiences

| | First time on a machine | Every time after |
|--|------------------------|------------------|
| Click **Sign with DSC** | Popup → download + install bridge once | Signs (PIN once per session) |

---

## Optional polish (business decisions, not code)

- **Remove the Windows SmartScreen warning:** buy a code-signing certificate
  (EV/OV) and sign `dsc-bridge.exe`. This is the only way to remove the warning
  — an MSI does not remove it.
- **Proper Windows MSI:** add a WiX/go-msi step to the GitHub Actions CI
  (`build-bridge.yml`) — it builds on a cloud Windows runner (no PC needed). The
  ZIP + install.bat already do the same automation, so this is cosmetic.
- **Company-managed machines:** IT can push the installer silently org-wide via
  Group Policy / Intune (Windows) or Ansible / apt repo (Linux), so users get it
  with zero action.
- **Zero-install signing entirely:** switch to Aadhaar eSign / cloud-HSM signing
  (no USB token) — different compliance + per-signature cost, but no local
  install ever. See the team if bulk, install-free signing is required.

---

## Quick server checklist

- [ ] `bench build --app finstein_e_sign` + `bench restart` on the environment
- [ ] Site served over HTTPS with a valid certificate
- [ ] Installer URLs above return the files (200, not 404)
- [ ] A test document signs end-to-end from a real signer machine + token
