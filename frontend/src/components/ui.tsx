import type { ReactNode } from 'react'

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-10 text-slate-400">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-600 border-t-indigo-400" />
      <span className="text-sm">{label}</span>
    </div>
  )
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-900/60 bg-red-950/40 px-4 py-3 text-sm text-red-300">
      {message}
    </div>
  )
}

export function SuccessNote({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-emerald-900/60 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
      {children}
    </div>
  )
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-800 py-12 text-center">
      <p className="font-medium text-slate-300">{title}</p>
      {hint && <p className="mt-1 text-sm text-slate-500">{hint}</p>}
    </div>
  )
}

export function Card({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={`rounded-xl border border-slate-800 bg-slate-900/60 ${className}`}
    >
      {children}
    </div>
  )
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string
  subtitle?: string
  actions?: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-400">{subtitle}</p>}
      </div>
      {actions}
    </div>
  )
}

/** Formats a signed rating delta with color. */
export function RatingDelta({ value }: { value: number }) {
  const rounded = Math.round(value * 10) / 10
  if (rounded > 0)
    return <span className="font-semibold text-emerald-400">+{rounded}</span>
  if (rounded < 0)
    return <span className="font-semibold text-red-400">{rounded}</span>
  return <span className="font-semibold text-slate-400">±0</span>
}

export function FairnessMeter({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color =
    value > 0.8 ? 'bg-emerald-500' : value > 0.5 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-800">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-sm font-semibold tabular-nums">{pct}%</span>
    </div>
  )
}
