# Software Requirements Specification
## Smart Personal Finance Management System (SPFM)
### Version 2.0 — Reduced scope for a 15-week bachelor internship

| Field | Value |
|---|---|
| Document version | 2.0 (supersedes 1.0) |
| Date | 18 August 2026 |
| Supervisor | MSc. Huỳnh Vinh Nam — ICTLab, USTH |
| Stack | HTML/CSS/vanilla JS · Python 3.11 + Flask · SQLAlchemy 2.x · **MySQL 8.0.16+ (InnoDB)** |
| Size | 11 use cases · 26 functional requirements · 34 non-functional requirements · 11 MySQL constraints |

> **Change from v1.0.** Scope reduced from 53 to 26 functional requirements. Removed: friend-request workflow, household ledgers, transaction-level sharing, recurring-payment detection, soft delete, import rollback, visual template editor, admin rule editor. Rationale for each removal is recorded in §7 — exclusions are design decisions and must be defended as such at the viva.

---

## 1. Introduction

### 1.1 Purpose

SPFM lets one person record and import personal financial transactions, plan a monthly budget, and receive **early** warnings when spending pace will exceed that budget. A minimal consent-based mechanism allows sharing a spending-status summary — never raw transactions — with one trusted contact.

### 1.2 Product goal

The system's distinguishing claim is *timing*: a warning issued on day 12 of the month is useful, one issued on day 30 is not. The burn-rate detector (FR-18) exists to demonstrate this claim, and experiment E1 (§6.1) exists to measure it.

### 1.3 Definitions

| Term | Meaning |
|---|---|
| **Account** | A store of money: cash wallet or bank account. Manually declared; no live bank connection exists. |
| **Category nature** | `COMMITTED` (rent, tuition), `SEMI_FIXED` (electricity, fuel), `DISCRETIONARY` (dining, shopping). |
| **Safe-to-Spend** | Balance − unpaid committed items − forecast semi-fixed items − savings target. |
| **Burn-rate alert** | Alert raised when *projected* end-of-month spending exceeds budget, based on elapsed-time pace. |
| **ShareGrant** | A revocable, expiring consent record letting one named user view another's budget status. |
| **Import template** | Per-bank column mapping telling the parser how to read that bank's statement. Seeded configuration, not user-authored. |
| **PDPL** | Law on Protection of Personal Data 2025 (effective 01/01/2026) and Decree 356/2025/ND-CP. |

### 1.4 Actors

| Actor | Description |
|---|---|
| **User** | Registers, logs in, owns exactly one personal ledger. |
| **Admin** | Seeded directly in the database; no registration path. Manages users and operations. **Has no read access to transaction content** (NFR-12). |

---

## 2. Use Cases

| ID | Use case | Actor | Priority |
|---|---|---|---|
| UC-01 | Register and log in | Guest | Must |
| UC-02 | Manage profile, export data, delete account | User | Must |
| UC-03 | Manage money accounts | User | Must |
| UC-04 | Record transactions manually | User | Must |
| UC-05 | Import a bank statement from Excel | User | Must |
| UC-06 | Resolve import conflicts and errors | User | Must |
| UC-07 | Plan monthly budgets | User | Must |
| UC-08 | Receive and handle spending alerts | User | Must |
| UC-09 | View spending statistics | User | Must |
| UC-10 | Share and revoke budget status | User | **Should** |
| UC-11 | Administer users and operations | Admin | Must |

---

## 3. Functional Requirements

### M1 — Authentication and account lifecycle (UC-01, UC-02)

| ID | Requirement |
|---|---|
| FR-01 | Guest registers with email, password and full name. Email is unique and format-validated. Registration shows a privacy notice with an unticked opt-in consent checkbox. |
| FR-02 | Guest logs in. After 5 consecutive failures on the same email, the account locks for 15 minutes. |
| FR-03 | User logs out (session invalidated server-side) and can change password, confirming with the current one. |
| FR-04 | User exports all own data as JSON + CSV, and can request account deletion which purges all personal data (NFR-10). |

