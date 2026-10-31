"use client";

import { useState, type FormEvent } from "react";
import { api, USE_MOCKS } from "@/lib/api";
import type { Campaign } from "@/lib/types";

type LineDraft = { name: string; amount: string; vendor: string; email: string };

export default function OrganizerForm({ campaign, onCreated }: { campaign: Campaign; onCreated: (id: number) => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [goal, setGoal] = useState("");
  const [organizer, setOrganizer] = useState("");
  const [lines, setLines] = useState<LineDraft[]>([{ name: "", amount: "", vendor: "", email: "" }]);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const update = (index: number, field: keyof LineDraft, value: string) => setLines((current) => current.map((line, i) => i === index ? { ...line, [field]: value } : line));

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPending(true); setError(""); setMessage("");
    try {
      const vendors = Array.from(new Map(lines.map((line) => [line.email.trim().toLowerCase(), { name: line.vendor.trim(), payout_email: line.email.trim() }])).values());
      const created = await api.createCampaign({
        title: title.trim(), description: description.trim(), goal_amount: Number(goal), currency: "USD", organizer_name: organizer.trim(), vendors,
        budget_lines: lines.map((line) => ({ name: line.name.trim(), budgeted_amount: Number(line.amount), vendor_name: line.vendor.trim(), vendor_payout_email: line.email.trim() })),
      });
      setMessage(USE_MOCKS ? "Demo campaign preview created; no data was saved." : `Campaign ${created.id} created.`);
      if (!USE_MOCKS) onCreated(created.id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not create campaign."); }
    finally { setPending(false); }
  };

  return <div className="grid gap-8 lg:grid-cols-[1.5fr_1fr]">
    <form onSubmit={submit} className="space-y-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div><h2 className="text-xl font-bold">Campaign details</h2><p className="mt-1 text-sm text-slate-500">Set a goal and assign each budget line to a vendor.</p></div>
      <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm font-medium">Campaign name<input required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Neighborhood garden" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label><label className="text-sm font-medium">Goal (USD)<input required type="number" min="1" step="0.01" value={goal} onChange={(e) => setGoal(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label></div>
      <label className="block text-sm font-medium">Organizer name<input required value={organizer} onChange={(e) => setOrganizer(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
      <label className="block text-sm font-medium">Description<textarea required rows={3} value={description} onChange={(e) => setDescription(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
      <div className="space-y-4"><div className="flex items-center justify-between"><h3 className="font-bold">Budget lines & vendors</h3><button type="button" onClick={() => setLines((current) => [...current, { name: "", amount: "", vendor: "", email: "" }])} className="text-sm font-semibold text-emerald-700">+ Add line</button></div>{lines.map((line, index) => <div key={index} className="grid gap-3 rounded-xl bg-slate-50 p-4 sm:grid-cols-2"><label className="text-xs font-medium">Item<input required value={line.name} onChange={(e) => update(index, "name", e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm" /></label><label className="text-xs font-medium">Budget (USD)<input required type="number" min="0.01" step="0.01" value={line.amount} onChange={(e) => update(index, "amount", e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm" /></label><label className="text-xs font-medium">Vendor name<input required value={line.vendor} onChange={(e) => update(index, "vendor", e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm" /></label><label className="text-xs font-medium">Vendor PayPal email<input required type="email" value={line.email} onChange={(e) => update(index, "email", e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm" /></label></div>)}</div>
      <button disabled={pending} className="rounded-lg bg-emerald-700 px-5 py-3 font-semibold text-white disabled:opacity-50">{pending ? "Creating…" : USE_MOCKS ? "Preview campaign" : "Create campaign"}</button>
      {message && <p role="status" className="rounded-lg bg-emerald-50 p-4 text-sm text-emerald-900">{message}</p>}
      {error && <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-900">{error}</p>}
    </form>
    <aside className="self-start rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><p className="text-sm font-semibold uppercase tracking-wide text-slate-500">Current example</p><h2 className="mt-2 text-xl font-bold">{campaign.title}</h2><p className="mt-2 text-sm text-slate-600">Goal ${campaign.goal_amount.toLocaleString()} · {campaign.budget_lines.length} assigned vendors</p><ul className="mt-5 space-y-3">{campaign.budget_lines.map((line) => <li key={line.id} className="flex justify-between border-b border-slate-100 pb-3 text-sm"><span>{line.name} · {line.vendor_name}</span><strong>${line.budgeted_amount}</strong></li>)}</ul></aside>
  </div>;
}
