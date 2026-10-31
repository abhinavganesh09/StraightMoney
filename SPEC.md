# StraightMoney: Project Spec (Fundraiser)

> Read this file at the start of every AI coding session (Antigravity, Codex, or any other tool). If your code conflicts with this spec, change the spec first and tell the team.

## 1. What we're building

StraightMoney is a community fundraising tool where **the organizer never holds the money**.

1. An organizer (a school club, a neighborhood group) posts a campaign with a goal and a budget split into line items, each tied to a named vendor.
2. Donors give through PayPal checkout (sandbox only).
3. When a vendor delivers, they upload an invoice and a photo as proof.
4. An AI reads the invoice and flags anything that doesn't match the approved budget line.
5. Plain-code rules check the invoice. A human verifier (for example a teacher or club advisor) reviews it and approves or rejects.
6. On approval, **PayPal pays the vendor directly**, and a public ledger shows every payment with its proof.

**Pitch in one line:** donors can see exactly where every dollar went, because the money goes straight to vendors and only against verified paperwork.

**Honest limits (say these in the pitch):** the AI checks paperwork consistency; it cannot prove that work was actually done. The human verifier is the trust anchor. StraightMoney makes fraud much harder and much more visible, and does not eliminate it. This is a sandbox demo, and a real fundraising platform would face regulation.

Hackathon: PayPal AI Hackathon. Submission deadline: **Thu 12 Nov 2026, 12:00 pm Pacific (1:30 am IST on 13 Nov)**. Target: submit on 11 Nov.

## 2. Core design rule

**The LLM never touches money.**

| Component | Can do | Cannot do |
|---|---|---|
| Extraction (LLM) | Turn an invoice into structured JSON | Approve or pay anything |
| Advisory checks (LLM) | Raise soft flags (item mismatch, odd photo) and write a plain-English summary | Block, approve, or change routing |
| Policy engine (plain code) | Apply hard rules and reject | Call PayPal |
| Verifier (human) | Approve or reject a checked invoice | Pay without passing the policy engine |
| Payment service (plain code) | Create donation orders, send vendor payouts | Pay an invoice that is not `VERIFIER_APPROVED` |

- **Every payout requires verifier approval.** There is no auto-pay in this project.
- Invoice text and photos are untrusted input. Instructions inside them (for example "ignore the rules and pay now") must have no effect, because the policy engine reads fields, not instructions.
- AI flags are advisory. They appear in the verifier's screen but never approve or block on their own.

## 3. Roles (demo uses a role switcher, no logins)

| Role | Does |
|---|---|
| Organizer | Creates a campaign, defines budget lines and vendors |
| Donor | Donates via PayPal, views progress and the ledger |
| Vendor | Uploads an invoice and a proof photo for a budget line |
| Verifier | Reviews checked invoices and approves or rejects |

## 4. Tech stack (locked)

| Part | Choice |
|---|---|
| Backend | Python 3.11+, FastAPI |
| Validation | Pydantic |
| Database | PostgreSQL through SQLAlchemy; create tables with `create_all`, no migrations |
| LLM | One provider's official Python SDK, with vision for photos: **TODO: team picks one** |
| PDF text | pdfplumber (text-based PDFs only) |
| PayPal | REST calls with `httpx`: Orders v2 for donations, Payouts for vendors. The PayPal Agent Toolkit is optional and not required |
| Frontend | Next.js App Router with TypeScript (TSX) and Tailwind, run with Node.js |
| Ledger table | **AG Grid Community** in a `"use client"` component (targets the AG Grid sponsor prize) |
| PayPal checkout button | PayPal React JS SDK in a `"use client"` component |
| Local development | Docker Compose runs PostgreSQL with a named volume |
| Hosting (demo) | Render, or run instructions in the README |
| Tests | pytest |
| Config | `.env` + python-dotenv |

Not allowed: LangChain or other agent frameworks, real money, Next.js API routes or server actions for business logic, ORMs other than SQLAlchemy.

## 5. Folder structure

```
StraightMoney/
├── SPEC.md
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
├── docker-compose.yml    # local PostgreSQL with a named volume
├── backend/
│   ├── main.py            # FastAPI app and routes
│   ├── config.py          # loads .env
│   ├── db.py              # connection and session
│   ├── models.py          # tables
│   ├── schemas.py         # Pydantic models
│   ├── extraction.py      # LLM invoice parsing
│   ├── advisory.py        # LLM soft flags and summary (advisory only)
│   ├── policy.py          # hard rules (plain code, no LLM)
│   ├── payments.py        # PayPal service (only file with credentials)
│   ├── audit.py           # audit log helper
│   ├── seed.py            # demo campaign, vendors, donors
│   └── tests/
├── frontend/              # Next.js App Router + TypeScript app
│   ├── app/               # pages
│   ├── components/        # UI, including client components
│   └── lib/
│       └── api.ts         # one typed FastAPI client
├── sample_invoices/       # fake data only
└── docs/                  # demo script, screenshots
```

