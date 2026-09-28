# Local Monaco assets

Version: `monaco-editor@0.52.2` (MIT, Microsoft).

The complete `min/vs/` tree and upstream `LICENSE` are vendored in `0.52.2/`.
Source: https://registry.npmjs.org/monaco-editor/-/monaco-editor-0.52.2.tgz
The pinned tarball SHA-512 is checked by `scripts/vendor_monaco.py` before
extraction. `0.52.2/SHA256SUMS` records each installed upstream file.

For a fresh node, run `python3 scripts/vendor_monaco.py` there. This downloads
the package directly on the node and verifies it; do not upload the large
package through SCP. An offline copy can be supplied with `--archive PATH`.
No npm install, build step, MCP service, or external CDN is needed at runtime.

The backend serves these files at `/static/monaco/0.52.2/`. A valid `/studio`
request sets a signed, 12-hour HttpOnly cookie scoped to that asset directory.
All asset requests, including workers and fonts, check the cookie; API routes
still require their existing token. Reopen the authenticated Studio URL when
the cookie expires. On HTTP the cookie is non-Secure; HTTPS requests receive
a Secure cookie. Successful assets are cached privately, while unauthorized
responses and the cookie-setting Studio page are not cached.
