"use client";
/* eslint-disable @next/next/no-img-element -- The API serves user-uploaded evidence at runtime. */

import { useState } from "react";
import { api, USE_MOCKS } from "@/lib/api";
import type { Invoice } from "@/lib/types";
import StatusBadge from "./StatusBadge";

const TEST_OVERRIDE_ENABLED = process.env.NEXT_PUBLIC_ENABLE_VERIFIER_TEST_OVERRIDE !== "false";

export default function VerifierReview({ invoice, onChanged }: { invoice: Invoice; onChanged: () => void }) {
  const [verifierName, setVerifierName] = useState("");
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const payoutCountryRestricted = /PAYOUT_NOT_AVAILABLE|country that is not allowed to send this payout|sandbox sender account.s country/i.test(invoice.ai_summary ?? "");
  const advisorySummary = (invoice.ai_summary ?? "").split("\nPayout was simulated")[0].split("\nPayout failed:")[0].split("\nPayPal Payouts are unavailable")[0];
  const evidenceUrl = api.assetUrl(invoice.evidence_path);
  const invoiceUrl = api.assetUrl(invoice.raw_file_path);
  const isImage = (path: string | null) => !!path && /\.(png|jpe?g|webp)$/i.test(path);
  const decide = async (action: "approve" | "reject" | "retry" | "test-override") => {
    if (action !== "test-override" && !verifierName.trim()) { setError("Enter your name before continuing."); return; }
    setPending(true); setError(""); setMessage("");
    const body = { verifier_name: verifierName.trim() || "Sandbox tester", note: note.trim() || (action === "test-override" ? "Sandbox payout test" : undefined), override_for_testing: action === "test-override" };
    try {
      const updated = action === "approve" || action === "test-override" ? await api.approveInvoice(invoice.id, body) : action === "reject" ? await api.rejectInvoice(invoice.id, body) : await api.retryInvoice(invoice.id, body);
      setMessage(USE_MOCKS ? `Demo ${action} selected. No request was sent.` : `Invoice is now ${updated.status}.`);
      if (!USE_MOCKS) onChanged();
    } catch (cause) { setError(cause instanceof Error ? cause.message : `Could not ${action} invoice.`); }
    finally { setPending(false); }
  };

  return <div className="grid gap-8 lg:grid-cols-[1.4fr_1fr]">
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm font-semibold uppercase tracking-wide text-slate-500">Invoice {invoice.invoice_number}</p><h2 className="mt-2 text-2xl font-bold">{invoice.budget_line_name ?? "Budget line unavailable"}</h2></div><StatusBadge status={invoice.status} /></div>
        <dl className="mt-6 grid gap-4 sm:grid-cols-2">{[["Vendor", invoice.vendor_name ?? "Unknown"], ["Invoice amount", `$${invoice.amount.toFixed(2)} ${invoice.currency}`], ["Paid", `$${invoice.paid_amount.toFixed(2)}`], ["Still owed", `$${invoice.remaining_amount.toFixed(2)}`], ["Payout email", invoice.payout_email], ["Submitted", new Date(invoice.created_at).toLocaleDateString()]].map(([label, value]) => <div key={label}><dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</dt><dd className="mt-1 font-medium">{value}</dd></div>)}</dl>
        <p className="mt-6 border-t border-slate-100 pt-5 text-sm leading-6 text-slate-600">{invoice.description ?? "No description extracted."}</p>
      </section>
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="text-xl font-bold">Check results</h2><div className="mt-4 divide-y divide-slate-100">{invoice.checks.map((check) => <div key={check.id} className="flex flex-wrap items-start justify-between gap-3 py-3"><div className="min-w-0 flex-1"><p className="font-medium capitalize">{check.check_name.replaceAll("_", " ")}</p><p className="mt-1 text-sm text-slate-500">{check.detail}</p></div><div className="flex gap-2"><span className={`rounded-full px-2 py-1 text-xs font-bold ${check.passed ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"}`}>{check.passed ? "Pass" : "Fail"}</span><span className={`rounded-full px-2 py-1 text-xs font-bold ${check.severity === "hard" ? "bg-slate-100 text-slate-700" : "bg-sky-50 text-sky-800"}`}>{check.severity}</span></div></div>)}</div></section>
    </div>
    <aside className="space-y-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="text-xl font-bold">Evidence</h2>{evidenceUrl && isImage(invoice.evidence_path) ? <img src={evidenceUrl} alt="Delivery evidence" className="mt-4 max-h-72 w-full rounded-lg object-contain" /> : <p className="mt-4 text-sm text-slate-500">No proof photo available.</p>}{evidenceUrl && !isImage(invoice.evidence_path) && <a href={evidenceUrl} target="_blank" rel="noreferrer" className="text-emerald-700 underline">Open evidence file</a>}{invoiceUrl && <p className="mt-3"><a href={invoiceUrl} target="_blank" rel="noreferrer" className="text-sm font-medium text-emerald-700 underline">Open invoice PDF or image</a></p>}</section>
      {payoutCountryRestricted && <section role="alert" className="rounded-2xl border border-amber-300 bg-amber-50 p-6 text-amber-950"><h2 className="font-bold">PayPal payout unavailable</h2><p className="mt-2 text-sm">The current sandbox sender account cannot send payouts from its country. No vendor funds were sent. Configure a Payouts-enabled sandbox Business account from a supported sending country, then retry this invoice.</p></section>}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="text-xl font-bold">AI advisory</h2><p className="mt-3 text-sm leading-6 text-slate-600">{advisorySummary || "No advisory summary available."}</p><p className="mt-3 text-xs text-slate-500">Advisory only. The verifier makes the decision.</p></section>
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="text-xl font-bold">Your decision</h2>{((TEST_OVERRIDE_ENABLED && (invoice.status === "REJECTED" || invoice.status === "AWAITING_VERIFIER" || invoice.status === "NEEDS_REVIEW")) || invoice.status === "AWAITING_VERIFIER" || (invoice.status === "FAILED" || invoice.status === "PAYOUT_PENDING" || invoice.status === "PARTIALLY_PAID" || invoice.status === "AWAITING_FUNDS")) && <><label className="mt-4 block text-sm font-medium">Your name<input value={verifierName} onChange={(event) => setVerifierName(event.target.value)} className="mt-1 w-full rounded border border-slate-300 p-2" /></label><label className="mt-3 block text-sm font-medium">Note<textarea value={note} onChange={(event) => setNote(event.target.value)} className="mt-1 w-full rounded border border-slate-300 p-2" /></label></>}{invoice.status === "AWAITING_VERIFIER" && <div className="mt-4 grid grid-cols-2 gap-3"><button disabled={pending} onClick={() => void decide("approve")} className="rounded-lg bg-emerald-700 px-4 py-3 font-semibold text-white disabled:opacity-50">Approve</button><button disabled={pending} onClick={() => void decide("reject")} className="rounded-lg border border-rose-300 bg-rose-50 px-4 py-3 font-semibold text-rose-800 disabled:opacity-50">Reject</button></div>}{TEST_OVERRIDE_ENABLED && invoice.amount > 0 && (invoice.status === "REJECTED" || invoice.status === "AWAITING_VERIFIER" || invoice.status === "NEEDS_REVIEW") && <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950"><p>Sandbox test override: approve this invoice and attempt to send available funds to the vendor&apos;s registered PayPal account. App policy and AI checks are bypassed. PayPal can still reject the transfer, and no money is marked paid unless PayPal confirms it.</p><button disabled={pending} onClick={() => void decide("test-override")} className="mt-3 rounded-lg bg-amber-700 px-4 py-3 font-semibold text-white disabled:opacity-50">Approve for sandbox test</button></div>}{(invoice.status === "FAILED" || invoice.status === "PAYOUT_PENDING" || invoice.status === "PARTIALLY_PAID" || invoice.status === "AWAITING_FUNDS") && <button disabled={pending} onClick={() => void decide("retry")} className="mt-4 rounded-lg bg-emerald-700 px-4 py-3 font-semibold text-white disabled:opacity-50">{invoice.status === "PAYOUT_PENDING" ? "Check payout status" : invoice.status === "PARTIALLY_PAID" || invoice.status === "AWAITING_FUNDS" ? "Pay available funds" : "Retry payout"}</button>}{pending && <p role="status" className="mt-3 text-sm">Submitting decision…</p>}{message && <p role="status" className="mt-3 rounded bg-emerald-50 p-3 text-sm text-emerald-900">{message}</p>}{error && <p role="alert" className="mt-3 rounded bg-red-50 p-3 text-sm text-red-900">{error}</p>}</section>
    </aside>
  </div>;
}
