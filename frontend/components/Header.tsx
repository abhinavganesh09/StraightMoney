"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const roles = [
  { label: "Organizer", href: "/organizer" },
  { label: "Donor", href: "/" },
  { label: "Vendor", href: "/vendor" },
  { label: "Verifier", href: "/verifier" },
];

export default function Header() {
  const pathname = usePathname();
  const activeRole = roles.find((role) => role.href === pathname)?.label ?? "Donor";
  return <header className="border-b border-slate-200 bg-white">
    <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4">
      <Link href="/" className="flex items-center gap-3 text-xl font-bold tracking-tight text-slate-900">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-700 text-sm font-bold text-white">SM</span>
        StraightMoney
      </Link>
      <div className="flex flex-wrap items-center gap-3">
        <nav aria-label="Main navigation" className="flex items-center gap-1 text-sm font-medium">
          <Link className={`rounded-lg px-3 py-2 ${pathname === "/" ? "bg-slate-100 text-slate-900" : "text-slate-500 hover:text-slate-900"}`} href="/">Campaign</Link>
          <Link className={`rounded-lg px-3 py-2 ${pathname.startsWith("/ledger") ? "bg-slate-100 text-slate-900" : "text-slate-500 hover:text-slate-900"}`} href="/ledger/1">Public ledger</Link>
        </nav>
        <label className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Role
          <select aria-label="Switch role" value={activeRole} onChange={(event) => { window.location.href = roles.find((role) => role.label === event.target.value)?.href ?? "/"; }} className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium normal-case tracking-normal text-slate-900">
            {roles.map((role) => <option key={role.label}>{role.label}</option>)}
          </select>
        </label>
      </div>
    </div>
  </header>;
}
