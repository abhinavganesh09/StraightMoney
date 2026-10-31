"use client";

import { useMemo } from "react";
import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef } from "ag-grid-community";
import type { LedgerEntry } from "@/lib/types";
import { api } from "@/lib/api";

ModuleRegistry.registerModules([AllCommunityModule]);

export default function LedgerGrid({ entries }: { entries: LedgerEntry[] }) {
  const columns = useMemo<ColDef<LedgerEntry>[]>(() => [
    { field: "created_at", headerName: "Date", valueFormatter: ({ value }) => value ? new Date(value as string).toLocaleDateString() : "", minWidth: 130 },
    { field: "type", headerName: "Type", minWidth: 110 },
    { field: "actor_name", headerName: "From / to", minWidth: 170 },
    { field: "amount", headerName: "Amount", valueFormatter: ({ value }) => `$${Number(value).toFixed(2)}`, minWidth: 130 },
    { field: "status", headerName: "Status", minWidth: 120 },
    { field: "proof_url", headerName: "Proof", cellRenderer: ({ value }: { value: string | null }) => { const url = api.assetUrl(value); return url ? <a className="font-medium text-emerald-700 underline" href={url} target="_blank" rel="noreferrer">View proof</a> : <span className="text-slate-400">—</span>; }, minWidth: 120 },
  ], []);
  return <div className="h-[430px] w-full"><AgGridReact rowData={entries} columnDefs={columns} defaultColDef={{ sortable: true, filter: true, resizable: true, flex: 1 }} pagination paginationPageSize={10} theme={themeQuartz.withParams({ accentColor: "#047857", fontFamily: "Arial, sans-serif" })} /></div>;
}