### M2 — Ledger, accounts and transactions (UC-03, UC-04)

| ID | Requirement |
|---|---|
| FR-05 | A single personal ledger is created automatically on registration. |
| FR-06 | User creates, edits and archives money accounts (`CASH`, `BANK`) with name, opening balance and optional bank code. For bank accounts only the **last 4 digits** are stored; full numbers and bank credentials are never accepted. |
| FR-07 | User performs full CRUD on transactions: date, amount, direction (`IN`/`OUT`), account, category, description. |
| FR-08 | User filters and searches transactions by date range, account, category and direction, with server-side pagination. |
| FR-09 | The system seeds a two-level category tree, each leaf tagged with a `nature` value. User may add and rename custom categories; deletion requires reassigning affected transactions. |

### M3 — Excel statement import (UC-05, UC-06) — *technical core*

| ID | Requirement |
|---|---|
| FR-10 | User uploads an `.xlsx`/`.csv` statement and selects the target account plus an active import template. |
| FR-11 | The parser reads both single signed-amount columns and separate debit/credit columns, configured per template. Templates for at least 3 banks are provided as seed data. |
| FR-12 | Import runs in **preview mode** first, reporting counts of new / duplicate / erroneous rows with a sample. Nothing is written until the user confirms. Failed rows are listed with row number and reason, downloadable as an error report. |
| FR-13 | The system computes `dedup_key = SHA256(account_id ‖ posted_at ‖ amount ‖ ref_no ‖ description)` and rejects rows already present. Re-importing an identical file adds zero rows. |
| FR-14 | The system flags probable duplicates against manually entered transactions (same account, date ±1 day, amount ±1%) and asks the user to merge or keep both. |
| FR-15 | On confirmation, ordered regex rules (`pattern → category`) classify rows by normalised merchant; unmatched rows become `Uncategorised`. User overrides are recorded and never re-overwritten. Commit is atomic — all valid rows or none. |

### M4 — Budget and alerts (UC-07, UC-08) — *the "smart" component*

| ID | Requirement |
|---|---|
| FR-16 | User sets a monthly budget amount per category and can copy the previous month's budgets forward. |
| FR-17 | The system computes and displays **Safe-to-Spend** for the current month. |
| FR-18 | **Threshold detector:** alert when actual spending in a category reaches 80%, and again at 100%, of budget. |
| FR-19 | **Burn-rate detector:** on day *d* of *D*, project month-end spending as `spent / w(d)`, where `w(d)` is the median cumulative spending fraction for that category at day *d* over the trailing 6 months, falling back to `d/D` when fewer than 3 months of history exist. Alert when `projected > budget × 1.05`. MySQL has no `PERCENTILE_CONT`, so `w(d)` is computed **in Python** by the nightly job: SQL returns the daily cumulative sums, the median is taken in application code. This is also the more testable arrangement. |
| FR-20 | Every alert carries a `dedup_key` with a 72-hour cooldown, a severity, a plain-language explanation of why it fired, and one concrete suggested action. User views an alert inbox and marks alerts read or dismissed. Alerts recompute nightly and after each import. |

### M5 — Statistics (UC-09)

| ID | Requirement |
|---|---|
| FR-21 | Dashboard shows current-month income, expense, net, Safe-to-Spend, and a per-category budget progress list with status colour plus text label. |
| FR-22 | Category breakdown (doughnut) for a selectable period, and a 12-month trend chart. |

### M6 — Consent-based sharing (UC-10) — **Should**

Disclosure is limited to **L1**: per-category status colour only. No amounts, no balances, no merchants, no descriptions, at any point.

| ID | Requirement |
|---|---|
| FR-23 | User (grantor) creates a `ShareGrant` naming a registered user by email, with an expiry date **not exceeding 90 days**. Only the grantor may initiate; the system provides **no** mechanism to request access to another user's data. |
| FR-24 | Grantee views a read-only page showing green/amber/red status per category, computed at request time. Raw transaction rows are never serialised into a grantee response. |
| FR-25 | Grantor revokes any grant instantly, with no counterparty approval and no cache delay. Expired grants behave as revoked; no auto-renewal exists. |
| FR-26 | Every grantee read writes an access-log row visible to the grantor, showing who viewed what and when. |