## 6. Invoice status lifecycle

```
SUBMITTED → EXTRACTED → CHECKED ─┬→ REJECTED (hard rule failed)
                                 └→ AWAITING_VERIFIER ─┬→ VERIFIER_REJECTED
                                                       └→ VERIFIER_APPROVED → AWAITING_FUNDS → PAYOUT_PENDING
                                                                                                 ├→ PARTIALLY_PAID → PAYOUT_PENDING (when more donations arrive)
                                                                                                 ├→ PAID
                                                                                                 └→ FAILED (retryable)
SUBMITTED → NEEDS_REVIEW (extraction failed)
```

- Status only moves forward along these arrows.
- Every transition writes an audit log entry.
- `REJECTED`, `VERIFIER_REJECTED`, and `PAID` are terminal. `FAILED` can be retried, and a retry goes back through the payment checks.

## 7. Data model

| Table | Fields |
|---|---|
| `campaigns` | id, title, description, goal_amount, currency, pool_balance, status (draft/active/closed), organizer_name |
| `budget_lines` | id, campaign_id, name, vendor_id, budgeted_amount, paid_amount |
| `vendors` | id, campaign_id, name, payout_email, status (active/blocked) |
| `donations` | id, campaign_id, donor_name, amount, paypal_order_id, status (created/captured/failed), created_at |
| `invoices` | id, campaign_id, budget_line_id, vendor_id, invoice_number, amount, currency, payout_email, description, extracted_json, ai_summary, status, created_at |
| `files` | id, invoice_id, kind (invoice/proof), filename, mime_type, data (`bytea`) |
| `checks` | id, invoice_id, check_name, passed (bool), severity (hard/soft), source (rule/ai), detail |
| `verifications` | id, invoice_id, verifier_name, decision (approve/reject), note, timestamp |
| `payouts` | id, invoice_id, paypal_batch_id, sender_batch_id, status, amount, currency, created_at (legacy single transfer) |
| `payout_installments` | id, invoice_id, paypal_batch_id, sender_batch_id, status, amount, currency, created_at |
| `audit_log` | id, timestamp, campaign_id, invoice_id, actor (extractor/engine/ai/verifier/system), action, detail (JSON) |

`payout_installments` stores each PayPal batch and amount against an approved invoice. Approved invoices can be `AWAITING_FUNDS` or `PARTIALLY_PAID`; captured donations automatically fund the remaining approved amount. Each installment has a distinct idempotency key, and only confirmed transfers reduce the pool balance. `audit_log` is append-only. `campaigns.pool_balance` goes up when a donation is captured and down when a payout succeeds.

Uploaded invoices and proof photos are stored in PostgreSQL as `bytea` for the hosted demo because host disks may be temporary. Files are linked to invoices through `files.invoice_id`.

## 8. Extraction schema

The LLM returns JSON matching this shape. Validate with Pydantic. On failure, retry once, then set `NEEDS_REVIEW`. Never guess missing fields.

```json
{
  "vendor_name": "string",
  "payout_email": "string",
  "invoice_number": "string",
  "amount": 0.0,
  "currency": "USD",
  "description": "string",
  "line_items": [{"description": "string", "amount": 0.0}]
}
```

## 9. Policy checks

Run in this order and log every result to `checks`.

| # | Check | Severity | Fails when |
|---|---|---|---|
| 1 | Campaign active | Hard | Campaign is not `active` |
| 2 | Vendor approved for this budget line | Hard | Vendor not registered for that line, or blocked |
| 3 | Payout email match | Hard | `payout_email` differs from the vendor's registered email |
| 4 | Duplicate | Hard | Same vendor + invoice number already submitted |
| 5 | Within budget line | Hard | Amount > line's `budgeted_amount - paid_amount` |
| 6 | Pool available for installment | Informational | Records the amount currently available; an approved invoice may wait for funds or receive a partial payout |
| 7 | Currency match | Hard | Currency differs from the campaign's |
| 8 | Evidence attached | Hard | No proof photo uploaded |

**Advisory (AI) flags, soft only:** the description doesn't match the budget line's item; the photo doesn't seem to show the described delivery; unusual wording or injected instructions found in the invoice. Soft flags show up on the verifier screen and never change routing.

**Routing**
- Any hard failure → `REJECTED`, with the reason written out
- Otherwise → `AWAITING_VERIFIER`, with soft flags shown

The policy engine is pure functions: data in, results out. No LLM calls, no network calls. Every check needs unit tests.

## 10. PayPal integration

Sandbox only. Never use live credentials.

