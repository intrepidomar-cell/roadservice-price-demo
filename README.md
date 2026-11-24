# Road Service — Modular Readers V3

Prototype for local PDF extraction and read-only same-vendor historical comparison. Public/cloud demo: **synthetic data only**. This archive contains source code and tests with fictitious data, not the uploaded work orders or their extracted contents.

## Architecture

- `app.py`: Streamlit UI; opens the current PDF, displays original and extraction, then queries historical prices. Global Comparison remains pending.
- `core/invoice_router.py`: cheap signatures from the first two pages; imports only the selected reader. Unsupported/ambiguous formats stop without fallback. Do not route by filename.
- `core/models.py`: shared `Invoice` and `LineItem` contracts, nullable values, source columns, warnings, code candidates and comparison eligibility.
- `core/pdf_utils.py`, `core/validation.py`: small generic functions. No vendor-specific branching.
- `readers/loves.py`: specialized Love's / Speedco Total Truck Care estimate layout (eight printed columns). Source values, metadata, notes, tire details, discounts, summary and reconciliation. Distinguishes printed zero from blank. No automatic hourly-unit conversion or authoritative part code inference. Parts/Labor code candidates require review before historical matching. Positive miscellaneous charges are eligible if totals reconcile, subject to vendor/history availability.
- `readers/decisiv.py`: independent coordinate-based reader for Freightliner Northwest / Gordon Truck Centers estimates. Returns the normalized model directly, preserves operations, warranty, part codes where printed, quantities, printed prices and amounts, operation totals, summary components and case notes. Uses letter-size digital layout; other variants require validation.
- `readers/gwm.py`: GWM Commercial Auto Glass digital invoice layout, five printed columns. Preserves service date, product/service label, description, prices, non-taxable marks and source identity.
- `readers/fleetperform.py`: explicit compatibility route for FleetPerform name + Hrs/Qty heading; temporarily calls the previous L10 code. No generic fallback. Needs a dedicated reader and regression tests using representative documents before removing L10.
- `legacy/`: transitional source and adapters; not executed for Love's. `core/legacy_adapter.py` bridges previous results.
- `invoice_display.py`, `extracted_items.py`: display and eligible comparison items.
- `roadservice_db.py`, `pricing.py`, `storage_reader.py`: SQL reads, statistics and PDF viewer; schema unchanged. Historical PDF is re-extracted only on explicit open; historical prices are queried from SQL. Existing `reconciliation.py` is retained as an optional development utility, not called during normal extraction.
- `tests/`: synthetic regression tests; not loaded by Streamlit.

## Install locally (Windows / VS Code)

1. Commit the current working version in Git (without any confidential PDFs or secrets). Create a branch, e.g. `git switch -c modular-readers-v3`.
2. Extract the ZIP. Copy its contents into your existing repository, merging folders and replacing matching files. Keep `.git/`, `.venv/`, `.streamlit/secrets.toml` and `.env` intact. Do not copy actual PDFs into Git. No SQL migration is required.
3. Once the new version has been copied, remove these **obsolete root files** if present: `operation_reader.py`, `invoice_reader_l10.py` (now in `legacy/`), `fix_duplicate_display.py`, `test_lectura_sintetica.py`, `INSTRUCCIONES.md`. Old README and validator are replaced. Do not remove the `legacy/` folder yet.
4. If dependencies need updating: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
5. Start: `.\.venv\Scripts\python.exe -m streamlit run app.py`.
6. For authorized local documents only, upload the PDFs in the local app. Public Streamlit Cloud remains synthetic-only. Local execution alone does not authorize handling corporate data; follow IT requirements.
7. Regression tests: `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt` then `.\.venv\Scripts\python.exe -m pytest -q tests`.
8. Batch validation without Streamlit or Supabase: `.\.venv\Scripts\python.exe validar_estimates.py "C:\path\to\authorized\PDFs"`.
9. Review `git status`, `git diff` and staged files. Push only code/synthetic tests after validation. Do not push real PDFs, extracted data, or secrets. `.gitignore` does not protect files already tracked; remove such files from tracking through an approved process.

