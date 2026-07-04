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
    return (
      <span className="font-semibold tabular-nums text-emerald-400">
        ▲ +{rounded}
      </span>
    )
  if (rounded < 0)
    return (
      <span className="font-semibold tabular-nums text-rose-400">
        ▼ {rounded}
      </span>
    )
  return <span className="font-semibold tabular-nums text-slate-400">±0</span>
}

/** Initials avatar — every name gets a face. */
export function Avatar({ name, size = 'md' }: { name: string; size?: 'sm' | 'md' }) {
  const initials = name
    .split(/\s+/)
    .map((word) => word[0] ?? '')
    .join('')
    .slice(0, 2)
    .toUpperCase()
  const sizing = size === 'sm' ? 'h-5 w-5 text-[9px]' : 'h-7 w-7 text-[11px]'
  return (
    <span
      className={`inline-flex flex-none items-center justify-center rounded-full bg-indigo-500/15 font-bold text-indigo-300 ${sizing}`}
    >
      {initials}
    </span>
  )
}

/** Podium ranks read as medals; the rest stay quiet. */
export function RankBadge({ rank }: { rank: number }) {
  const tone =
    rank === 1
      ? 'text-amber-400'
      : rank === 2
        ? 'text-slate-300'
        : rank === 3
          ? 'text-amber-600'
          : 'text-slate-500'
  return <span className={`font-bold tabular-nums ${tone}`}>{rank}</span>
}

/** RD rendered as a confidence bar (1 − RD/350): full = settled rating. */
export function ConfidenceBar({ rd }: { rd: number }) {
  const confidence = Math.max(0, Math.min(1, 1 - rd / 350))
  return (
    <span
      className="inline-block h-1 w-16 overflow-hidden rounded-full bg-slate-800 align-middle"
      title={`RD ${Math.round(rd)} — ${Math.round(confidence * 100)}% settled`}
    >
      <span
        className="block h-full rounded-full bg-indigo-400"
        style={{ width: `${Math.round(confidence * 100)}%` }}
      />
    </span>
  )
}

/** Outcome/state pill. Emerald/rose = outcomes, amber = attention, indigo = meta. */
export function Pill({
  tone,
  children,
}: {
  tone: 'win' | 'loss' | 'draw' | 'warn' | 'flag'
  children: ReactNode
}) {
  const tones = {
    win: 'bg-emerald-500/10 text-emerald-300',
    loss: 'bg-rose-500/10 text-rose-300',
    draw: 'bg-slate-800 text-slate-400',
    warn: 'bg-amber-500/10 text-amber-300',
    flag: 'bg-indigo-500/10 text-indigo-300',
  }
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${tones[tone]}`}
    >
      {children}
    </span>
  )
}

/** Two-sided win-probability bar (left share = the given probability). */
export function WinProbBar({ probability }: { probability: number }) {
  const pct = Math.round(probability * 100)
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-slate-700">
      <div className="rounded-full bg-indigo-400" style={{ width: `${pct}%` }} />
    </div>
  )
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
