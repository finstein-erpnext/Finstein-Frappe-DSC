# AGENTS.md

DSC digital-signing platform for Frappe/ERPNext v15. PAdES PDF signing via a hardware DSC USB token, using a local desktop "bridge agent" for the crypto.

## Repo layout — two independent toolchains

- `finstein_e_sign/` — the Frappe app (Python + JS). Module namespace is `finstein_e_sign.finstein_e_sign` (doctypes live under `finstein_e_sign/finstein_e_sign/doctype/`, not `finstein_e_sign/doctype/`).
- `dsc_bridge/` — a Go desktop agent that talks PKCS#11 to the token over localhost HTTPS. Its stateful files (`go.mod`, Go version) may not match the CI workflow (see below).

The two sides are coupled through the wire protocol only: the bridge serves `https://127.0.0.1:4645` (`/v1/status`, `/v1/certs`, `/v1/pair`, `/v1/sign`), and the browser JS calls it directly — the Frappe server never talks to the token.

## Frappe app

- **No `package.json` / npm.** Frontend deps (pdf.js) are vendored in `finstein_e_sign/public/js/vendor/`. After changing app assets run `bench build --app finstein_e_sign` + `bench --site <site> clear-cache` + `bench restart`. No DB migration is needed for code-only changes.
- **Tests are not pytest.** They are scripts run inside the bench site via `bench --site <site> execute`:
  - `finstein_e_sign.setup_demo.run` / `finstein_e_sign.setup_demo.teardown`
  - `finstein_e_sign.test_signing_pipeline.run_test` (end-to-end signing with a self-signed cert)
  - `finstein_e_sign.dsc_test.run` (rule-engine smoke test)
- **Do not** add "DSC Document Sign" to `doctype_js` in `hooks.py` — its folder-local JS is auto-loaded; listing it twice crashes the form with a "redeclaration of const" SyntaxError.
- The rules-engine `doc_events` registry in `hooks.py:37-76` is computed at import time from `_DEFAULT_TRACKED_DOCTYPES` + configured `DSC Rule` doctypes. Adding a DSC Rule for a **new** doctype requires a bench restart to take effect.
- Default agent port is **4645** everywhere in code (`api/signing.py`, `finstein_e_sign.js`). REQUIREMENTS.md's `8765` is stale — trust the code.
- Signing flow entrypoints are whitelisted APIs in `finstein_e_sign/api/signing.py` (`initiate`, `finalize`, `get_form_actions`, `retry`, `cancel`, `abort_in_progress`); the pyHanko work is in `finstein_e_sign/finstein_e_sign/signing_engine.py` (`prepare_pdf_for_signing`, `finalize_signed_pdf`).
- `hooks.py` overrides two core whitelisted methods for print/email gating — if you touch `download_pdf`/email paths, remember these overrides exist.
- Built-in CCA India trust store: `finstein_e_sign/finstein_e_sign/cca_india_trust_bundle.pem`.

## dsc_bridge (Go)

- Build/test via `dsc_bridge/build.sh` subcommands: `local`, `linux`, `linux-package`, `deb`, `windows`, `windows-x86`, `darwin-amd64|arm64|universal`, `all`, `msi`, `test`, `integration`.
- `go test ./...` covers unit tests; `./build.sh integration` runs SoftHSM2 integration tests (`-tags softhsm`) and needs `sudo apt install softhsm2 opensc` + `./test_setup.sh` first.
- Windows binaries are cross-compiled from Linux with MinGW (`gcc-mingw-w64-*`), for both amd64 and 386 — a windows runner can't build the 386 CGO binary. See `.github/workflows/build-bridge.yml`.
- `go.mod` declares `go 1.25.0` but the CI workflow pins `go-version: 1.22`. If CI fails with a Go-version error, bump the workflow.
- Tag pushes (`v*`) trigger a GitHub Release with all binaries.

## Shipped installers — keep in sync with dsc_bridge

`finstein_e_sign/public/downloads/` (and legacy `dsc_bridge/windows-package.zip`) hold prebuilt installers served to end users in-app (`.deb`, `.tar.gz`, Windows zips; all version `1.0.0`). When you change the bridge, rebuild these artifacts and bump the versions there and in `docs/production-rollout.md`, or in-app installs will ship stale binaries.

## Conventions

- Python: ruff is the formatter/linter — **tabs, double quotes, line length 110** (`pyproject.toml`). Prettier + eslint apply to JS. Run via `pre-commit install`.
- Doctype JSON schemas: 2-space indent, no trailing newline (`.editorconfig`).
- Docs live in `docs/` (MkDocs + mkdocs-material, `mkdocs serve` to preview); it's the source of truth for user-facing behaviour.
