# Software Requirements Specification
## Smart Personal Finance Management System (SPFM)

| Field | Value |
|---|---|
| Document version | 1.0 |
| Date | 18 August 2026 |
| Project type | Bachelor internship project (14 weeks) |
| Prepared for | ICTLab / USTH |
| Supervisor | MSc. Huỳnh Vinh Nam |
| Stack | HTML/CSS/JS · Python 3.11 + Flask · SQLAlchemy 2.x · PostgreSQL 15 |

---

## 1. Introduction

### 1.1 Purpose

This document specifies the functional and non-functional requirements for **SPFM**, a web-based personal finance management system with budget tracking and proactive overspending alerts. It is the contractual reference for implementation, review and acceptance of the internship project.

### 1.2 Scope

SPFM allows an individual to record income and expense transactions, import bank statements from Excel files, define per-category budgets, receive early warnings when spending pace exceeds plan, and optionally share **derived spending summaries** (not raw transactions) with trusted contacts. A separate administrator role manages system reference data and operations without access to transaction content.

**Explicitly out of scope** (see §8 for rationale): direct integration with real bank APIs, payment execution, mobile applications, credit scoring, minors' accounts.

### 1.3 Definitions

| Term | Meaning |
|---|---|
| **Ledger** | A book of accounts. `PERSONAL` (single owner) or `HOUSEHOLD` (shared by a family group). |
| **Account** | A store of money inside a ledger: cash wallet, bank account, e-wallet. Manually declared; no live bank connection. |
| **Transaction** | A single dated money movement (`IN`/`OUT`) belonging to one account. |
| **Category nature** | `COMMITTED` (rent, tuition, insurance), `SEMI_FIXED` (electricity, water, fuel), `DISCRETIONARY` (dining out, shopping). |
| **Budget** | A planned spending cap for one category in one calendar month. |
| **Safe-to-Spend (STS)** | Available balance minus unpaid committed items, forecast semi-fixed items, and the savings target for the period. |
| **Burn-rate alert** | A warning issued when *projected* end-of-period spending exceeds budget, based on elapsed-time pace. |
| **ShareGrant** | A revocable, time-bounded consent object authorising one user to view another user's derived spending data at a specified disclosure level. |
| **Disclosure level** | `L1` = per-category budget status (green/amber/red, no amounts); `L2` = per-category totals versus budget. |
| **Import template** | A per-bank column-mapping configuration that tells the parser how to read that bank's Excel statement. |
| **PDPL** | Law on Protection of Personal Data 2025, effective 01/01/2026, with Decree 356/2025/ND-CP. |

### 1.4 References

- IEEE 830-1998, Recommended Practice for Software Requirements Specifications.
- Law on Protection of Personal Data 2025 (Vietnam), effective 01/01/2026; Decree 356/2025/ND-CP. Transaction history and financial information are classified as **sensitive personal data**.
- Circular 64/2024/TT-NHNN on Open API in the banking sector, effective 01/03/2025.
- OWASP Top 10 (2021) and OWASP ASVS Level 1.

---

## 2. Overall Description

### 2.1 Product perspective

Self-contained three-tier web application. No external system dependency is required for the system to function.

```
┌──────────────────────────────────────────────┐
│  Browser — HTML / CSS / vanilla JS           │
│  Chart.js (statistics), Fetch API            │
└───────────────────┬──────────────────────────┘
                    │  HTTPS, JSON + server-rendered Jinja2
┌───────────────────▼──────────────────────────┐
│  Flask application                           │
│  ├── Blueprints: auth, txn, import, budget,  │
│  │   alert, share, stats, admin              │
│  ├── Service layer (business rules)          │
│  ├── ShareAccessGuard (single access gate)   │
│  └── APScheduler — nightly alert job         │
└───────────────────┬──────────────────────────┘
                    │  SQLAlchemy ORM
┌───────────────────▼──────────────────────────┐
│  PostgreSQL 15                               │
└──────────────────────────────────────────────┘
```

### 2.2 Actors

| Actor | Description |
|---|---|
| **Guest** | Unauthenticated visitor. May register or log in only. |
| **User** | Authenticated end user. Full control over own ledgers and consent grants. |
| **Admin** | Operator. Accounts are seeded directly in the database; **no self-registration flow exists**. Manages reference data and operations. Has **no read access to transaction content** (NFR-PRI-06). |

### 2.3 Assumptions and dependencies

