"use client";

import { useState, type FormEvent } from "react";
import { api, USE_MOCKS } from "@/lib/api";
import type { Campaign } from "@/lib/types";

export default function VendorForm({ campaign, onSubmitted }: { campaign: Campaign; onSubmitted: () => void }) {
  const [lineId, setLineId] = useState(String(campaign.budget_lines[0]?.id ?? ""));
  const [number, setNumber] = useState("");
  const [invoice, setInvoice] = useState<File | null>(null);
  const [proof, setProof] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const line = campaign.budget_lines.find((item) => String(item.id) === lineId);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!line || !invoice || !proof) return;
    setPending(true); setError(""); setMessage("");
    const form = new FormData();
    form.append("campaign_id", String(campaign.id));
    form.append("budget_line_id", String(line.id));
    form.append("invoice_number", number.trim());
    if (line.vendor_id !== null) form.append("vendor_id", String(line.vendor_id));
    form.append("invoice_file", invoice);
    form.append("proof_photo", proof);
    try {
      const result = await api.uploadInvoice(form);
      setMessage(USE_MOCKS ? "Demo submission preview; no files were uploaded." : `Invoice ${result.invoice_number} submitted with status ${result.status}.`);
      if (!USE_MOCKS) onSubmitted();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not upload invoice."); }
    finally { setPending(false); }
  };
  return <div className="grid gap-8 lg:grid-cols-[1.4fr_1fr]">
    <form onSubmit={submit} className="space-y-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div><h2 className="text-xl font-bold">Submit delivery paperwork</h2><p className="mt-1 text-sm text-slate-500">Upload an invoice and a separate proof photo.</p></div>
      <label className="block text-sm font-medium">Budget line<select value={lineId} onChange={(event) => setLineId(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2">{campaign.budget_lines.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.vendor_name}</option>)}</select></label>
      {line && <div className="rounded-lg bg-slate-50 p-4 text-sm text-slate-600">Approved vendor: <strong className="text-slate-900">{line.vendor_name}</strong> · Remaining budget: <strong className="text-slate-900">${(line.budgeted_amount - line.paid_amount).toFixed(2)}</strong></div>}
      <label className="block text-sm font-medium">Invoice number<input required value={number} onChange={(event) => setNumber(event.target.value)} placeholder="INV-001" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
      <label className="block text-sm font-medium">Invoice file <span className="font-normal text-slate-500">(PDF or image)</span><input required type="file" accept="application/pdf,image/*" onChange={(event) => setInvoice(event.target.files?.[0] ?? null)} className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
      <label className="block text-sm font-medium">Delivery proof photo<input required type="file" accept="image/*" onChange={(event) => setProof(event.target.files?.[0] ?? null)} className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
      <button disabled={pending || !line} className="rounded-lg bg-emerald-700 px-5 py-3 font-semibold text-white disabled:opacity-50">{pending ? "Uploading…" : USE_MOCKS ? "Preview submission" : "Submit invoice"}</button>
      {pending && <p role="status" className="text-sm text-slate-600">Reading and checking your invoice. This can take up to three minutes; please keep this page open.</p>}
      {message && <p role="status" className="rounded-lg bg-emerald-50 p-4 text-sm text-emerald-900">{message}</p>}
      {error && <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-900">{error}</p>}
    </form>
    <aside className="self-start rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><p className="text-sm font-semibold uppercase tracking-wide text-slate-500">What happens next</p><ol className="mt-5 space-y-5 text-sm text-slate-600"><li><strong className="text-slate-900">1. Extract</strong><p>Invoice details are read and structured.</p></li><li><strong className="text-slate-900">2. Check</strong><p>Eight hard rules review the invoice and budget.</p></li><li><strong className="text-slate-900">3. Verify</strong><p>A human reviews the evidence before any payout.</p></li></ol></aside>
  </div>;
}