### M7 — Administration (UC-11)

| ID | Requirement |
|---|---|
| FR-27 | Admin logs in through the standard form; the seeded `ADMIN` role unlocks `/admin`. No runtime path elevates a `USER` to `ADMIN`. |
| FR-28 | Admin searches users, locks/unlocks accounts, resets passwords and executes deletion requests. Listings show metadata only — email, status, registration date, last login. Never balances or transactions. |
| FR-29 | Admin views seeded import templates and classification rules and toggles each active/inactive. *Authoring* templates is done via the seed script, not through a UI. |
| FR-30 | Admin views an operations dashboard — active users, import success rate per bank, nightly job status, error count — and queries the audit log. Aggregate figures are suppressed below 5 users. |

> Numbering runs to FR-30 with four IDs consolidated during reduction; 26 requirements are in force.

---

## 4. Data Requirements

### 4.1 Entities (14 tables, down from 18)

`users` · `ledgers` · `accounts` · `categories` · `transactions` · `categorization_rules` · `import_templates` · `import_batches` · `import_errors` · `budgets` · `alerts` · `share_grants` · `share_access_logs` · `audit_logs`

Removed in v2: `ledger_members`, `friendships`, `recurring_groups`, `alert_configs`.

### 4.2 Non-negotiable data rules

| ID | Rule |
|---|---|
| DR-01 | All monetary columns are `BIGINT` VND. `FLOAT`/`REAL`/`DOUBLE PRECISION` are prohibited for money. |
| DR-02 | `transactions.dedup_key` carries a `UNIQUE` constraint **at the database level**, not only in service code. |
| DR-03 | MySQL has no `TIMESTAMP WITH TIME ZONE`. All instants are stored as `DATETIME(6)` holding **UTC**, converted to `Asia/Ho_Chi_Minh` in the application layer only. The `TIMESTAMP` type is prohibited: it applies implicit session-timezone conversion and overflows in 2038. |
| DR-04 | Foreign keys to `users` use `ON DELETE CASCADE`, so erasure is complete and verifiable. |
| DR-05 | Schema changes go through Alembic migrations only. `create_all()` is prohibited outside tests. |
| DR-06 | Indices required on `transactions(account_id, posted_at)`, `transactions(dedup_key)`, `alerts(user_id, triggered_at)`, `share_grants(grantee_id, valid_until)`. |

### 4.3 MySQL-specific constraints

MySQL differs from other SQL engines in ways that directly affect this design. The following are requirements, not recommendations.

