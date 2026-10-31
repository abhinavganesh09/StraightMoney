import type { Campaign, Donation, Invoice, LedgerEntry } from "./types";

const created = "2026-10-29T10:00:00Z";

export const mockCampaign: Campaign = {
  id: 1,
  title: "School Library Corner",
  description: "Help create an inviting reading corner with shelves, books, and a fresh coat of paint.",
  goal_amount: 1200,
  currency: "USD",
  pool_balance: 1200,
  status: "active",
  organizer_name: "Demo Organizer",
  created_at: created,
  vendors: [
    { id: 1, campaign_id: 1, name: "Vendor A", payout_email: "vendor-a@example.com", status: "active", created_at: created },
    { id: 2, campaign_id: 1, name: "Vendor B", payout_email: "vendor-b@example.com", status: "active", created_at: created },
    { id: 3, campaign_id: 1, name: "Vendor C", payout_email: "vendor-c@example.com", status: "active", created_at: created },
  ],
  budget_lines: [
    { id: 1, campaign_id: 1, name: "Shelves", vendor_id: 1, vendor_name: "Vendor A", budgeted_amount: 400, paid_amount: 0, created_at: created },
    { id: 2, campaign_id: 1, name: "Books", vendor_id: 2, vendor_name: "Vendor B", budgeted_amount: 600, paid_amount: 0, created_at: created },
    { id: 3, campaign_id: 1, name: "Paint", vendor_id: 3, vendor_name: "Vendor C", budgeted_amount: 200, paid_amount: 0, created_at: created },
  ],
};

export const mockDonations: Donation[] = [
  { id: 1, campaign_id: 1, donor_name: "Alice Johnson", amount: 500, currency: "USD", paypal_order_id: "DEMO-ORDER-001", status: "captured", created_at: "2026-10-29T11:00:00Z" },
  { id: 2, campaign_id: 1, donor_name: "Bob Smith", amount: 400, currency: "USD", paypal_order_id: "DEMO-ORDER-002", status: "captured", created_at: "2026-10-29T12:00:00Z" },
  { id: 3, campaign_id: 1, donor_name: "Carol Davis", amount: 300, currency: "USD", paypal_order_id: "DEMO-ORDER-003", status: "captured", created_at: "2026-10-29T13:00:00Z" },
];

export const mockInvoices: Invoice[] = [
  {
    id: 1, campaign_id: 1, budget_line_id: 1, vendor_id: 1, invoice_number: "SHELVES-001",
    amount: 400, currency: "USD", payout_email: "vendor-a@example.com",
    description: "Four sturdy library shelves delivered and assembled.", status: "AWAITING_VERIFIER",
    ai_summary: "The invoice details match the Shelves budget line. The attached delivery photo appears relevant. Human review is still required.",
    vendor_name: "Vendor A", budget_line_name: "Shelves", created_at: "2026-10-30T09:15:00Z",
    checks: [
      ["campaign_active", true, "hard", "Campaign is active."],
      ["vendor_approved", true, "hard", "Vendor A is assigned to Shelves."],
      ["payout_email_match", true, "hard", "Payout email matches the vendor record."],
      ["no_duplicate", true, "hard", "No earlier invoice uses this number for Vendor A."],
      ["within_budget_line", true, "hard", "The $400 invoice fits the $400 remaining line budget."],
      ["pool_has_funds", true, "hard", "The campaign pool covers the invoice."],
      ["currency_match", true, "hard", "Invoice and campaign both use USD."],
      ["evidence_attached", true, "hard", "A proof photo is attached."],
      ["photo_relevance", true, "soft", "The photo appears to show shelving."],
    ].map(([check_name, passed, severity, detail], index) => ({
      id: index + 1, invoice_id: 1, check_name: String(check_name), passed: Boolean(passed),
      severity: severity as "hard" | "soft", source: severity === "soft" ? "ai" as const : "rule" as const,
      detail: String(detail), created_at: "2026-10-30T09:15:00Z",
    })),
    verifications: [], payout: null, installments: [], paid_amount: 0, remaining_amount: 400,
    raw_file_path: "uploads/shelves-invoice.pdf",
    evidence_path: "uploads/shelves-delivery.jpg",
  },
];

export const mockLedger: LedgerEntry[] = mockDonations.map((donation) => ({
  type: "donation", amount: donation.amount, actor_name: donation.donor_name,
  status: donation.status, created_at: donation.created_at, proof_url: null,
}));
