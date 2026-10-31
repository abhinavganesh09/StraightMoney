"use client";

import { useEffect, useState } from "react";
import VendorForm from "@/components/VendorForm";
import { api } from "@/lib/api";
import type { Campaign, CampaignSummary } from "@/lib/types";

export default function VendorPage() {
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingCampaign, setLoadingCampaign] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submittedMessage, setSubmittedMessage] = useState("");

  useEffect(() => {
    let active = true;
    api.listCampaigns()
      .then((items) => {
        if (!active) return;
        setCampaigns(items);
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
      .finally(() => { if (active) setLoadingCampaign(false); });
    return () => { active = false; };
  }, [selectedId, refreshKey]);

  const selectCampaign = (id: number) => {
    setCampaign(null);
    setSelectedId(id);
    setLoadingCampaign(true);
    setError(null);
    setSubmittedMessage("");
  };

  return <main className="mx-auto max-w-6xl px-5 py-10">
    <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-700">Vendor</p>
    <h1 className="mt-2 mb-8 text-4xl font-bold">Upload an invoice</h1>
    {loadingList && <p role="status">Loading campaigns…</p>}
    {!loadingList && !error && campaigns.length === 0 && <p>No campaigns are available yet.</p>}
    {campaigns.length > 0 && <label className="mb-6 block max-w-lg text-sm font-medium">
      Campaign
      <select value={selectedId ?? ""} onChange={(event) => selectCampaign(Number(event.target.value))} className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2">
        {campaigns.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
      </select>
    </label>}
    {loadingCampaign && <p role="status">Loading campaign details…</p>}
    {submittedMessage && <p role="status" className="mb-4 rounded bg-emerald-50 p-4 text-emerald-900">{submittedMessage}</p>}
    {error && <p role="alert" className="rounded bg-red-50 p-4 text-red-900">{error}</p>}
    {!loadingCampaign && !error && campaign && campaign.id === selectedId && <VendorForm key={campaign.id} campaign={campaign} onSubmitted={() => {
      setSubmittedMessage("Invoice submitted. Campaign data refreshed.");
      setLoadingCampaign(true);
      setRefreshKey((key) => key + 1);
    }} />}
  </main>;
}
