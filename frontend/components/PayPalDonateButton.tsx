"use client";

import { useState } from "react";
import { PayPalScriptProvider, PayPalButtons } from "@paypal/react-paypal-js";
import { api, USE_MOCKS } from "@/lib/api";

export default function PayPalDonateButton({
  campaignId,
  currency = "USD",
  onCaptured,
}: {
  campaignId: number;
  currency?: string;
  onCaptured: () => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("50");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [capturing, setCapturing] = useState(false);
  const clientId = process.env.NEXT_PUBLIC_PAYPAL_CLIENT_ID;
  const valid = name.trim().length > 0 && Number.isFinite(Number(amount)) && Number(amount) > 0;

  const handleSimulatedDonation = async () => {
    if (!valid) {
      setError(`Enter your name and a valid ${currency} amount.`);
      return;
    }
    setCapturing(true);
    setError("");
    setMessage("");
    try {
      const donation = await api.createDonation(campaignId, name.trim(), Number(amount), true);
      await api.captureDonation(donation.paypal_order_id);
      setMessage("Donation captured! Refreshing campaign and ledger…");
      await onCaptured();
      setMessage("Donation captured! Campaign progress and ledger refreshed.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not complete donation.");
    } finally {
      setCapturing(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm font-medium text-slate-700">
          Your name
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Jane Doe"
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
          />
        </label>
        <label className="text-sm font-medium text-slate-700">
          Amount (USD)
          <input
            type="number"
            min="0.01"
            step="0.01"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
          />
        </label>
      </div>

      {USE_MOCKS ? (
        <button
          type="button"
          disabled={!valid}
          onClick={() => {
            setError("");
            setMessage(`Demo only: a $${Number(amount).toFixed(2)} donation by ${name.trim()} would start PayPal checkout.`);
          }}
          className="w-full rounded-lg bg-amber-400 px-5 py-3 font-semibold text-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Donate with PayPal
        </button>
      ) : clientId && !clientId.startsWith("your-") ? (
        <div className="space-y-2">
          <PayPalScriptProvider
            options={{
              clientId: clientId,
              currency: currency,
              intent: "capture",
              enableFunding: "card",
            }}
          >
            <PayPalButtons
              disabled={!valid || capturing}
              forceReRender={[campaignId, amount, name]}
              style={{ layout: "vertical", shape: "rect" }}
              createOrder={async () => {
                if (!valid) throw new Error("Enter your name and a valid USD amount.");
                setError("");
                setMessage("");
                try {
                  const donation = await api.createDonation(campaignId, name.trim(), Number(amount), false);
                  return donation.paypal_order_id;
                } catch (cause) {
                  setError(cause instanceof Error ? cause.message : "Could not start checkout.");
                  throw cause;
                }
              }}
              onApprove={async (data) => {
                setCapturing(true);
                setError("");
                setMessage("PayPal payment approved! Capturing donation into campaign pool…");
                try {
                  await api.captureDonation(data.orderID);
                  setMessage("Donation captured! Real sandbox funds credited to merchant and ledger refreshed.");
                  await onCaptured();
                } catch (cause) {
                  setError(cause instanceof Error ? cause.message : "Could not capture the donation.");
                } finally {
                  setCapturing(false);
                }
              }}
              onCancel={() => {
                setCapturing(false);
                setMessage("");
                setError("Checkout was cancelled. No donation was captured.");
              }}
              onError={(cause: unknown) => {
                setCapturing(false);
                const msg = (cause as Error)?.message || String(cause) || "PayPal checkout failed.";
                setError(msg);
              }}
            />
          </PayPalScriptProvider>

          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700 space-y-1.5">
            <div className="font-semibold text-slate-900">Live PayPal Sandbox Test Info:</div>
            <p>
              To see money <strong>actually deducted in PayPal Sandbox</strong>:
            </p>
            <ul className="list-disc pl-4 space-y-1 text-slate-600">
              <li>
                <strong>Card (no login needed):</strong> Click &ldquo;Debit or Credit Card&rdquo;, use Sandbox Test Card: <code className="bg-slate-200 px-1 py-0.5 rounded font-mono text-slate-900">4012 8888 8888 1881</code> (Exp: <code className="bg-slate-200 px-1 py-0.5 rounded font-mono text-slate-900">12/28</code>, CVV: <code className="bg-slate-200 px-1 py-0.5 rounded font-mono text-slate-900">123</code>, Zip: <code className="bg-slate-200 px-1 py-0.5 rounded font-mono text-slate-900">95131</code>).
              </li>
              <li>
                <strong>PayPal Login:</strong> Log in with your Sandbox Personal (Buyer) test account from <a href="https://developer.paypal.com/dashboard/accounts" target="_blank" rel="noreferrer" className="underline font-medium text-blue-700">developer.paypal.com</a>.
              </li>
            </ul>
          </div>

          <div className="space-y-1 text-center pt-1">
            <button
              type="button"
              disabled={!valid || capturing}
              onClick={handleSimulatedDonation}
              className="text-xs text-slate-500 hover:text-emerald-700 underline disabled:opacity-50"
            >
              Simulate donation without PayPal deduction (UI demo mode)
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-sm text-amber-800">
            Set NEXT_PUBLIC_PAYPAL_CLIENT_ID to your sandbox client ID to enable live checkout.
          </p>
          <button
            type="button"
            disabled={!valid || capturing}
            onClick={handleSimulatedDonation}
            className="w-full rounded-lg bg-emerald-700 px-5 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            Simulate Donation (${Number(amount || 0).toFixed(2)})
          </button>
        </div>
      )}

      {capturing && <p role="status" className="text-sm text-slate-600">Capturing donation…</p>}
      {message && <p role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900">{message}</p>}
      {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-900">{error}</p>}
      {USE_MOCKS && <p className="text-xs text-slate-500">Demo mode uses mock data. No payment is made.</p>}
    </div>
  );
}
