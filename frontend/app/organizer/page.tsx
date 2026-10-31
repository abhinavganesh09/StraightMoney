"use client";

import { useEffect, useState } from "react";
import OrganizerForm from "@/components/OrganizerForm";
import { api } from "@/lib/api";
import type { Campaign } from "@/lib/types";

export default function OrganizerPage() {
  const [campaignId, setCampaignId] = useState(1);
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createdMessage, setCreatedMessage] = useState("");
  useEffect(() => {
    let active = true;
    api.getCampaign(campaignId).then((item) => { if (active) setCampaign(item); })
      .catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : "Could not load campaign."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [campaignId]);
  return <main className="mx-auto max-w-6xl px-5 py-10"><p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-700">Organizer</p><h1 className="mt-2 mb-8 text-4xl font-bold">Set up a campaign</h1>{loading && <p role="status">Loading campaign…</p>}{createdMessage && <p role="status" className="mb-4 rounded bg-emerald-50 p-4 text-emerald-900">{createdMessage}</p>}{error && <p role="alert" className="rounded bg-red-50 p-4 text-red-900">{error}</p>}{!loading && !error && campaign && <OrganizerForm campaign={campaign} onCreated={(id) => { setCreatedMessage(`Campaign ${id} created.`); setLoading(true); setCampaignId(id); }} />}</main>;
}
