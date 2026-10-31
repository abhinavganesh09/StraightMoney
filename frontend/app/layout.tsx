import type { Metadata } from "next";
import Header from "@/components/Header";
import "./globals.css";

export const metadata: Metadata = {
  title: "StraightMoney",
  description: "Community fundraising with a public spending ledger.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body className="min-h-screen bg-slate-50 text-slate-900"><Header />{children}<footer className="mx-auto max-w-6xl px-5 py-10 text-xs text-slate-500">StraightMoney demo · PayPal Sandbox concept · No real money moves</footer></body></html>;
}
