import { mockCampaign, mockInvoices, mockLedger } from "./mockData";
import type { Campaign, CampaignCreate, CampaignSummary, Donation, Invoice, LedgerEntry, VerificationRequest } from "./types";

export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "true";
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

function errorMessage(payload: unknown, fallback: string): string {
  if (typeof payload !== "object" || payload === null) return fallback;
  const body = payload as { detail?: unknown; message?: unknown };
  const detail = body.detail ?? body.message;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      if (typeof item === "object" && item !== null && "msg" in item) return String(item.msg);
      return String(item);
    }).join("; ");
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, signal: init?.signal ?? AbortSignal.timeout(180000) });
  } catch (cause) {
    if (cause instanceof Error && cause.name === "TimeoutError") {
      throw new Error("The API took too long to respond. Refresh the invoice before trying again; the payment may still be pending.");
    }
    throw new Error(`Could not reach the API at ${API_URL}. Refresh the invoice before trying again; approval may have been recorded.`);
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(errorMessage(body, `API request failed: ${response.status} ${response.statusText}`));
  }
  return body as T;
}

export const api = {
  listCampaigns: async (): Promise<CampaignSummary[]> => USE_MOCKS ? [mockCampaign] : request<CampaignSummary[]>("/campaigns"),
  getCampaign: async (id: number): Promise<Campaign> => USE_MOCKS ? mockCampaign : request<Campaign>(`/campaigns/${id}`),
  getInvoices: async (campaignId?: number, status?: string): Promise<Invoice[]> => {
    if (USE_MOCKS) return mockInvoices.filter((invoice) => (campaignId === undefined || invoice.campaign_id === campaignId) && (!status || invoice.status === status));
    const query = new URLSearchParams();
    if (campaignId !== undefined) query.set("campaign_id", String(campaignId));
    if (status) query.set("status", status);
    return request<Invoice[]>(`/invoices${query.size ? `?${query}` : ""}`);
  },
  getInvoice: async (id: number): Promise<Invoice> => USE_MOCKS ? mockInvoices.find((invoice) => invoice.id === id)! : request<Invoice>(`/invoices/${id}`),
  getLedger: async (campaignId: number): Promise<LedgerEntry[]> => USE_MOCKS ? mockLedger : request<LedgerEntry[]>(`/campaigns/${campaignId}/ledger`),
  assetUrl: (path: string | null): string | null => path && !USE_MOCKS ? `${API_URL}/${path.replace(/^\//, "")}` : null,
  createCampaign: (data: CampaignCreate): Promise<Campaign> => USE_MOCKS ? Promise.resolve(mockCampaign) : request<Campaign>("/campaigns", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }),
  createDonation: (campaignId: number, donor_name: string, amount: number, simulate: boolean = false): Promise<Donation> => USE_MOCKS ? Promise.resolve({ id: 99, campaign_id: campaignId, donor_name, amount, currency: "USD", paypal_order_id: `MOCK-ORDER-${Date.now()}`, status: "created", created_at: new Date().toISOString() }) : request<Donation>(`/campaigns/${campaignId}/donations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ donor_name, amount, simulate }) }),
  captureDonation: (orderId: string): Promise<Donation> => USE_MOCKS ? Promise.resolve({ id: 99, campaign_id: 1, donor_name: "Demo Donor", amount: 0, currency: "USD", paypal_order_id: orderId, status: "captured", created_at: new Date().toISOString() }) : request<Donation>(`/donations/${orderId}/capture`, { method: "POST" }),
  uploadInvoice: (form: FormData): Promise<Invoice> => USE_MOCKS ? Promise.resolve(mockInvoices[0]) : request<Invoice>("/invoices", { method: "POST", body: form }),
  approveInvoice: (id: number, data: VerificationRequest): Promise<Invoice> => USE_MOCKS ? Promise.resolve(mockInvoices[0]) : request<Invoice>(`/invoices/${id}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }),
  rejectInvoice: (id: number, data: VerificationRequest): Promise<Invoice> => USE_MOCKS ? Promise.resolve(mockInvoices[0]) : request<Invoice>(`/invoices/${id}/reject`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }),
  retryInvoice: (id: number, data: VerificationRequest): Promise<Invoice> => USE_MOCKS ? Promise.resolve(mockInvoices[0]) : request<Invoice>(`/invoices/${id}/retry`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }),
};
