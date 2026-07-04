import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react'
import { useState } from 'react'

// ---------------------------------------------------------------------------
// Forge component kit — tokens in index.css, spec in docs/frontend-redesign.md
// ---------------------------------------------------------------------------

const focusRing =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ember/60'

// --- Buttons ---------------------------------------------------------------

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

const buttonVariants: Record<ButtonVariant, string> = {
  primary: 'bg-ember font-semibold text-ember-ink hover:bg-ember-bright',
  secondary:
    'border border-line-strong bg-raised font-medium text-ink hover:border-faint',
  ghost: 'font-medium text-mute hover:bg-raised hover:text-ink',
  danger: 'border border-loss/40 font-medium text-loss hover:bg-loss/10',
}

export function Button({
  variant = 'secondary',
  size = 'md',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  size?: 'sm' | 'md'
}) {
  const sizing = size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-2 text-sm'
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${focusRing} ${buttonVariants[variant]} ${sizing} ${className}`}
      {...props}
    />
  )
}

/** Two-step destructive action: first tap arms, second confirms. */
export function ConfirmButton({
  prompt,
  confirmLabel,
  busyLabel,
  busy = false,
  onConfirm,
  children,
  size = 'sm',
}: {
  prompt: string
  confirmLabel: string
  busyLabel?: string
  busy?: boolean
  onConfirm: () => void
  children: ReactNode
  size?: 'sm' | 'md'
}) {
  const [armed, setArmed] = useState(false)
  if (!armed) {
    return (
      <Button variant="ghost" size={size} onClick={() => setArmed(true)}>
        {children}
      </Button>
    )
  }
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-xs text-loss">{prompt}</span>
      <Button variant="danger" size={size} disabled={busy} onClick={onConfirm}>
        {busy ? (busyLabel ?? confirmLabel) : confirmLabel}
      </Button>
      <Button variant="ghost" size={size} onClick={() => setArmed(false)}>
        Cancel
      </Button>
    </span>
  )
}

// --- Form controls -----------------------------------------------------------

const controlBase = `w-full rounded border bg-raised px-3 py-2 text-sm text-ink placeholder:text-faint focus:outline-none ${focusRing}`

function controlBorder(invalid?: boolean) {
  return invalid
    ? 'border-loss focus:border-loss'
    : 'border-line focus:border-ember'
}

export function Input({
  invalid,
  className = '',
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return (
    <input
      className={`${controlBase} ${controlBorder(invalid)} ${className}`}
      {...props}
    />
  )
}

export function Textarea({
  invalid,
  className = '',
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }) {
  return (
    <textarea
      className={`${controlBase} ${controlBorder(invalid)} ${className}`}
      {...props}
    />
  )
}

export function Select({
  invalid,
  className = '',
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }) {
  return (
    <select
      className={`${controlBase} ${controlBorder(invalid)} ${className}`}
      {...props}
    />
  )
}

/** Uppercase condensed label wrapping a control. */
export function Field({
  label,
  hint,
  error,
  className = '',
  children,
}: {
  label: string
  hint?: string
  error?: string | null
  className?: string
  children: ReactNode
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1 block font-display text-xs font-semibold uppercase tracking-wider text-faint">
        {label}
      </span>
      {children}
      {error ? (
        <span className="mt-1 block text-xs text-loss">{error}</span>
      ) : (
        hint && <span className="mt-1 block text-xs text-faint">{hint}</span>
      )}
    </label>
  )
}

/** Exclusive choice rendered as a connected control strip. */
export function SegmentedControl<T extends string | number>({
  options,
  value,
  onChange,
  size = 'md',
  className = '',
}: {
  options: { value: T; label: ReactNode }[]
  value: T
  onChange: (value: T) => void
  size?: 'sm' | 'md'
  className?: string
}) {
  const sizing = size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3 py-1.5 text-sm'
  return (
    <div
      className={`inline-flex rounded border border-line bg-surface p-0.5 ${className}`}
      role="group"
    >
      {options.map((option) => (
        <button
          key={String(option.value)}
          onClick={() => onChange(option.value)}
          aria-pressed={option.value === value}
          className={`rounded-[3px] font-semibold transition-colors ${focusRing} ${sizing} ${
            option.value === value
              ? 'bg-ember text-ember-ink'
              : 'text-mute hover:text-ink'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

// --- Surfaces ----------------------------------------------------------------

export function Card({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`rounded-lg border border-line bg-surface ${className}`}>
      {children}
    </div>
  )
}

/** Section heading inside a card: condensed, uppercase, quiet. */
export function CardTitle({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <h2
      className={`font-display text-sm font-semibold uppercase tracking-wider text-mute ${className}`}
    >
      {children}
    </h2>
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
        <h1 className="font-display text-3xl font-bold uppercase tracking-wide">
          {title}
        </h1>
        {subtitle && <p className="mt-0.5 text-sm text-mute">{subtitle}</p>}
      </div>
      {actions}
    </div>
  )
}

/** Big number with a label — the scoreboard unit. */
export function StatCard({
  label,
  value,
  caption,
}: {
  label: string
  value: ReactNode
  caption?: ReactNode
}) {
  return (
    <Card className="p-4">
      <p className="font-display text-xs font-semibold uppercase tracking-wider text-faint">
        {label}
      </p>
      <p className="mt-1 font-data text-2xl font-semibold">{value}</p>
      {caption && <p className="mt-0.5 text-xs text-faint">{caption}</p>}
    </Card>
  )
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-line py-12 text-center">
      <p className="font-medium text-mute">{title}</p>
      {hint && <p className="mt-1 text-sm text-faint">{hint}</p>}
    </div>
  )
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-10 text-mute">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-line-strong border-t-ember" />
      <span className="text-sm">{label}</span>
    </div>
  )
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded border border-loss/40 bg-loss/10 px-4 py-3 text-sm text-loss">
      {message}
    </div>
  )
}

