"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import LedgerGrid from "@/components/LedgerGrid";
import { api, USE_MOCKS } from "@/lib/api";
import type { Campaign, LedgerEntry } from "@/lib/types";

export default function LedgerPage() {
  const { campaignId } = useParams<{ campaignId: string }>();
  const id = Number(campaignId);
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [entries, setEntries] = useState<LedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isInteger(id) || id < 1) return;
    let active = true;
    Promise.all([api.getCampaign(id), api.getLedger(id)]).then(([item, rows]) => {
      if (active) { setCampaign(item); setEntries(rows); setError(null); }
    }).catch((cause: unknown) => {
      if (active) setError(cause instanceof Error ? cause.message : "Could not load the ledger.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id]);

  const total = (type: string, status: string) => entries.filter((item) => item.type === type && item.status === status).reduce((sum, item) => sum + item.amount, 0);
  return <main className="mx-auto max-w-6xl px-5 py-10">
    <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-700">Public record</p>
    <div className="mt-2 mb-8 flex flex-wrap items-end justify-between gap-4"><div><h1 className="text-4xl font-bold">Transparency ledger</h1><p className="mt-2 text-slate-600">{campaign?.title ?? "Campaign"} · donations in and vendor payouts out</p></div><Link href="/" className="text-sm font-semibold text-emerald-700 hover:underline">← Back to campaign</Link></div>
    {!Number.isInteger(id) || id < 1 ? <p role="alert" className="rounded bg-red-50 p-4 text-red-900">Invalid campaign ID.</p> : null}
    {loading && <p role="status">Loading ledger…</p>}
    {error && <p role="alert" className="rounded bg-red-50 p-4 text-red-900">{error}</p>}
    {!loading && !error && campaign && <><div className="mb-6 grid gap-4 sm:grid-cols-3">{[["Donations captured", `$${total("donation", "captured").toFixed(2)}`], ["Vendor payouts", `$${total("payout", "success").toFixed(2)}`], ["Ledger entries", String(entries.length)]].map(([label, value]) => <div key={label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><p className="text-sm text-slate-500">{label}</p><p className="mt-1 text-2xl font-bold">{value}</p></div>)}</div><div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><LedgerGrid entries={entries} /></div>{USE_MOCKS && <p className="mt-4 text-xs text-slate-500">Demo data for the UI preview.</p>}</>}
  </main>;
}
