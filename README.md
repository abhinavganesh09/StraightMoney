# StraightMoney

**A PayPal Sandbox prototype for transparent community fundraising.** Donors fund a campaign, vendors submit invoices and delivery evidence, and a verifier approves eligible payouts to the vendor's registered PayPal account. The organizer does not receive a payout through the app. Built for the PayPal AI Hackathon; no live payments are supported.

## Current state

The repository contains a FastAPI backend and Next.js frontend, backed by PostgreSQL. On first startup, the API creates its tables and seeds a **School Library Corner** campaign with a $1,200 goal and three budget lines: shelves ($400), books ($600), and paint ($200). The UI includes campaign and donation, organizer, vendor submission, verifier, and public ledger pages.

| Step | Implementation |
| --- | --- |
| Donate | PayPal Orders v2 checkout and capture, or a simulated donation for local demos |
| Submit | Vendor uploads a PDF or image invoice and optional proof photo |
| Extract and review | Gemini extracts invoice fields and provides advisory flags; eight Python policy checks decide whether the invoice can reach the verifier |
| Approve and pay | A verifier approves or rejects; approved invoices use PayPal Payouts in tracked installments as captured funds become available |
| Inspect | The public ledger shows donation records and confirmed payouts, with links to uploaded evidence where available |

The eight policy checks cover campaign status, assigned vendor, registered payout email, duplicate invoice number, remaining budget, available funds, currency, and attached proof. The funds check reports how much is available for the first installment; a short balance does not prevent approval. Advisory AI output cannot independently approve a payout.

**Sandbox test override:** The verifier UI has an explicit test action that can approve an invoice despite failed policy checks. It is enabled by default in the example configuration and only works with the PayPal Sandbox base URL. It records an audit event and routes to the vendor's registered email. Set `ENABLE_VERIFIER_TEST_OVERRIDE=false` and `NEXT_PUBLIC_ENABLE_VERIFIER_TEST_OVERRIDE=false` to hide and reject it when testing the normal policy flow.

## Run locally

Prerequisites: Python 3.11+, Node.js and npm, and Docker Compose. A Gemini API key enables AI invoice extraction and advisory checks; without one, the backend uses a simple heuristic fallback for demos. PayPal Sandbox credentials are needed to exercise actual Sandbox checkout and payout calls; the app also has simulation paths for local demonstrations.

1. From the repository root, copy the environment examples and edit the copies:

   ```powershell
   Copy-Item .env.example .env
   Copy-Item frontend/.env.example frontend/.env.local
   ```

   Set a PostgreSQL password in `.env` and use the same value in `DATABASE_URL`. For PayPal Sandbox, set `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, and the matching public `NEXT_PUBLIC_PAYPAL_CLIENT_ID` in `frontend/.env.local`. Set `LLM_API_KEY` to your Gemini key and choose an available `LLM_MODEL`. Keep `PAYPAL_BASE_URL` on the Sandbox URL. The frontend API URL defaults to `http://localhost:8000`.

2. Start PostgreSQL from the repository root:

   ```powershell
   docker compose up -d
   ```

3. Start the API from `backend`:

   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   uvicorn main:app --reload --port 8000
   ```

   The API is at <http://localhost:8000>, its health endpoint at <http://localhost:8000/health>, and interactive docs at <http://localhost:8000/docs>. Start it from `backend` so the default upload directory resolves there.

4. In a second terminal, start the UI:

   ```powershell
   cd frontend
   npm ci
   npm run dev
   ```

   Open <http://localhost:3000>. Set `NEXT_PUBLIC_USE_MOCKS=true` in `frontend/.env.local` for a frontend-only preview; that mode does not persist actions. With mocks off, the UI uses the FastAPI backend.

## Demo flow

1. Open the seeded campaign and capture a Sandbox donation, or use **Simulate donation without PayPal deduction** for a local demo.
2. Open `/vendor`, select the campaign and budget line, and upload an invoice plus a proof photo. For meaningful AI extraction, configure Gemini. Extraction errors leave the invoice needing review.
3. Open `/verifier` to inspect extracted fields, policy checks, advisory flags, and evidence. Approve a passing invoice or reject it.
4. Check `/ledger/1` for captured donations and successful payouts. If the campaign has less than the approved invoice amount, later captured donations can trigger the remaining installment.

Payouts are only counted as paid after PayPal confirms success. A simulated payout is recorded as failed and does **not** reduce the campaign balance or claim that the vendor received money. If a Sandbox sender gets `403 PAYOUT_NOT_AVAILABLE`, use a Payouts-enabled Sandbox Business account from a supported sending country, restart the API with that account's credentials, and use **Retry payout** on the invoice. A failed transfer does not reduce the balance.

## Verification

From `backend`, run the automated tests with the installed environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

From `frontend`, run:

```powershell
npm run lint
npm run build
```

The optional live Sandbox CLI scripts require real Sandbox credentials and an interactive buyer approval or eligible payout recipient. Run them from the repository root using the backend virtual environment:

```powershell
.\backend\.venv\Scripts\python.exe backend/scripts/donate_test.py
.\backend\.venv\Scripts\python.exe backend/scripts/payout_test.py vendor@example.com
```

## Repository notes

- Backend: `backend/main.py` exposes the API; `policy.py` contains deterministic checks; `installments.py` manages payout state; `payments.py` calls PayPal; `extraction.py` and `advisory.py` call Gemini.
- Frontend: `frontend/app` contains the routes; `frontend/lib/api.ts` is the typed API client.
- `docker-compose.yml` starts PostgreSQL. Tables are created with SQLAlchemy `create_all`; there is no migration system yet.
- [`SPEC.md`](SPEC.md) describes the intended product. [`docs/`](docs/) and [`sample_invoices/`](sample_invoices/) currently contain placeholders rather than a finished demo script, screenshots, or sample files.
- This is a hackathon prototype. The API has no user authentication or role enforcement, and uploaded invoice and proof files are served publicly from `/uploads`. Use synthetic demo data and Sandbox credentials only.

## License

MIT. See [`LICENSE`](LICENSE).