export function SuccessNote({ children }: { children: ReactNode }) {
  return (
    <div className="rounded border border-win/30 bg-win/10 px-4 py-3 text-sm text-win">
      {children}
    </div>
  )
}

// --- People ------------------------------------------------------------------

/** Stable hue per name so every player keeps a recognizable color. */
function nameHue(name: string): number {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) | 0
  }
  return Math.abs(hash) % 360
}

export function Avatar({
  name,
  size = 'md',
}: {
  name: string
  size?: 'sm' | 'md' | 'lg'
}) {
  const initials = name
    .split(/\s+/)
    .map((word) => word[0] ?? '')
    .join('')
    .slice(0, 2)
    .toUpperCase()
  const hue = nameHue(name)
  const sizing =
    size === 'sm'
      ? 'h-5 w-5 text-[9px]'
      : size === 'lg'
        ? 'h-12 w-12 text-base'
        : 'h-7 w-7 text-[11px]'
  return (
    <span
      className={`inline-flex flex-none items-center justify-center rounded-full font-bold ${sizing}`}
      style={{
        backgroundColor: `hsl(${hue} 35% 20%)`,
        color: `hsl(${hue} 65% 72%)`,
      }}
    >
      {initials}
    </span>
  )
}

/** Tappable player token: avatar + name, optional remove. */
export function PlayerChip({
  name,
  onClick,
  onRemove,
  active = false,
}: {
  name: string
  onClick?: () => void
  onRemove?: () => void
  active?: boolean
}) {
  const Tag = onClick ? 'button' : 'span'
  return (
    <Tag
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded border py-1 pl-1 pr-2 text-sm font-medium transition-colors ${focusRing} ${
        active
          ? 'border-ember/60 bg-ember/10 text-ink'
          : 'border-line bg-raised text-mute hover:border-line-strong hover:text-ink'
      }`}
    >
      <Avatar name={name} size="sm" />
      {name}
      {onRemove && (
        <span
          role="button"
          tabIndex={0}
          aria-label={`Remove ${name}`}
          onClick={(e) => {
            e.stopPropagation()
            onRemove()
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.stopPropagation()
              onRemove()
            }
          }}
          className="ml-0.5 text-faint hover:text-loss"
        >
          ✕
        </span>
      )}
    </Tag>
  )
}

// --- Data display --------------------------------------------------------------

/** Formats a signed rating delta with color. */
export function RatingDelta({ value }: { value: number }) {
  const rounded = Math.round(value * 10) / 10
  if (rounded > 0)
    return (
      <span className="font-data text-sm font-semibold text-win">
        ▲ +{rounded}
      </span>
    )
  if (rounded < 0)
    return (
      <span className="font-data text-sm font-semibold text-loss">
        ▼ {rounded}
      </span>
    )
  return <span className="font-data text-sm font-semibold text-mute">±0</span>
}

/** Podium ranks read as medals; the rest stay quiet. */
export function RankBadge({ rank }: { rank: number }) {
  const tone =
    rank === 1
      ? 'text-gold'
      : rank === 2
        ? 'text-silver'
        : rank === 3
          ? 'text-bronze'
          : 'text-faint'
  return <span className={`font-data font-semibold ${tone}`}>{rank}</span>
}

/** RD rendered as a confidence bar (1 − RD/350): full = settled rating. */
export function ConfidenceBar({ rd }: { rd: number }) {
  const confidence = Math.max(0, Math.min(1, 1 - rd / 350))
  return (
    <span
      className="inline-block h-1 w-16 overflow-hidden rounded-full bg-raised align-middle"
      title={`RD ${Math.round(rd)} — ${Math.round(confidence * 100)}% settled`}
    >
      <span
        className="block h-full rounded-full bg-faint"
        style={{ width: `${Math.round(confidence * 100)}%` }}
      />
    </span>
  )
}

/** Outcome/state pill. Win/loss = outcomes only, warn = attention, flag = meta. */
export function Pill({
  tone,
  children,
}: {
  tone: 'win' | 'loss' | 'draw' | 'warn' | 'flag'
  children: ReactNode
}) {
  const tones = {
    win: 'bg-win/10 text-win',
    loss: 'bg-loss/10 text-loss',
    draw: 'bg-raised text-mute',
    warn: 'bg-warn/10 text-warn',
    flag: 'bg-ember/10 text-ember',
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
    <div className="flex h-1.5 w-full gap-px overflow-hidden rounded-full bg-raised">
      <div className="rounded-l-full bg-ember" style={{ width: `${pct}%` }} />
      <div className="flex-1 rounded-r-full bg-line-strong" />
    </div>
  )
}

/** N-team stacked win-probability bar; the favored segment glows ember. */
export function ProbBar({
  segments,
}: {
  segments: { label: string; probability: number }[]
}) {
  if (segments.length === 0) return null
  const favored = segments.reduce(
    (best, s, i) => (s.probability > segments[best].probability ? i : best),
    0,
  )
  return (
    <div>
      <div className="flex h-2 w-full gap-px overflow-hidden rounded-full bg-raised">
        {segments.map((segment, i) => (
          <div
            key={i}
            className={i === favored ? 'bg-ember' : 'bg-line-strong'}
            style={{ width: `${Math.max(1, segment.probability * 100)}%` }}
            title={`${segment.label}: ${Math.round(segment.probability * 100)}%`}
          />
        ))}
      </div>
      <div className="mt-1 flex flex-wrap justify-between gap-x-3 text-xs">
        {segments.map((segment, i) => (
          <span
            key={i}
            className={i === favored ? 'font-medium text-ink' : 'text-faint'}
          >
            {segment.label}{' '}
            <span className="font-data">
              {Math.round(segment.probability * 100)}%
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}

export function FairnessMeter({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color =
    value > 0.8 ? 'bg-win' : value > 0.5 ? 'bg-warn' : 'bg-loss'
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-24 overflow-hidden rounded-full bg-raised">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-data text-sm font-semibold">{pct}%</span>
    </div>
  )
}