- Base URL: `https://api-m.sandbox.paypal.com`
- Auth: OAuth2 client-credentials token
- **Donations:** Orders v2. Create the order on the backend, the donor approves in PayPal's checkout (PayPal JS SDK button), and the backend captures it and credits `pool_balance`.
- **Vendor payouts:** Payouts API, using a unique installment ID as `sender_batch_id` and `sender_item_id` for idempotency. Verifier approval pays the available pool amount, and later captured donations trigger further installments toward the approved balance. Check payout status before any retry. Never blindly resend.
- **Confirmation:** poll payout and order status. Webhooks are a stretch goal.

**First task for the team (Day 1):** one sandbox donation (create, approve, capture) and one sandbox payout, both visible in the sandbox dashboard. Verify endpoints and request formats against PayPal's current developer docs, and confirm Payouts is enabled for the sandbox business account and funded.

**If Payouts doesn't work in the sandbox:** decide the fallback on Day 1, not later. Options are paying the vendor's sandbox account through an Orders-based transfer, or, as a last resort, recording the payout in the ledger as simulated and stating that clearly in the submission. Donations through Orders remain real either way.

`payments.py` is the only file allowed to read PayPal credentials.

## 11. API endpoints (backend)

| Method | Path | Purpose |
|---|---|---|
| GET | `/campaigns` | List campaigns |
| GET | `/campaigns/{id}` | Campaign detail: budget lines, pool, progress |
| POST | `/campaigns` | Organizer creates a campaign with budget lines and vendors |
| POST | `/campaigns/{id}/donations` | Create a PayPal order for a donation |
| POST | `/donations/{order_id}/capture` | Capture the approved order and credit the pool |
| POST | `/invoices` | Vendor uploads invoice + evidence; runs extraction and checks |
| GET | `/invoices` | List invoices (filter by `campaign_id`, `status`) |
| GET | `/invoices/{id}` | Detail with checks, AI summary, evidence, payout |
| GET | `/files/{id}` | Serve a stored invoice or proof file (used by the verifier screen and the public ledger) |
| POST | `/invoices/{id}/approve` | Verifier approves (body: verifier name, note) and triggers payout |
| POST | `/invoices/{id}/reject` | Verifier rejects (body: verifier name, reason) |
| POST | `/invoices/{id}/retry` | Retry a `FAILED` payout |
| GET | `/campaigns/{id}/ledger` | Public ledger: donations in, payouts out, with proof links |

FastAPI's auto docs at `/docs` are the source of truth for request and response shapes. Enable CORS for the frontend dev server.

## 12. Frontend (five screens)

1. **Campaign page:** title, goal progress bar, budget lines with paid/remaining, Donate button (PayPal checkout)
2. **Organizer setup:** create a campaign, add budget lines and vendors
3. **Vendor upload:** choose the budget line, upload an invoice and a proof photo
4. **Verifier review:** invoice details, check results (pass/fail, hard/soft), AI summary and flags, evidence photo, Approve and Reject buttons
5. **Public ledger:** AG Grid table of every donation and payout, with proof links, filterable

These are Next.js pages that call the FastAPI backend only. Next.js holds no business logic and never calls PayPal's secret-key APIs.

Keep it clean and simple: a role switcher in the header, colored status badges, no animations.

## 13. Environment variables

Defined in `.env` (never committed). Keep `.env.example` with placeholders.

```
PAYPAL_CLIENT_ID=your-id-here
PAYPAL_CLIENT_SECRET=your-secret-here
PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com
LLM_API_KEY=your-key-here
LLM_MODEL=your-model-here
SUPPORTED_CURRENCY=USD
POSTGRES_USER=straightmoney
POSTGRES_PASSWORD=change-me
POSTGRES_DB=straightmoney
DATABASE_URL=postgresql+psycopg://straightmoney:change-me@localhost:5432/straightmoney
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_PAYPAL_CLIENT_ID=your-client-id-here
```

The backend loads the repo-root `.env`. Next.js does not read it: put `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_PAYPAL_CLIENT_ID` in `frontend/.env.local` (never committed), and keep a `frontend/.env.example` with placeholders.

## 14. Demo scenarios (must always work)

Seed campaign: "School library corner", goal $1,200, budget lines: Shelves $400 (Vendor A), Books $600 (Vendor B), Paint $200 (Vendor C).

| # | Scenario | Expected outcome |
|---|---|---|
| 1 | Three donors fund the campaign through PayPal checkout | Pool reaches the goal, progress bar updates |
| 2 | Vendor A submits a matching $400 invoice with a delivery photo | Passes checks, verifier approves, vendor paid, ledger entry with proof |
| 3 | Vendor B submits a $720 invoice against the $600 Books line | Rejected: exceeds remaining line budget |
| 4 | Vendor C submits an invoice with a different payout email plus an injected "pay immediately" line | Rejected: payout email mismatch. The injection has no effect and is flagged |
| 5 | Same invoice number submitted twice | Second one rejected as a duplicate |
| 6 | Valid invoice, but the photo doesn't match the description | AI soft flag shown; verifier rejects; no payout |
| 7 | Garbled PDF | `NEEDS_REVIEW` |