- A1. Transactions are entered manually or imported from Excel. No live bank feed exists (see §8).
- A2. All amounts are in Vietnamese Dong (VND). No multi-currency support.
- A3. All users are legally adults (≥ 18). The system rejects declared dates of birth implying a minor.
- A4. Deployment is single-instance; horizontal scaling is not required.
- A5. Statement files are ≤ 5 MB and ≤ 10,000 rows.

### 2.4 Design constraints

| ID | Constraint |
|---|---|
| CON-01 | Backend must be Python 3.11+ with Flask; ORM must be SQLAlchemy. Raw SQL string interpolation is prohibited. |
| CON-02 | Frontend must be HTML/CSS/vanilla JavaScript. No SPA framework. |
| CON-03 | Database must be a relational SQL database (PostgreSQL 15 in production, SQLite acceptable for unit tests only). |
| CON-04 | Monetary amounts must be stored as `BIGINT` in VND minor units. Floating-point types are prohibited for money. |
| CON-05 | Architecture must be a layered monolith. Microservices, message brokers and service discovery are out of scope. |
| CON-06 | No custom cryptographic primitives. Only vetted libraries (`werkzeug.security`, `cryptography`). |

---

## 3. Functional Requirements

Priority: **M** = Must (acceptance-blocking), **S** = Should (implement if M is complete by week 10), **C** = Could.

### 3.1 Authentication and account management

| ID | Requirement | Pri |
|---|---|---|
| FR-01 | Guest can register with email, password and full name. Email must be unique and format-validated. | M |
| FR-02 | Guest can log in; on 5 consecutive failures for the same email, that account is locked for 15 minutes. | M |
| FR-03 | User can log out, invalidating the server-side session. | M |
| FR-04 | User can change password, requiring the current password for confirmation. | M |
| FR-05 | User can view and edit own profile (full name, display currency locale). | M |
| FR-06 | User can export **all** own data as a machine-readable archive (JSON + CSV). | M |
| FR-07 | User can request account deletion. All personal data is erased per NFR-PRI-04. | M |

### 3.2 Ledgers, accounts and transactions

| ID | Requirement | Pri |
|---|---|---|
| FR-08 | A `PERSONAL` ledger is created automatically on registration. | M |
| FR-09 | User can create, edit and archive money accounts (`BANK`, `CASH`, `EWALLET`) with name, opening balance and optional bank code. | M |
| FR-10 | For `BANK` accounts, the system stores **only the last 4 digits** of the account number. Full numbers and bank credentials are never accepted or stored. | M |
| FR-11 | User can create, read, update and delete transactions: date, amount, direction, account, category, description. | M |
| FR-12 | User can filter and search transactions by date range, account, category, direction and amount range, with pagination. | M |
| FR-13 | Deleting a transaction performs a soft delete retained for 30 days, then hard-deleted. | S |

### 3.3 Categories and classification

| ID | Requirement | Pri |
|---|---|---|
| FR-14 | The system provides a seeded two-level system category tree, each leaf tagged with a `nature` value. | M |
| FR-15 | User can create, rename and delete own custom categories. Deletion requires reassignment of affected transactions. | M |
| FR-16 | On import, the system applies ordered regex classification rules (`pattern → category`) to `merchant_norm`; unmatched rows fall back to `Uncategorised`. | M |
| FR-17 | User can override any auto-assigned category; the override is recorded and never re-overwritten by the rule engine. | M |

### 3.4 Excel statement import

| ID | Requirement | Pri |
|---|---|---|
| FR-18 | User can upload an `.xlsx`/`.csv` statement, select the target account and an active import template. | M |
| FR-19 | The parser supports both single-column signed amounts and separate debit/credit columns, configurable per template. | M |
| FR-20 | The system computes `dedup_key = SHA256(account_id ‖ posted_at ‖ amount ‖ ref_no ‖ description)` and rejects rows already present. | M |
| FR-21 | The system detects probable duplicates against manually entered transactions (same account, date within ±1 day, amount within ±1%) and presents them for a merge / keep-both decision. | M |
| FR-22 | Import runs in **preview mode** first: the user sees counts of new / duplicate / erroneous rows and a sample before confirming. No data is written until confirmation. | M |
| FR-23 | Rows that fail parsing are recorded with row number and reason, and are downloadable as an error report. | M |
| FR-24 | Import is transactional: on confirmation either all valid rows commit or none do. | M |
| FR-25 | User can view import history and roll back an entire batch within 24 hours. | S |

