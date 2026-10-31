"use client";

import { useEffect, useState } from "react";
import VerifierReview from "@/components/VerifierReview";
import { api } from "@/lib/api";
import type { CampaignSummary, Invoice } from "@/lib/types";

export default function VerifierPage() {
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [campaignId, setCampaignId] = useState<number | null>(null);
  const [status, setStatus] = useState("");
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    api.listCampaigns().then((items) => {
      if (active) { setCampaigns(items); setCampaignId(items[0]?.id ?? null); setLoading(items.length > 0); }
    }).catch((cause: unknown) => {
      if (active) { setError(cause instanceof Error ? cause.message : "Could not load campaigns."); setLoading(false); }
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (campaignId === null) return;
    let active = true;
    api.getInvoices(campaignId, status || undefined).then((items) => {
      if (!active) return;
      setInvoices(items);
      setInvoice(null);
      setSelectedId(items[0]?.id ?? null);
      setDetailLoading(items.length > 0);
      setError(null);
    }).catch((cause: unknown) => {
      if (active) setError(cause instanceof Error ? cause.message : "Could not load invoices.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [campaignId, status, refreshKey]);

  useEffect(() => {
    if (selectedId === null) return;
    let active = true;
    api.getInvoice(selectedId).then((item) => {
      if (active) { setInvoice(item); setError(null); }
    }).catch((cause: unknown) => {
      if (active) setError(cause instanceof Error ? cause.message : "Could not load invoice details.");
    }).finally(() => { if (active) setDetailLoading(false); });
    return () => { active = false; };
  }, [selectedId, refreshKey]);

  return <main className="mx-auto max-w-6xl px-5 py-10">
    <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-700">Verifier</p>
    <h1 className="mt-2 text-4xl font-bold">Review invoices</h1>
    <p className="mt-2 mb-8 text-slate-600">Review policy checks, AI flags, and evidence before choosing a decision.</p>
    <div className="mb-6 flex flex-wrap gap-4"><label className="text-sm">Campaign<select value={campaignId ?? ""} onChange={(event) => { setLoading(true); setCampaignId(Number(event.target.value)); }} className="ml-2 rounded border border-slate-300 bg-white p-2">{campaigns.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label><label className="text-sm">Status<select value={status} onChange={(event) => { setLoading(true); setStatus(event.target.value); }} className="ml-2 rounded border border-slate-300 p-2"><option value="">All</option><option value="AWAITING_VERIFIER">Awaiting verifier</option><option value="FAILED">Failed payout</option><option value="AWAITING_FUNDS">Awaiting funds</option><option value="PARTIALLY_PAID">Partially paid</option><option value="PAYOUT_PENDING">Payout pending</option><option value="REJECTED">Rejected</option><option value="PAID">Paid</option><option value="NEEDS_REVIEW">Needs review</option></select></label></div>
    {loading && <p role="status">Loading invoices…</p>}
    {error && <p role="alert" className="mb-5 rounded border border-red-200 bg-red-50 p-4 text-red-900">{error}</p>}
    {!loading && !error && invoices.length === 0 && <p>No invoices match these filters.</p>}
    {invoices.length > 0 && <div className="mb-6 flex flex-wrap gap-2">{invoices.map((item) => <button type="button" key={item.id} aria-pressed={selectedId === item.id} onClick={() => { setInvoice(null); setDetailLoading(true); setSelectedId(item.id); }} className={`rounded border px-3 py-2 text-sm ${selectedId === item.id ? "border-emerald-700 bg-emerald-50" : "border-slate-300 bg-white"}`}>{item.invoice_number} · {item.status}</button>)}</div>}
    {detailLoading && !error && <p role="status">Loading invoice details…</p>}
    {!loading && !detailLoading && !error && invoice && invoices.some((item) => item.id === invoice.id) && <VerifierReview invoice={invoice} onChanged={() => { setLoading(true); setRefreshKey((key) => key + 1); }} />}
  </main>;
}
