# Independent AGY Review: Phase 0 Document Download Gate

## 1. Review Scope
- **Target**: Review of the `phase0_document_download.py` implementation, Document Download Gate run evidence (`document-dev-20260928-01`), Checkpoint/Resume logic, and regression tests.
- **Constraints**: Offline verification only. No live API requests, text parsing, RAG, or dataset GO/DROP decisions. No modifications to code or configuration.

## 2. 100-Item Sample Verification
- **Result**: Perfect Match.
- **Evidence**: Verified via offline script that the 100 candidates listed in `data/downloaded/document-dev-20260928-01/manifest.json` match the exact `pblancId`, `printFlpthNm`, and `printFileNm` sequentially from the original raw source files of `api-quality-dev-20260928-01`. No new or different API data was gathered.

## 3. Download Evidence & File Properties Verification
- **Result**: Exactly 100 files successfully downloaded and stored with matching properties.
- **Evidence**: An offline python check iterated over all 100 metadata files and raw byte files in `data/downloaded/document-dev-20260928-01/`:
  - **Count**: Target 100, HTTP Requests 100, SUCCESS 100, HTTP 200: 100. Redirects: 0.
  - **Uniqueness**: 0 duplicate URLs, 0 duplicate SHA-256 hashes.
  - **Format Match**: Declared extensions (`PDF`: 70, `HWP`: 15, `HWPX`: 15) perfectly match the `actual_format` detected.
  - **File Checks**: All 100 binary files exist, are non-empty, and their actual sizes and SHA-256 hashes match exactly with the corresponding `metadata.json`.

## 4. Format Identification Logic
- **Result**: Robust and conservative.
- **Evidence**: The code in `scripts/phase0_document_download.py` appropriately identifies formats without fully unpacking or parsing content:
  - **PDF**: Matches `%PDF-` signature.
  - **HWP**: Conservatively reads OLE structure without unpacking body to find `FileHeader` (preventing false positives for other OLEs).
  - **HWPX / XLSX / ZIP**: Checks `PK` zip signature and safely verifies `mimetype` and directory structures (`[Content_Types].xml`, `Contents/header.xml`) without risky ZIP extraction. Drops out to `UNKNOWN` on complex limits.

## 5. HTTP & Security Boundary Audit
- **Result**: Boundaries strictly observed.
- **Evidence**: 
  - `public_url` filters strictly for `https`, specific host (`www.bizinfo.go.kr`), and allowed query parameters (`atchfileid`, `filesn`), blocking userinfo auth.
  - `open_document` uses an empty `ProxyHandler` and a custom redirect handler. Secret configs are loaded only to check for credential reflections in URLs, headers, and bodies (which are cleanly rejected). No API keys were transmitted to the document server.
  - File byte reads loop safely up to a strict `max_file_bytes`, ignoring potentially false `Content-Length`.

## 6. Content-Type vs Format Verification
- **Result**: Accurately separated.
- **Evidence**: The code correctly identified `application/octet-stream` for all 100 HTTP requests, storing this observation in `content_type`. Crucially, it did not misuse this generic MIME type to claim formatting certainty. Format conclusions were strictly derived from the file byte signatures (`actual_format`).

## 7. Checkpoint / Resume Audit
- **Result**: Safely implemented.
- **Evidence**: `checkpoint` function accurately logs processing state. The `records` and `download(resume=True)` logic strongly verifies `manifest` parity, prevents downloading `SUCCESS` items again, asserts full checksum/size integrity for all pre-existing files, and halts if orphan or modified files exist.

## 8. Supplementary Downloads & Token Pairing
- **Result**: Did not download; token counts accurately paired.
- **Evidence**: The implementation generated 86 items with valid `flpthNm` URL/filename combinations. It calculated matching `@` separated tokens (`PAIR_COUNT_MATCH: 86`). Supplementary URLs were strictly not requested over HTTP, preserving the bounding limits. 

## 9. Primary Notice Hypothesis & Semantic Boundary
- **Result**: Scope respected.
- **Evidence**: The report generator properly set `primary_notice_hypothesis` to `SUPPORTED_BY_DOWNLOAD_EVIDENCE`, leaving `document_body_semantics`, `PDF_HWP_HWPX_XLSX_text_parsing`, `OCR`, and `RAG_value` as strictly `UNMEASURED`. The downloader makes no semantic claims beyond binary availability.

## 10. Existing Guardrails & Regression Tests
- **Result**: No existing tests were weakened.
- **Evidence**: Offline run of `./scripts/check-all.sh` executed and passed 136 Unit/Contract tests and 20 Integration tests. Modifications to `scripts/lib/validate.py` and `scripts/check-all.sh` only updated descriptions/names without omitting assertions.

## 11. 35 Staged Changes Audit
- **Result**: Code and Git states are clean.
- **Evidence**: 17 modified files and 18 created files exactly cover the downloader script, its contracts, 12 checkpoints, 2 reports, and test files. Untracked file count is 0. Secret `.env` files are not staged or leaked.

## 12. Final Verdict
**PASS**

## 13. Pre-Parsing Gate Checklist for Human Review
- [ ] Review `harness/workspace/reports/2026-09-28-codex-document-download-gate-report.md`.
- [ ] Confirm no external secrets were uploaded to remote tracking.
- [ ] Execute `git commit -m "feat(document): Phase 0 document download gate and evidence"` and push to `origin/dev`.
- [ ] Only upon approval, proceed to the Text Parsing / OCR evaluation phase.