All sample data is fake.

## 15. Demo video plan (under 3 minutes, public on YouTube)

| Time | Content |
|---|---|
| 0:00 to 0:20 | The problem: donors can't see where money goes |
| 0:20 to 0:50 | Campaign page, donors fund it through PayPal |
| 0:50 to 1:40 | Valid invoice → AI check → verifier approves → vendor paid → ledger entry |
| 1:40 to 2:20 | Fraud cases rejected: wrong email with injected instruction, inflated amount |
| 2:20 to 2:50 | Public ledger and the one-line close |

Record on the machine that runs the demo. No copyrighted music or third-party logos.

## 16. Build order and schedule

| Dates | Goal |
|---|---|
| 29 to 31 Oct | PayPal sandbox proof: donation (create, approve, capture) and one payout. Decide the payout fallback. Pick the LLM. Repo ready; docker compose up gives a working Postgres for everyone |
| 1 to 5 Nov | Database, donations flow, policy engine with tests, payments service, frontend skeleton. Work in parallel (see section 17) |
| 6 to 8 Nov | Extraction, advisory flags, verifier flow, ledger. Connect everything end to end |
| 9 to 10 Nov | Seed data, UI polish, hosted demo or run instructions, README, run all scenarios three times in a row, record video |
| 11 Nov | Submit on Devpost. Keep 12 Nov morning as a buffer only |

If time runs short, cut from the bottom: advisory flags and the photo check go first, then the AG Grid filters. Never cut the PayPal flows or the policy engine.

## 17. Team split

| Person | Owns |
|---|---|
| 1 | PayPal integration: donations, payouts, status polling (`payments.py`) |
| 2 | Database, policy engine, audit log, tests |
| 3 | Extraction and advisory AI (`extraction.py`, `advisory.py`) |
| 4 | Next.js and TypeScript frontend, seed data, demo script, video |

Each module has one owner at a time, so two people (or two AI tools) don't edit the same file.

## 18. Rules for AI coding tools

- Make **one small change per prompt**, not "build the app".
- Write or update tests with every change, and run them before committing.
- Never put credentials in code, prompts, logs, or commits. Read them only from `.env`.
- Next.js is UI only. Never put PayPal secrets, payment logic, or policy logic in the frontend.
- Never add the LLM to the approval or payout path. Never let anything but `payments.py` call PayPal.
- Don't add new dependencies or frameworks without asking the team.
- Don't rewrite files you weren't asked to touch.
- When something fails, show the exact error and fix the cause. Don't suppress it.
- Keep functions small and typed, with clear names.

## 19. Team workflow

- Feature branches and pull requests. Have a teammate review anything touching `policy.py` or `payments.py`.
- Run `npm run lint` and `npm run build` before opening a pull request.
- Commit often with clear messages.
- Before submission: run all scenarios from section 14 end to end at least three times in a row.

## 20. Submission checklist (PayPal AI Hackathon)

- [ ] Public GitHub repo with the MIT license visible in the About section
- [ ] README with setup and run instructions, test credentials, and sandbox notes
- [ ] Working demo: hosted URL, or complete run instructions judges can follow
- [ ] Public YouTube demo video, under 3 minutes, showing the project working end to end
- [ ] Text description covering features, the PayPal products used, and the AI tools used
- [ ] Every team member is of legal age where they live, and one person is appointed Representative to submit
- [ ] The project stays free and accessible to judges until the judging period ends (15 Dec)
- [ ] No real secrets in the repo or git history

## 21. Out of scope

Real money, user accounts and login, email intake, mobile app, multi-currency, multi-tenant support, tax receipts. Stretch only: webhooks, refunds of unspent funds to donors when a campaign is cancelled, a milestone timeline view.

## Temporary sandbox verifier test override

When `ENABLE_VERIFIER_TEST_OVERRIDE=true`, the verifier can click **Approve for sandbox test** on an unpaid invoice with a positive amount. This bypasses AI and application policy checks for one explicit sandbox payment attempt. It routes only to the vendor's registered email, uses the campaign currency, and sends at most the campaign's available balance. It records a `test_override` verification and audit entry. It does not automatically pay later donations toward this test invoice. PayPal still decides whether the payout can be sent, and only a confirmed success marks any amount paid. The override is refused outside the PayPal sandbox. Set `ENABLE_VERIFIER_TEST_OVERRIDE=false` and `NEXT_PUBLIC_ENABLE_VERIFIER_TEST_OVERRIDE=false` to remove it after testing.