### 3.5 Budgets and alerts

| ID | Requirement | Pri |
|---|---|---|
| FR-26 | User can set a monthly budget amount per category, and copy the previous month's budgets forward. | M |
| FR-27 | The system computes and displays **Safe-to-Spend** for the current period. | M |
| FR-28 | **Threshold detector:** raise an alert when actual spending in a category reaches 80% and again at 100% of budget. | M |
| FR-29 | **Burn-rate detector:** on day *d* of *D*, project end-of-period spending as `spent / w(d)`, where `w(d)` is the median cumulative spending fraction for that category at day *d* over the trailing 6 months, falling back to `d/D` when fewer than 3 months of history exist. Raise an alert when `projected > budget × 1.05`. | M |
| FR-30 | Every alert carries a `dedup_key`; the same key must not fire again within a 72-hour cooldown. | M |
| FR-31 | Every alert includes a severity, a plain-language explanation of *why* it fired, and one concrete suggested action. | M |
| FR-32 | User can view an alert inbox, mark alerts read, and dismiss them. | M |
| FR-33 | Alerts are recomputed by a scheduled job once per day and on demand after each import. | M |
| FR-34 | **Recurring detector:** cluster transactions by normalised merchant, amount within ±5% and interval of 28–31 days; after 3 occurrences, register a recurring group and forecast the next charge. | S |

### 3.6 Statistics

| ID | Requirement | Pri |
|---|---|---|
| FR-35 | Dashboard shows current-month income, expense, net, and Safe-to-Spend. | M |
| FR-36 | Category breakdown (doughnut chart) for a selectable period. | M |
| FR-37 | Monthly trend (bar/line chart) over the trailing 12 months. | M |
| FR-38 | Budget progress list with per-category status colour and remaining amount. | M |
| FR-39 | Export any statistical view to CSV. | C |

### 3.7 Social features and consent-based sharing

| ID | Requirement | Pri |
|---|---|---|
| FR-40 | User can send, accept, decline and cancel friend requests. | S |
| FR-41 | User can create a `HOUSEHOLD` ledger, invite friends as members, and record transactions into it. Household members see household transactions only — **never** each other's personal ledgers. | S |
| FR-42 | User (grantor) can create a `ShareGrant` for a friend specifying: disclosure level (`L1` or `L2`), an optional category subset, and an expiry date **not exceeding 90 days**. | S |
| FR-43 | Only the grantor may initiate a grant. The system provides **no** mechanism to request access to another user's data. | S |
| FR-44 | User can revoke any grant instantly; revocation takes effect on the next request with no cache delay. | S |
| FR-45 | Grantee can view only the derived report permitted by the grant. Amounts are omitted entirely at `L1`. Balances, account numbers, merchant names and descriptions are never disclosed at any level. | S |
| FR-46 | Every access by a grantee is logged and **visible to the grantor**, showing who viewed what and when. | S |
| FR-47 | Expired grants are treated as revoked. No auto-renewal exists. | S |

### 3.8 Administration

| ID | Requirement | Pri |
|---|---|---|
| FR-48 | Admin logs in through the standard login form; the seeded `ADMIN` role grants access to `/admin`. No registration path creates an admin. | M |
| FR-49 | Admin can search users and lock/unlock accounts, reset passwords, and execute deletion requests. Listings show metadata only (email, status, registration date, last login) — never balances or transactions. | M |
| FR-50 | Admin can create, edit, version, activate and deactivate import templates, and validate a template against an uploaded sample file **without persisting** that file. | M |
| FR-51 | Admin can manage the system category tree and the ordered classification rule set. | M |
| FR-52 | Admin can edit default alert parameters (thresholds, burn-rate factor, cooldown, detector on/off). | M |
| FR-53 | Admin can view an operations dashboard (active users, import success rate per bank, job status, error rate) and query the audit log. All aggregate figures are suppressed when derived from fewer than 5 users. | M |

---

## 4. Data Requirements

### 4.1 Core entities

`users` · `ledgers` · `ledger_members` · `accounts` · `categories` · `transactions` · `categorization_rules` · `import_templates` · `import_batches` · `import_errors` · `budgets` · `recurring_groups` · `alerts` · `alert_configs` · `friendships` · `share_grants` · `share_access_logs` · `audit_logs`