| ID | Requirement | Consequence if ignored |
|---|---|---|
| MY-01 | Server version **8.0.16 or later**. Earlier versions parse `CHECK` constraints and then silently ignore them. | Every `CHECK` in the schema becomes decorative |
| MY-02 | Database, all tables and all string columns use `utf8mb4` with `utf8mb4_0900_ai_ci`. The legacy `utf8` alias (3-byte) is prohibited. | Emoji and some symbols in imported merchant strings raise `Incorrect string value` and abort the import |
| MY-03 | Connection URI must carry the charset explicitly: `mysql+pymysql://user:pass@host/db?charset=utf8mb4`. | The driver may negotiate `latin1` and Vietnamese diacritics are stored corrupted — silently, with no error |
| MY-04 | `dedup_key` is `BINARY(32)` storing the raw SHA-256 digest, not `VARCHAR(64)`. | A `utf8mb4 VARCHAR(64)` index key occupies 256 bytes instead of 32, on the hottest index in the import path |
| MY-05 | `sql_mode` must include `STRICT_TRANS_TABLES` and `ONLY_FULL_GROUP_BY` (both default in 8.0) and must not be relaxed. | Out-of-range and wrong-type values are silently coerced instead of rejected — unacceptable for monetary data |
| MY-06 | SQLAlchemy engine configured with `pool_pre_ping=True` and `pool_recycle=280`. | Idle Flask workers hit `MySQL server has gone away` after the server's `wait_timeout` |
| MY-07 | All tables use the InnoDB engine with foreign key checks enabled. MyISAM is prohibited. | `ON DELETE CASCADE` in DR-04 does nothing, so account deletion (NFR-10) leaves orphaned personal data |
| MY-08 | Enumerated values (`direction`, `nature`, `status`, `role`) are stored as `VARCHAR(20)` with a `CHECK` constraint, not as the native `ENUM` type. | Adding a value later requires an `ALTER TABLE` on the whole table |
| MY-09 | Money columns are **signed** `BIGINT`. `BIGINT UNSIGNED` is prohibited. | Any corrective or reversal entry wraps around instead of going negative |
| MY-10 | Integration tests run against MySQL in Docker. SQLite is permitted for pure unit tests of parsing and arithmetic only, never for anything touching collation, constraints or dates. | Tests pass locally and fail on the real database |
| MY-11 | Alembic migrations contain **one logical change each** and are rehearsed against a copy of the database. MySQL DDL is not transactional, so a failed migration cannot be rolled back automatically. | A half-applied migration leaves the schema in a state requiring manual repair |

**Note on collation.** `utf8mb4_0900_ai_ci` is accent- and case-insensitive, so `ca phe` matches `Cà Phê`. This is helpful for the merchant classification rules in FR-15, and it makes email uniqueness case-insensitive for free. It also means a `UNIQUE` constraint on category name treats `Ăn uống` and `an uong` as the same value — intended here, but the intern must know it is happening rather than discover it.

---

## 5. Non-Functional Requirements

Two tiers. **Verified** requirements must produce evidence in the final report. **Applied** requirements must be implemented correctly and are confirmed by code review only.

### 5.1 Verified — evidence required in the report

| ID | Requirement | Evidence |
|---|---|---|
| NFR-01 | Passwords hashed with `pbkdf2:sha256` (≥ 600,000 iterations) via `werkzeug.security`. Plaintext or reversible storage is a top-severity defect. | Screenshot of raw `users` table |
| NFR-02 | Session cookies set `HttpOnly`, `Secure`, `SameSite=Lax`; 30-minute idle timeout. Session ID regenerated on login. | Response header capture |
| NFR-03 | All database access goes through the SQLAlchemy ORM or bound parameters. String-concatenated or f-string SQL is prohibited. | `bandit` report + grep for `text(f"` |
| NFR-04 | CSRF protection via Flask-WTF on every non-GET endpoint. | Replay without token → `400` |
| NFR-05 | Object-level authorisation: user A requesting user B's `transaction_id` receives `404`. Sequential IDs must never confer access. | Automated test |
| NFR-06 | Upload safety: extension whitelist, `MAX_CONTENT_LENGTH` 5 MB, magic-byte check, `secure_filename()`, storage outside web root, deleted within 24 h. | Test with renamed executable |
| NFR-07 | Test coverage ≥ 60% overall and ≥ 85% for the import parser, dedup logic, budget calculator and alert detectors. | `pytest-cov` report |
| NFR-08 | 95th-percentile response under 800 ms for read pages, with 20,000 seeded transactions and 10 concurrent users. | `locust` or `ab` output |
| NFR-09 | Dashboard issues ≤ 10 SQL queries per render. N+1 patterns are defects. | Query-count assertion in test |
| NFR-10 | Account deletion purges all personal data. A post-deletion query across every table returns zero rows for that user. Only a salted email hash is retained for the deletion record. | SQL output before/after |
| NFR-11 | Re-importing an identical file produces zero new rows (idempotence). | Automated test |
| NFR-12 | **Administrative blindness.** No admin interface, endpoint or query exposes any identified user's transaction amounts, descriptions, merchants or balances. Enforced by the absence of such a code path. | Code review + attempted access, documented |

