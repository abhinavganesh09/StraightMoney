import type { CampaignStatus, InvoiceStatus } from "@/lib/types";

const colors: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  AWAITING_VERIFIER: "bg-amber-50 text-amber-800 ring-amber-200",
  PAID: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  REJECTED: "bg-rose-50 text-rose-800 ring-rose-200",
  VERIFIER_REJECTED: "bg-rose-50 text-rose-800 ring-rose-200",
  NEEDS_REVIEW: "bg-amber-50 text-amber-800 ring-amber-200",
};
export default function StatusBadge({ status }: { status: CampaignStatus | InvoiceStatus | string }) {
  return <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ring-1 ${colors[status] ?? "bg-slate-100 text-slate-700 ring-slate-200"}`}>{status.replaceAll("_", " ").toLowerCase()}</span>;
}
