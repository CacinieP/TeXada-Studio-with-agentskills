# Local desktop preview acceptance — 2026-11-08

A self-contained macOS ARM development preview was built from PR #32 commit
`79677da`, with Homebrew framework CPython 3.13.16. It is **macOS 27+ only**:
the bundled Python binary declares minos 27.0, and the candidate app plist was
updated accordingly. This is not evidence of compatibility with older macOS.
The app is locally ad-hoc signed and deep signature verification passed; it is
not Developer ID signed or notarized, and no GitHub Release was created.
Model weights are external and are not in the package.

Acceptance in a fresh HOME, private app state and PATH=/usr/bin:/bin:
- Bundled Tectonic, pdfinfo and pdftoppm execute without Homebrew PATH.
- Offline Chinese/formula/table two-page PDF compiles with no missing characters.
- The actual bundled app starts its local backend.
- Settings persist 1B F16, 1B Q4 and 35B Q4 service aliases.
- Document create/read/save succeeds with version hashes.
- Native preview compiles and PDF export returns real PDF bytes.
- All 108 bundled Mach-O files were checked for external Homebrew/user dylib
  dependencies; none were found. Ad-hoc deep signature verification passed.

See acceptance.json and archive.json for measured checks, source identity,
archive size and SHA256. Candidate generation still needs a separately started
local model; the installer checks do not imply model weights are bundled or
that OCR content is correct. Stop previous Studio instances before testing,
because the application otherwise intentionally reuses a live local session.

The first build with uv standalone Python failed because zlib is a static
builtin without __file__. The build preflight now rejects that environment
before resource collection and explains how to use a framework Python.
Desktop packaging regression: 12 tests passed.

PR #32 remains unmerged because automatic approval review requested explicit
approval for merging its updated head into main. Hosted bundle CI separately
needs the prepared macOS 15 runner change, which current OAuth workflow scope
cannot push. These are distinct from this locally completed preview build.