### 5.2 Applied — implemented and code-reviewed

**Security.** Password policy ≥ 10 characters with 3 of 4 character classes (NFR-13). `SECRET_KEY` and database URI from environment variables, never committed (NFR-14). Rate limiting via Flask-Limiter: 10/min on login and registration (NFR-15). Jinja2 autoescaping left on; `|safe` never applied to user input (NFR-16). Security headers via Flask-Talisman: CSP without `unsafe-inline`, `nosniff`, `X-Frame-Options: DENY` (NFR-17). Server-side schema validation on all input; client-side validation treated as convenience only (NFR-18). `DEBUG=False` outside local development (NFR-19). Dependencies pinned and audited with `pip-audit`; no High or Critical CVE at submission (NFR-20).

**Personal data protection.** Financial information and transaction history are sensitive personal data under the PDPL 2025 and Decree 356/2025/ND-CP, so the following are compliance-relevant rather than optional:

- **Data minimisation (NFR-21).** Collect only email, full name and self-entered financial records. Never collect national ID, full account or card numbers, bank credentials, OTPs, biometrics or precise location.
- **Withdrawal of consent (NFR-22).** One settings action revokes all outstanding grants and stops all sharing, immediately and without counterparty approval.
- **Purpose limitation (NFR-23).** No profiling, credit scoring, advertising, model training or third-party disclosure.
- **Log hygiene (NFR-24).** Logs never contain passwords, tokens, transaction amounts, descriptions or full email addresses; emails appear masked as `ab***@domain.com`.
- **Retention (NFR-25).** Audit logs 12 months, import error reports 30 days, uploaded source files 24 hours — enforced by a scheduled purge job, not manual action.
- **Single access gate (NFR-26).** All cross-user reads pass through one `ShareAccessGuard`. No blueprint queries another user's data directly.
- **No minors (NFR-27).** Registration rejects a declared date of birth indicating age below 18, since processing children's data requires safeguards outside this project's scope.

**Reliability and quality.** Import, transaction write and grant revocation are atomic (NFR-28). Derived balance equals `opening_balance + Σ(IN) − Σ(OUT)`, checked by a consistency script (NFR-29). Unhandled exceptions return a generic page and log a correlation ID; no stack trace reaches the browser (NFR-30). Strict layering `routes → services → repositories → models`; no business logic in routes (NFR-31). PEP 8 enforced by `ruff` in CI (NFR-32). Interface in Vietnamese, dates `dd/mm/yyyy`, VND grouping; colour never the sole carrier of meaning (NFR-33). `README.md` takes a clean machine to a running seeded instance in under 15 minutes (NFR-34).

---

## 6. Acceptance

### 6.1 Required experiments

Because the evaluation dataset is synthetic, ground truth is available. **Two** experiments are mandatory, reduced from three in v1.0.

**E1 — Alert quality and timeliness.** Inject ≥ 50 labelled overspending episodes across 24 months of synthetic data.

| Method | Precision | Recall | F1 | Mean lead time (days) |
|---|---|---|---|---|
| Static threshold at 80% (FR-18) | | | | |
| Linear pace `d/D` | | | | |
| Historical pace `w(d)` (FR-19) | | | | |

*Lead time* = days between the alert and month end. This is the primary result: a detector that identifies overspending accurately but only on the final day has little practical value, and this metric is what separates the three methods.

**E2 — Duplicate detection.** Precision and recall of `dedup_key` plus fuzzy matching (FR-13, FR-14) across four scenarios: identical re-import, overlapping date ranges, import after manual entry, and reordered rows.

### 6.2 Deliverables

1. Source repository with commit history and `README.md`.
2. Alembic migrations and a seed script: system categories, classification rules, import templates for ≥ 3 banks, one admin account.
3. Synthetic data generator producing 24 months of realistic activity — salary on day 5, rent on day 1, evenly distributed dining, month-end-skewed shopping.
4. Test suite meeting NFR-07.
5. Internship report containing the §6.1 results, the ERD, and the §7 exclusion rationale.