## Scope and limitations

- Three provided Love's/Speedco estimates were inspected and parsed locally. All 17 line items (including two with no printed amounts) and three printed totals were recovered and reconciled. This establishes coverage for these samples, not every Love's format or final invoice. Final invoice status is not inferred from a missing estimate marker.
- Six automated tests with generated synthetic PDFs pass in the development environment. Actual Streamlit rendering and live Supabase queries were not executed in that environment; local app integration and historic seed matching must still be checked. Existing dependency constraints were retained.
- No OCR. A new format needs an independent reader, a signature and regression fixtures. Current Love's parser is validated on the observed eight-column layout, including tables starting on page 2; continuation across pages without a repeated table header and other revisions need samples.
- No automatic storage or database ingestion. Private Storage remains limited to the existing synthetic FleetPerform bucket/paths. Vendor-name matching is provisional; map corporate vendor IDs and approve historical data before production use. Fee comparisons use printed totals, not equivalent per-unit rates. Zero-valued estimates do not enter comparisons.
- Historical extraction of previously stored PDFs is on demand only; no batch reprocessing on every price query.

## Add a reader

Create `readers/<format>.py` with `read(pdf, path) -> Invoice`. Add a unique signature in `core/invoice_router.py` and a synthetic test. Reuse shared primitives, but do not alter other readers to handle the new format. Use an existing reader only when the layout and extraction semantics are practically identical. If a new reader needs many special-case branches, split it into a distinct reader. Never infer missing monetary values or payment status.

## V2 — Decisiv validation and historical comparison

- Ten supplied estimate PDFs (seven cases, eight byte-distinct documents) were read locally. All 40 operations and 100 operation line items were recovered, plus ten separate summary-only Shop Supplies records. Printed summary and operation aggregate reconcile in all ten files. One operation has neither part price nor printed Parts Total, so its itemized reconciliation is unavailable; no inferred price is stored.
- The Pacific sample has 13 printed part codes and an extended amount exceeding the printed unit price by $125. The summary also prints Core of $125; this is preserved separately, not double counted or automatically allocated.
- Case number, estimate version, updated timestamp and source SHA-256 are retained to support later deduplication; no actual historical ingestion or deduplication is implemented in this release.
- Positive non-warranty miscellaneous charges are candidates for read-only historical comparison. Parts and labor are preserved but withheld from the current exact code/UOM comparison until their identity, unit and pricing basis are homologated. Generic operation codes are not unique labor service IDs. No historical records are created from these estimates.
- No new dependency, SQL migration, or live DB access. Love's and FleetPerform source files are unchanged. The UI displays Decisiv operations separately and the final economic summary only once. Streamlit rendering and Supabase live integration still require local verification.

## V3 — GWM Commercial Auto Glass (initial coverage)

- Two actual one-page invoices, four detail rows, both totals reconciled with the header and detail. No real PDFs, extracted records or private metadata are included.
- The new reader uses coordinates and the common model; no L10 dependency. It does not assume two rows. Tested with synthetic five-row invoice, multiline description, multiple service dates, quantity greater than one, large dollar amounts, missing price and mismatched totals. Ten regression tests passed in total; all 13 previously supplied Love's/Decisiv PDFs were also rerun with the same row counts and totals.
- Positive, consistent recognized glass and installation lines are passed to `extract_candidates`: code is the complete printed Product/Service identifier, unit `EA` is a normalized per-product/per-service quantity (not printed UOM or hours), and price is the printed Unit Price. No invented manufacturer equivalence: preserve the distinct description; confirm catalog mapping before historical ingestion. New or unclassified items are retained but not automatically compared.
- Service location is not treated as a verified physical vendor branch. No evidence of payment, no automatic historical inserts, and no estimates promoted into final invoices. Actual comparison requires validated matching invoice records and vendor/shop mapping in PostgreSQL; existing query/schema remain unchanged.
- Initial coverage only: real multi-page invoices, different product/service types and tax/discount variants need validation. Pages without a repeated table heading are not guessed. Incomplete or discrepant monetary extraction blocks comparison.
- Changed `core/invoice_router.py`, `invoice_display.py` (generic caption), `app.py` (price-basis caption includes normalized unit) and README. Added `readers/gwm.py` and `tests/test_gwm.py`. Other readers and SQL/pricing/storage files are byte-identical to V2. No dependency changes. Live Streamlit and Supabase were not tested.