### 4.2 Mandatory data rules

| ID | Rule |
|---|---|
| DR-01 | All monetary columns are `BIGINT` VND. `FLOAT`, `REAL` and `DOUBLE PRECISION` are prohibited for money. |
| DR-02 | `transactions.dedup_key` carries a `UNIQUE` constraint enforced **at the database level**, not only in service code. |
| DR-03 | All timestamps are stored as `TIMESTAMP WITH TIME ZONE` in UTC; presentation converts to `Asia/Ho_Chi_Minh`. |
| DR-04 | Every table carrying personal data has a `created_at`; mutable tables also carry `updated_at`. |
| DR-05 | Foreign keys from a user's data to `users` use `ON DELETE CASCADE` so that erasure is complete and verifiable. |
| DR-06 | Schema changes are managed exclusively through Alembic migrations. `create_all()` is prohibited outside tests. |
| DR-07 | Indices are required on `transactions(account_id, posted_at)`, `transactions(dedup_key)`, `alerts(user_id, triggered_at)`, `share_grants(grantee_id, valid_until)`. |

---

## 5. External Interface Requirements

### 5.1 User interface

- **UI-01** Responsive layout usable from 360 px to 1920 px width.
- **UI-02** Every destructive action (delete transaction, delete category, revoke grant, delete account) requires explicit confirmation naming the affected object.
- **UI-03** The import flow is a four-step wizard: *upload → map/preview → resolve duplicates → confirm*. Progress and step state are always visible.
- **UI-04** All monetary values are rendered with Vietnamese thousands grouping and the `₫` suffix.
- **UI-05** Error messages state what failed and what the user should do next; raw stack traces are never shown.

### 5.2 API

- **API-01** JSON over HTTPS, resource-oriented paths under `/api/v1/`.
- **API-02** Standard status codes: `200`, `201`, `400`, `401`, `403`, `404`, `409` (duplicate), `413` (file too large), `422` (validation), `429` (rate limited), `500`.
- **API-03** Error body shape: `{"error": {"code": "...", "message": "...", "details": [...]}}`.
- **API-04** All list endpoints support `?page=` and `?per_page=` with a maximum page size of 100.

---

## 6. Non-Functional Requirements

### 6.1 Security — authentication and session

| ID | Requirement | Verification |
|---|---|---|
| NFR-SEC-01 | Passwords are hashed with `pbkdf2:sha256` (≥ 600,000 iterations) or bcrypt (cost ≥ 12) via `werkzeug.security`. Plaintext or reversible storage is a defect of the highest severity. | Inspect DB; no reversible value present |
| NFR-SEC-02 | Password policy: minimum 10 characters, at least three of {lowercase, uppercase, digit, symbol}, and rejection against a list of the 10,000 most common passwords. | Unit test |
| NFR-SEC-03 | Session cookies are set `HttpOnly`, `Secure`, `SameSite=Lax`, with an idle timeout of 30 minutes and an absolute lifetime of 12 hours. | Inspect response headers |
| NFR-SEC-04 | The session identifier is regenerated on login and on privilege change, to prevent session fixation. | Manual test |
| NFR-SEC-05 | `SECRET_KEY`, database URI and all credentials are read from environment variables. No secret is committed to the repository. | Repository scan (`gitleaks`) |
| NFR-SEC-06 | Rate limiting via Flask-Limiter: 10 requests/minute on `/login` and `/register`, 5 uploads/minute on `/import`, 300 requests/minute globally per IP. | Load test |
| NFR-SEC-07 | Admin accounts are provisioned only by a seed script executed against the database. No runtime code path can elevate a `USER` to `ADMIN`. | Code review |

### 6.2 Security — application

