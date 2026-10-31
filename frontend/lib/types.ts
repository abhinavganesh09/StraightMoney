export type CampaignStatus = "draft" | "active" | "closed";
export type InvoiceStatus = "SUBMITTED" | "EXTRACTED" | "CHECKED" | "AWAITING_VERIFIER" | "REJECTED" | "NEEDS_REVIEW" | "VERIFIER_REJECTED" | "VERIFIER_APPROVED" | "PAYOUT_PENDING" | "AWAITING_FUNDS" | "PARTIALLY_PAID" | "PAID" | "FAILED";
export type CheckSeverity = "hard" | "soft";

export interface Vendor { id: number; campaign_id: number; name: string; payout_email: string; status: "active" | "blocked"; created_at: string }
export interface BudgetLine { id: number; campaign_id: number; name: string; vendor_id: number | null; vendor_name: string | null; budgeted_amount: number; paid_amount: number; created_at: string }
export interface CampaignSummary { id: number; title: string; description: string | null; goal_amount: number; currency: string; pool_balance: number; status: CampaignStatus; organizer_name: string; created_at: string }
export interface Campaign extends CampaignSummary { vendors: Vendor[]; budget_lines: BudgetLine[] }
export interface CampaignCreate { title: string; description: string; goal_amount: number; currency: string; organizer_name: string; vendors: Array<Pick<Vendor, "name" | "payout_email">>; budget_lines: Array<{ name: string; budgeted_amount: number; vendor_name: string; vendor_payout_email: string }> }
export interface Donation { id: number; campaign_id: number; donor_name: string; amount: number; currency: string; paypal_order_id: string; status: "created" | "captured" | "failed"; created_at: string }
export interface CheckResult { id: number; invoice_id: number; check_name: string; passed: boolean; severity: CheckSeverity; source: "rule" | "ai"; detail: string; created_at: string }
export interface Verification { id: number; invoice_id: number; verifier_name: string; decision: "approve" | "reject" | "test_override"; note: string | null; timestamp: string }
export interface Payout { id: number; invoice_id: number; paypal_batch_id: string | null; sender_batch_id: string | null; status: string; amount: number; currency: string; created_at: string }
export interface Invoice { id: number; campaign_id: number; budget_line_id: number; vendor_id: number; invoice_number: string; amount: number; currency: string; payout_email: string; description: string | null; evidence_path: string | null; raw_file_path: string | null; status: InvoiceStatus; ai_summary: string | null; paid_amount: number; remaining_amount: number; installments: Payout[]; vendor_name: string | null; budget_line_name: string | null; created_at: string; checks: CheckResult[]; verifications: Verification[]; payout: Payout | null }
export interface LedgerEntry { type: "donation" | "payout"; amount: number; actor_name: string; status: string; created_at: string; proof_url: string | null }
export interface VerificationRequest { verifier_name: string; note?: string; override_for_testing?: boolean }