## Modular V4 — compact invoice presentation

All supported readers share the same view for both uploaded and historical PDFs:
1. **Document Information**, collapsed by default, contains metadata, reconciliation, reader warnings and any pending legacy rows.
2. **Repair Details**, one bordered container with Complaint before charges; operations, tables and their associated subtotals remain together. Decisiv Parts Total and Operation Total are display-only rows, not comparison items. Legacy subtables are associated by explicit table/task ID.
3. **Economic Summary**, a single separate container when printed summary data exists.

Service comments and general case notes are no longer rendered; the reader results are retained unchanged. No changes to readers, normalized data, comparison logic, database, or dependencies. Tests simulate the Streamlit display contract (no running Streamlit server or Supabase connection required). Run `python -m pytest tests/` locally. To update V3, replace `app.py` and `invoice_display.py`; optionally copy `tests/test_invoice_display.py` and this README. Preserve `.git`, `.venv`, `.streamlit`, and credentials.


## Modular V4.1 — independent collapsible sections

All supported readers use the same three independent Streamlit expanders: Document Information (collapsed), Repair Details (expanded), and Economic Summary (expanded, only when summary data exists). No placeholder summary is created. The detail content, table order, and historical comparison behavior are unchanged from V4. To update V4, replace only `invoice_display.py` (tests and README optional).


## Modular V4.2 — hide page provenance from visible tables

Page, End page and legacy pagina columns are hidden in the shared display, including subtables and economic summaries. Operation captions retain only the operation code when present. Row order, the overall document page count, internal source page references and comparison data are unchanged. Replace only `invoice_display.py` to update V4.1; tests and README are optional.

## Modular V4.3 — two digital invoice readers (no OCR)

This release is based directly on V4.2, not on the withdrawn OCR experiment. Adds `readers/a_mobile_maintenance.py`, `readers/battleground_wrecker.py`, their explicit signatures in `core/invoice_router.py`, and `tests/test_mobile_and_battleground.py`. All existing readers, presentation, database queries, price calculation and dependencies remain unchanged.

- A Mobile Maintenance: one actual digital invoice, five line items and four printed economic summary values. All four checks reconcile. The reader preserves printed truncated item codes and separates drive time from repair labor. It preserves service location separately from vendor address. Variable-length rows and wrapped descriptions tested synthetically; real additional products and multi-page layouts remain unvalidated. Only recognized single-quantity fees enter comparison candidates.
- Battleground Wrecker: six actual digital invoices, 61 detail rows, all totals and row arithmetic reconciled. Includes two PDFs with signature-only second pages. The charge name and continuation details remain together, retaining distinct part codes even when charge labels repeat. Explicit codes with normalized EA and recognized single-quantity fees are eligible for matching. Uncoded parts, fluid products pending catalog mapping and labor without an explicit unit remain visible but not eligible. Requested date is not assumed to be invoice issue date. Service location does not establish a vendor branch. No proof of payment inferred. No generic Towbook reader or guesses about table continuations without repeated headers.
- 22 automated synthetic tests passed; the 15 prior real digital samples produced identical complete normalized outputs compared with V4.2. The previously supplied scanned AMS Towing document remains unsupported. No corporate PDFs or extracted data included. Live Streamlit and Supabase were not tested, and no database writes or schema changes were made. Future historical data must use consistent code, vendor ID and unit conventions.
- Upgrade from V4.2: copy the two new reader files and replace `core/invoice_router.py`; optionally copy the test and README. Alternatively merge the full ZIP into your repository, keeping `.git`, `.venv`, `.streamlit` and `.env`. No dependency updates needed. Do not commit confidential documents or secrets.
