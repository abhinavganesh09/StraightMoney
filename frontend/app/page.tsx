"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Campaign, CampaignSummary } from "@/lib/types";
import PayPalDonateButton from "@/components/PayPalDonateButton";
import ProgressBar from "@/components/ProgressBar";
import StatusBadge from "@/components/StatusBadge";

const money = (value: number) => `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function CampaignPage() {
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ledgerCount, setLedgerCount] = useState<number | null>(null);

  const refreshAfterCapture = async () => {
    if (selectedId === null) return;
    const [updated, entries] = await Promise.all([api.getCampaign(selectedId), api.getLedger(selectedId)]);
    setCampaign(updated);
    setCampaigns((current) => current.map((item) => item.id === updated.id ? updated : item));
    setLedgerCount(entries.length);
  };

  useEffect(() => {
    let active = true;
    api.listCampaigns()
      .then((items) => {
        if (!active) return;
        setCampaigns(items);
        setLoadingDetail(items.length > 0);
        setSelectedId(items[0]?.id ?? null);
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Could not load campaigns.");
      })
      .finally(() => { if (active) setLoadingList(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (selectedId === null) return;
    let active = true;
    api.getCampaign(selectedId)
      .then((item) => { if (active) setCampaign(item); })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Could not load campaign details.");
      })
      .finally(() => { if (active) setLoadingDetail(false); });
    return () => { active = false; };
  }, [selectedId]);

  return <main className="mx-auto max-w-6xl space-y-8 px-5 py-10">
    <section aria-label="Campaign list">
      <h1 className="text-2xl font-bold">Campaigns</h1>
      {loadingList && <p role="status" className="mt-3 text-slate-600">Loading campaigns…</p>}
      {!loadingList && !error && campaigns.length === 0 && <p className="mt-3 text-slate-600">No campaigns yet.</p>}
      {campaigns.length > 0 && <div className="mt-4 flex flex-wrap gap-3">{campaigns.map((item) =>
        <button key={item.id} type="button" onClick={() => { setCampaign(null); setLedgerCount(null); setLoadingDetail(true); setError(null); setSelectedId(item.id); }} aria-pressed={selectedId === item.id}
          className={`rounded-lg border px-4 py-2 text-left ${selectedId === item.id ? "border-emerald-700 bg-emerald-50" : "border-slate-300 bg-white"}`}>
          <span className="block font-semibold">{item.title}</span>
          <span className="text-sm text-slate-600">{money(item.pool_balance)} raised of {money(item.goal_amount)}</span>
        </button>)}</div>}
    </section>
    {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-900">{error}</p>}
    {loadingDetail && <p role="status" className="text-slate-600">Loading campaign details…</p>}
    {!loadingDetail && !error && campaign && <>
      <div className="flex flex-wrap items-center justify-between gap-4"><p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-700">Community campaign</p><StatusBadge status={campaign.status} /></div>
      <div className="grid gap-8 lg:grid-cols-[1.5fr_1fr]">
        <section className="space-y-6">
          <div><h2 className="text-4xl font-bold tracking-tight sm:text-5xl">{campaign.title}</h2><p className="mt-4 max-w-2xl text-lg leading-8 text-slate-600">{campaign.description}</p></div>
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><div className="mb-6 grid grid-cols-2 gap-4"><div><p className="text-sm text-slate-500">Raised</p><p className="mt-1 text-3xl font-bold">{money(campaign.pool_balance)}</p></div><div><p className="text-sm text-slate-500">Goal</p><p className="mt-1 text-3xl font-bold">{money(campaign.goal_amount)}</p></div></div><ProgressBar current={campaign.pool_balance} goal={campaign.goal_amount} /></div>
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><div className="mb-5 flex items-center justify-between"><h3 className="text-xl font-bold">Where the money goes</h3><Link href={`/ledger/${campaign.id}`} className="text-sm font-semibold text-emerald-700 hover:underline">View public ledger →</Link></div>{ledgerCount !== null && <p role="status" className="text-sm text-slate-500">Ledger refreshed · {ledgerCount} entries</p>}<div className="divide-y divide-slate-100">{campaign.budget_lines.map((line) => <div key={line.id} className="flex items-center justify-between gap-4 py-4"><div><p className="font-semibold">{line.name}</p><p className="text-sm text-slate-500">{line.vendor_name ?? "Vendor pending"}</p></div><div className="text-right"><p className="font-semibold">{money(line.budgeted_amount - line.paid_amount)} remaining</p><p className="text-sm text-slate-500">{money(line.paid_amount)} paid of {money(line.budgeted_amount)}</p></div></div>)}</div></div>
        </section>
        <aside className="self-start rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">Support the campaign</p><h3 className="mt-2 text-2xl font-bold">Make a donation</h3><p className="mb-6 mt-2 text-sm leading-6 text-slate-600">Donations go toward approved budget lines. A human verifier reviews each vendor invoice before payout.</p><PayPalDonateButton campaignId={campaign.id} currency={campaign.currency} onCaptured={refreshAfterCapture} /></aside>
      </div>
    </>}
  </main>;
}
