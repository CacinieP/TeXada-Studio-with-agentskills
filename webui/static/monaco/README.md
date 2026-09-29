# Local Monaco assets

The complete `monaco-editor@0.52.2` `min/vs/` tree is stored in `0.52.2/`, with
Microsoft’s original MIT [LICENSE](0.52.2/LICENSE) and per-file [SHA256SUMS](0.52.2/SHA256SUMS).

## Restore or verify

From the repository root:

```bash
python scripts/vendor_monaco.py
```

The script downloads the [pinned npm archive](https://registry.npmjs.org/monaco-editor/-/monaco-editor-0.52.2.tgz),
checks its SHA-512, extracts the assets and verifies each file. For an offline
archive, add `--archive /path/to/monaco-editor-0.52.2.tgz`.
On an allocated node, download the archive there according to the deployment rules.
Studio serves the installed assets locally; no frontend build is required.

## Authentication and caching

An authenticated `/studio` request sets a signed, 12-hour HttpOnly cookie scoped
to `/static/monaco/0.52.2/`. Asset requests, including workers and fonts, use that
cookie; API requests use the token. Reopen the authenticated Studio URL to renew
an expired cookie.

HTTPS requests receive a Secure cookie. Successful assets are cached privately;
unauthorized responses and the cookie-setting Studio page are not cached.