| ID | Requirement | Verification |
|---|---|---|
| NFR-SEC-08 | All database access goes through the SQLAlchemy ORM or bound parameters. String-concatenated or f-string SQL is prohibited. | Static scan (`bandit`, grep for `text(f"`) |
| NFR-SEC-09 | Jinja2 autoescaping remains enabled. The `\|safe` filter must not be applied to any user-supplied value. | Code review |
| NFR-SEC-10 | CSRF protection via Flask-WTF on every state-changing form and non-GET endpoint. | Test: replay without token → `400` |
| NFR-SEC-11 | Response headers set via Flask-Talisman: `Content-Security-Policy` (no `unsafe-inline`, no `unsafe-eval`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, HSTS. | Header inspection |
| NFR-SEC-12 | Uploads: extension whitelist `.xlsx`/`.csv`, `MAX_CONTENT_LENGTH` of 5 MB, magic-byte verification, `secure_filename()`, storage outside the web root under a generated UUID, and deletion within 24 hours of processing. | Test with renamed executable |
| NFR-SEC-13 | All input is validated server-side by explicit schemas (Marshmallow or Pydantic). Client-side validation is treated as a convenience only. | Test: bypass client, submit malformed payload |
| NFR-SEC-14 | Every object-scoped endpoint verifies ownership before acting. Sequential identifiers must never confer access (prevention of IDOR / broken object-level authorisation). | Test: user A requests user B's `transaction_id` → `404` |
| NFR-SEC-15 | Third-party dependencies are pinned in `requirements.txt` and audited with `pip-audit`; no dependency carries a known High or Critical CVE at submission. | CI report |
| NFR-SEC-16 | `DEBUG=False` in any non-local environment. The Werkzeug debugger must never be reachable. | Deployment checklist |

### 6.3 Personal data protection

Financial information and transaction history are **sensitive personal data** under the PDPL 2025 and Decree 356/2025/ND-CP. The following requirements are compliance-relevant, not merely good practice.

| ID | Requirement | Verification |
|---|---|---|
| NFR-PRI-01 | **Data minimisation.** The system collects only email, full name and self-entered financial records. It must not collect or store: national ID number, full bank account numbers, card numbers, bank login credentials, OTPs, biometric data, or precise location. | Schema review |
| NFR-PRI-02 | **Explicit consent.** Registration presents a privacy notice that states plainly that transaction history is sensitive personal data, what is processed, why, and for how long. Consent is an unticked opt-in — never pre-selected, never bundled with the terms of service. | UI review |
| NFR-PRI-03 | **Withdrawal of consent.** A single settings action revokes all outstanding `ShareGrant` records and stops all sharing. The effect is immediate and requires no counterparty approval. | Functional test |
| NFR-PRI-04 | **Right to erasure.** An account deletion request purges all personal data within 72 hours. Retained afterwards: only irreversibly anonymised aggregates (no identifier, no linkage) plus a deletion record containing a salted hash of the email for audit purposes. | Post-deletion DB query returns zero rows |
| NFR-PRI-05 | **Right to portability.** Full export in JSON and CSV, delivered within 60 seconds for a dataset of 10,000 transactions. | Timed test |
| NFR-PRI-06 | **Administrative blindness.** No admin interface, endpoint or query exposes transaction amounts, descriptions, merchants or balances of an identified user. This is enforced by the absence of such a code path, not by UI omission. | Code review + penetration attempt |
| NFR-PRI-07 | **Encryption at rest for identifying fields.** `accounts.masked_number` and `accounts.bank_code` are encrypted at column level (Fernet, AES-128-CBC + HMAC) with a key held outside the database. | Inspect raw column contents |
| NFR-PRI-08 | **Transport encryption.** TLS 1.2+ for all traffic; plain HTTP redirects to HTTPS. | `sslscan` |
| NFR-PRI-09 | **Log hygiene.** Application logs must never contain passwords, session tokens, transaction amounts, descriptions or full email addresses. Emails appear masked (`ab***@domain.com`). | Log grep after test scenario |
| NFR-PRI-10 | **Retention.** Audit logs retained 12 months; import error reports 30 days; uploaded source files 24 hours; soft-deleted transactions 30 days. Retention is enforced by a scheduled purge job, not by manual action. | Job execution log |
| NFR-PRI-11 | **Purpose limitation.** Personal data is used solely to deliver the features in §3. No profiling, credit scoring, advertising, model training or third-party disclosure occurs. | Documented in privacy notice |
| NFR-PRI-12 | **Sharing is derived-only.** Grantees receive aggregated figures computed at request time. Raw transaction rows are never serialised to a grantee response at any disclosure level. | Response payload inspection |
| NFR-PRI-13 | **Access transparency.** Every grantee read writes a `share_access_logs` row that the grantor can view. Log writing failure aborts the read. | Functional test |
| NFR-PRI-14 | **Single access gate.** All cross-user reads pass through one `ShareAccessGuard` component. No blueprint may query another user's data directly. | Architecture test asserting call graph |
| NFR-PRI-15 | **No minors.** Registration rejects a declared date of birth indicating an age below 18, since processing children's data requires safeguards outside this project's scope. | Boundary test |
| NFR-PRI-16 | **Breach procedure.** A documented procedure exists covering detection, containment, notification of affected users, and record-keeping. Delivered as a document; no implementation required. | Deliverable check |

### 6.4 Performance

| ID | Requirement |
|---|---|
| NFR-PERF-01 | 95th-percentile server response time under 500 ms for read pages, measured with a seeded dataset of 50,000 transactions and 20 concurrent users. |
| NFR-PERF-02 | A 5,000-row import completes preview within 10 seconds and commit within 20 seconds. |
| NFR-PERF-03 | The dashboard issues no more than 10 SQL queries per render. N+1 query patterns are defects (verified with `flask-sqlalchemy-debug` or query counting in tests). |
| NFR-PERF-04 | The nightly alert job processes 1,000 users within 5 minutes. |
| NFR-PERF-05 | Initial page payload under 500 KB excluding cached assets. |

### 6.5 Reliability and integrity

| ID | Requirement |
|---|---|
| NFR-REL-01 | Import, transaction write and grant revocation are atomic: on any error the transaction rolls back with no partial state. |
| NFR-REL-02 | Re-importing an identical file produces zero new rows (idempotence), verified by an automated test. |
| NFR-REL-03 | Every account's derived balance equals `opening_balance + Σ(IN) − Σ(OUT)`; a consistency check script verifies this for all accounts. |
| NFR-REL-04 | Daily automated database backup with a documented and **executed** restore drill. Recovery point objective 24 h, recovery time objective 4 h. |
| NFR-REL-05 | Unhandled exceptions return a generic error page, log a correlation ID server-side, and never leak internals. |

### 6.6 Usability, maintainability, portability

| ID | Requirement |
|---|---|
| NFR-USE-01 | A new user can record their first transaction within 2 minutes without documentation, verified with 3 test subjects. |
| NFR-USE-02 | Interface language is Vietnamese; date format `dd/mm/yyyy`; currency grouping per Vietnamese convention. |
| NFR-USE-03 | Colour is never the sole carrier of meaning; budget status also carries a text label (contrast ratio ≥ 4.5:1). |
| NFR-MNT-01 | Strict layering: `routes → services → repositories → models`. No route contains business logic; no route imports a model directly. |
| NFR-MNT-02 | Automated test coverage ≥ 60% overall and ≥ 85% for the import parser, dedup logic, budget calculator and alert detectors. |
| NFR-MNT-03 | Code conforms to PEP 8, enforced by `ruff`/`flake8` in CI. Public service functions carry type hints and docstrings. |
| NFR-MNT-04 | All configuration is environment-variable driven; no environment-specific value is hard-coded. |
| NFR-MNT-05 | `README.md` allows a clean machine to reach a running instance with seed data in under 15 minutes. |
| NFR-PORT-01 | Runs on Linux and Windows with Python 3.11+; deployable via `docker compose up`. |
| NFR-PORT-02 | Functional on current Chrome, Firefox and Edge. No Internet Explorer support. |

---

## 7. Acceptance Criteria

The project is accepted when all **M**-priority functional requirements pass, all §6 non-functional requirements are verified by their stated method, and the following measured results are reported.

### 7.1 Required experiments

Because the evaluation dataset is synthetic, ground truth is available. Three quantitative results are mandatory in the final report.

**E1 — Alert quality.** Inject *N* ≥ 50 labelled overspending episodes across 24 months of synthetic data. Report:

| Method | Precision | Recall | F1 | Mean lead time (days) |
|---|---|---|---|---|
| Static threshold at 80% | | | | |
| Linear pace `d/D` | | | | |
| Historical pace `w(d)` (FR-29) | | | | |

*Lead time* = days between the alert and period end. A method that detects overspending accurately but only on the final day has limited practical value; this metric captures that distinction.

**E2 — Duplicate detection.** Report precision and recall of `dedup_key` matching plus fuzzy matching (FR-20, FR-21) across four scenarios: identical re-import, overlapping date ranges, import after manual entry, and reordered rows.

**E3 — Recurring detection** (if FR-34 implemented). Precision and recall against the injected subscription list.

### 7.2 Deliverables

1. Source repository with commit history and `README.md`.
2. Alembic migrations plus a seed script (system categories, classification rules, import templates for ≥ 3 banks, one admin account).
3. Synthetic data generator producing 24 months of realistic activity — salary on day 5, rent on day 1, evenly distributed dining, month-end-skewed shopping, ≥ 3 recurring subscriptions.
4. Automated test suite meeting NFR-MNT-02.
5. Internship report including the §7.1 results, the ERD, and the §8 scope-exclusion rationale.
6. Breach-response procedure document (NFR-PRI-16).

---

## 8. Excluded Scope and Rationale

Recording *why* something was excluded is part of the specification. Each exclusion below is a deliberate engineering decision, not an omission.

| Excluded | Rationale |
|---|---|
| **Direct bank API integration** | Circular 64/2024/TT-NHNN structures Open API access around a contract between the bank and the third party. A student project cannot obtain such an agreement. The system therefore defines a `TransactionSource` interface with a `FileImportAdapter` implementation, so a future banking adapter can be added without changing the domain layer. |
| **Third-party aggregators (SePay, Casso, etc.)** | Oriented toward business payment reconciliation, require a corporate account, and charge fees. Not viable at this scope. |
| **SMS / notification reading** | Android `READ_SMS` is effectively unavailable under current Google Play policy, and notification-derived data lacks reference numbers and balances, making reliable deduplication impossible. |
| **Minors' accounts and parental control** | The PDPL 2025 imposes stricter conditions on processing children's data, including verified guardian consent. Out of proportion for a 14-week project. Sharing is therefore modelled as voluntary, revocable, symmetric consent between adults. |
| **Disclosure levels L3/L4 (transaction-level sharing)** | Merchant names and descriptions reveal location, health and lifestyle information. `L1`/`L2` satisfy the stated use case — "is this person overspending?" — without that exposure. |
| **Balance sharing** | Never disclosed at any level. It answers no budgeting question and carries the highest disclosure risk. |
| **Access-request mechanism** | Deliberately absent (FR-43). If a request feature existed, refusing it would carry a social cost, allowing a stronger party to pressure a weaker one into consent. Grants are grantor-initiated only. |
| **Multi-currency, investments, debt tracking, mobile app, microservices** | Beyond the internship timebox. |

---

## Appendix A — Requirements Traceability

| Use case | Functional requirements |
|---|---|
| UC-G-01 Register | FR-01, NFR-PRI-02, NFR-PRI-15 |
| UC-G-02 Log in | FR-02, NFR-SEC-01…04, NFR-SEC-06 |
| UC-U-02 Manage money accounts | FR-09, FR-10, NFR-PRI-01, NFR-PRI-07 |
| UC-U-03 Record transactions | FR-11, FR-12, FR-13 |
| UC-U-05 Import statement | FR-18…FR-20, FR-22, FR-24, NFR-SEC-12, NFR-REL-02 |
| UC-U-06 Resolve import results | FR-21, FR-23, FR-25 |
| UC-U-07 Set budgets | FR-26, FR-27 |
| UC-U-08 Handle alerts | FR-28…FR-33 |
| UC-U-09 View statistics | FR-35…FR-39, NFR-PERF-01, NFR-PERF-03 |
| UC-U-10 Friends | FR-40 |
| UC-U-11 Grant sharing | FR-42, FR-43, FR-45, NFR-PRI-12, NFR-PRI-14 |
| UC-U-12 Revoke and audit | FR-44, FR-46, FR-47, NFR-PRI-03, NFR-PRI-13 |
| UC-U-14 Household ledger | FR-41 |
| UC-U-15 Export and delete | FR-06, FR-07, NFR-PRI-04, NFR-PRI-05 |
| UC-A-02 Manage users | FR-49, NFR-PRI-06 |
| UC-A-03 Manage import templates | FR-50 |
| UC-A-04 Manage categories and rules | FR-51 |
| UC-A-05 Configure alerts | FR-52 |
| UC-A-06 Operations and audit | FR-53, NFR-PRI-09, NFR-PRI-10 |

---

## Appendix B — Kill-Switch Policy

If **M**-priority requirements are not complete by the end of week 10, all **S** and **C** items (FR-13, FR-25, FR-34, FR-39, FR-40…FR-47) are dropped and weeks 11–12 are reallocated to hardening, testing and the §7.1 experiments. This policy is stated to the intern in week 1 so that descoping is a planned outcome rather than a late failure.

---

*Prepared by MSc. Huỳnh Vinh Nam — ICTLab, USTH*
