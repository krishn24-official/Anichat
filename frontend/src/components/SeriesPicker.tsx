import type { Series } from '../types'

interface Props {
  series: Series[]
  value: string | null
  onChange: (id: string | null) => void
}

/**
 * Pick a series to search in ("All series" by default). Sequels are grouped under their
 * franchise (Naruto: Naruto + Naruto Shippuden).
 * Called by: components/Header.tsx
 */
export function SeriesPicker({ series, value, onChange }: Props) {
  const groups = new Map<string, Series[]>()
  for (const s of series) groups.set(s.franchise, [...(groups.get(s.franchise) ?? []), s])
  const titleOf = (id: string) => series.find((s) => s.id === id)?.title ?? id

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="sr-only">Series</span>
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
        className="max-w-[11rem] truncate rounded-lg border border-line bg-panel-2 px-2.5 py-1.5 text-text focus:outline-2 focus:outline-accent sm:max-w-none"
      >
        <option value="">All series</option>
        {[...groups.entries()].map(([franchise, members]) =>
          members.length === 1 ? (
            <option key={members[0].id} value={members[0].id}>{members[0].title}</option>
          ) : (
            <optgroup key={franchise} label={titleOf(franchise)}>
              {members.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
            </optgroup>
          ),
        )}
      </select>
    </label>
  )
}
