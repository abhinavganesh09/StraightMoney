export default function ProgressBar({ current, goal }: { current: number; goal: number }) {
  const percent = goal > 0 ? Math.min(100, Math.round((current / goal) * 100)) : 0;
  return <div>
    <div className="mb-2 flex items-center justify-between text-sm text-slate-600"><span>Funded</span><span className="font-semibold text-slate-900">{percent}%</span></div>
    <div className="h-3 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label="Campaign funding progress">
      <div className="h-full rounded-full bg-emerald-600" style={{ width: `${percent}%` }} />
    </div>
  </div>;
}