### 6.3 Schedule and effort budget

| Weeks | Module | Deliverable |
|---|---|---|
| 1 | Requirements analysis, scope agreement | This SRS, signed off |
| 2 | Schema, ERD, **synthetic data generator** | 24 months of seeded data |
| 3–4 | M1 + M2 — auth, accounts, transaction CRUD | Demo 1 |
| 5–7 | M3 — import engine, dedup, conflict resolution | Demo 2: three bank formats |
| 8–9 | M4 — budget, Safe-to-Spend, two detectors | Demo 3: alerts firing correctly |
| 10 | M5 — statistics | Demo 4 |
| 11 | M7 — administration | |
| 12 | M6 — sharing (**drop if behind**) | Demo 5 |
| 13 | Experiments E1, E2; testing; NFR evidence | Results tables |
| 14 | Report and slides | Draft |
| 15 | Buffer and rehearsal | Submission |

**Week 2 is the highest-risk item and is routinely deferred.** Without 24 months of realistic synthetic data, the charts are empty and the detectors have nothing to fire on — a problem usually discovered in week 13, when there is no time to fix it. The generator is a week-2 deliverable, not a week-13 one.

**Kill switch.** If M1–M5 are not complete by the end of week 11, drop M6 entirely and reallocate weeks 12–13 to hardening, testing and experiments. State this to the intern in week 1, so descoping is a planned outcome rather than a late failure.

---

## 7. Excluded Scope and Rationale

Recording *why* something was excluded is part of the specification. Each exclusion is a deliberate decision and must be defensible at the viva.

| Excluded | Rationale |
|---|---|
| **Direct bank API integration** | Circular 64/2024/TT-NHNN structures Open API access around a contract between the bank and the third party. A student project cannot obtain one. The system therefore defines a `TransactionSource` interface with a `FileImportAdapter` implementation, so a banking adapter can later be added without touching the domain layer. |
| **Third-party aggregators (SePay, Casso)** | Built for business payment reconciliation; require a corporate account and charge fees. |
| **SMS / notification reading** | `READ_SMS` is effectively unavailable under current Google Play policy, and notification-derived data lacks reference numbers and balances, making reliable deduplication impossible. |
| **Friend-request workflow** | Removed in v2. A `ShareGrant` already encodes the relationship, so a separate friendship entity with its own request/accept/decline state machine is redundant — roughly a week of work for no added capability. |
| **Household / shared ledgers** | Removed in v2. Multi-member ledgers force a tenancy check into every query and every test, roughly doubling the authorisation surface. Disproportionate at this scope. |
| **Transaction-level sharing (L3/L4)** | Merchant names and descriptions reveal location, health and lifestyle information. `L1` answers the actual question — "is this person overspending?" — without that exposure. |
| **Balance sharing** | Never disclosed. It answers no budgeting question and carries the highest disclosure risk. |
| **Access-request mechanism** | Deliberately absent (FR-23). If a request feature existed, refusing it would carry a social cost, letting a stronger party pressure a weaker one into consent. Grants are grantor-initiated only. |
| **Minors' accounts and parental control** | The PDPL 2025 imposes stricter conditions on processing children's data, including verified guardian consent. Disproportionate for a 15-week project. Sharing is therefore voluntary, revocable consent between adults. |
| **Recurring-payment detection** | Removed in v2. Attractive but not load-bearing: the alert claim is already demonstrated by E1. |
| **Visual import-template editor** | Removed in v2. Templates remain data rather than code — the architectural point stands — but authoring happens through the seed script. Building a mapping UI costs a week and demonstrates nothing new. |
| **Soft delete, import rollback, CSV export of charts** | Convenience features; removed to protect the core. |
| **Multi-currency, investments, debt tracking, mobile app, microservices** | Beyond the timebox. |

---

*Prepared by MSc. Huỳnh Vinh Nam — ICTLab, USTH*
