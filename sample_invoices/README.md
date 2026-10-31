# StraightMoney — Sample Invoices

This directory holds **fake sample invoices** for demo and testing purposes only.
No real vendor or financial data is stored here.

## Files (to be added)

- `vendor_a_shelves_valid.pdf` — Valid $400 invoice for shelves (passes all checks)
- `vendor_b_books_inflated.pdf` — $720 invoice against $600 line (over budget)
- `vendor_c_paint_wrong_email.pdf` — Invoice with wrong payout email + injected instruction
- `vendor_a_shelves_duplicate.pdf` — Same invoice number as vendor_a_shelves_valid (duplicate)
- `vendor_b_books_garbled.pdf` — Garbled/corrupt PDF (triggers NEEDS_REVIEW)
- `proof_shelves.jpg` — Photo of shelves delivery (matches description)
- `proof_mismatch.jpg` — Photo that doesn't match the invoice description
