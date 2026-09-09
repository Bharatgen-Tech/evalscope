import { useCallback, useMemo, useRef, useState } from 'react'
import { ArrowUpDown, ChevronDown, Layers } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useLocale } from '@/contexts/LocaleContext'
import SearchInput from '@/components/ui/SearchInput'
import FilterChip from '@/components/ui/FilterChip'
import Button from '@/components/ui/Button'

/** Above this many options, render only a search-matched slice instead of every row at once. */
const DROPDOWN_SEARCH_THRESHOLD = 8
/** Cap on rows rendered even after search narrows the match set, so a broad query still stays cheap. */
const DROPDOWN_MAX_RENDERED = 50

export interface ReportFilters {
  search: string
  models: string[]
  datasets: string[]
  sortBy: 'model' | 'dataset' | 'time'
  sortOrder: 'asc' | 'desc'
  /**
   * Roll same-model reports into one expandable row each. Display-only - no
   * report is read, written, or merged; every child report keeps its own
   * identity and its own honestly-attributed score underneath.
   */
  groupByModel: boolean
}

interface ReportFiltersProps {
  filters: ReportFilters
  availableModels: string[]
  availableDatasets: string[]
  onChange: (filters: ReportFilters) => void
}

// Multi-select dropdown with checkboxes
function MultiSelectDropdown({
  label,
  options,
  selected,
  onChange,
}: {
  label: string
  options: string[]
  selected: string[]
  onChange: (selected: string[]) => void
}) {
  const { t } = useLocale()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  const toggle = (val: string) => {
    if (selected.includes(val)) onChange(selected.filter((s) => s !== val))
    else onChange([...selected, val])
  }

  const showSearch = options.length > DROPDOWN_SEARCH_THRESHOLD
  const matched = useMemo(
    () => (query.trim() ? options.filter((o) => o.toLowerCase().includes(query.trim().toLowerCase())) : options),
    [options, query],
  )
  const visible = matched.slice(0, DROPDOWN_MAX_RENDERED)
  const hiddenCount = matched.length - visible.length

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => {
          if (o) setQuery('')
          return !o
        })}
        className={cn(
          'coarse-target flex items-center gap-1.5 px-3 py-2 text-sm rounded-[var(--radius-sm)]',
          'bg-[var(--bg-deep)] border border-[var(--border)] text-[var(--text)]',
          'hover:border-[var(--border-md)] transition-all duration-[var(--transition)]',
          'cursor-pointer',
          selected.length > 0 && 'border-[var(--accent-dim)]',
        )}
      >
        <span className="truncate max-w-[120px]">
          {selected.length > 0 ? `${label} (${selected.length})` : label}
        </span>
        {/* text-dim allowed: dropdown chevron icon (DESIGN.md §Text) */}
        <ChevronDown size={14} className={cn('text-[var(--text-dim)] transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => { setOpen(false); setQuery('') }} />
          <div className="absolute z-20 top-full mt-1 left-0 min-w-[200px] max-w-[280px] rounded-[var(--radius)] bg-[var(--bg-card)] border border-[var(--border)] shadow-[var(--shadow-lg)] py-1">
            {showSearch && (
              <div className="px-2 pb-1.5">
                <SearchInput value={query} onChange={setQuery} placeholder={t('reports.filters.filterOptions')} />
              </div>
            )}
            <div className="max-h-[240px] overflow-y-auto">
              {options.length === 0 ? (
                // text-dim allowed: decorative em-dash placeholder (DESIGN.md §Text)
                <div className="px-3 py-2 text-xs text-[var(--text-dim)]">—</div>
              ) : visible.length === 0 ? (
                <div className="px-3 py-2 text-xs text-[var(--text-dim)]">{t('reports.filters.noMatches')}</div>
              ) : (
                <>
                  {visible.map((opt) => (
                    <label
                      key={opt}
                      className="flex items-center gap-2 px-3 py-1.5 text-sm text-[var(--text)] hover:bg-[var(--bg-card2)] cursor-pointer transition-colors"
                    >
                      <input
                        type="checkbox"
                        checked={selected.includes(opt)}
                        onChange={() => toggle(opt)}
                        className="accent-[var(--accent)] w-3.5 h-3.5"
                      />
                      <span className="truncate">{opt}</span>
                    </label>
                  ))}
                  {hiddenCount > 0 && (
                    <div className="px-3 py-1.5 text-xs text-[var(--text-dim)]">
                      {t('reports.filters.moreMatches', { n: hiddenCount })}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default function ReportFiltersBar({
  filters,
  availableModels,
  availableDatasets,
  onChange,
}: ReportFiltersProps) {
  const { t } = useLocale()

  const update = useCallback(
    (patch: Partial<ReportFilters>) => onChange({ ...filters, ...patch }),
    [filters, onChange],
  )

  const sortOptions: { value: ReportFilters['sortBy']; label: string }[] = [
    { value: 'time', label: t('reports.filters.time') },
    { value: 'model', label: t('reports.filters.model') },
    { value: 'dataset', label: t('reports.filters.dataset') },
  ]

  const activeFilters: { key: string; label: string; onRemove: () => void }[] = []
  filters.models.forEach((m) =>
    activeFilters.push({
      key: `model:${m}`,
      label: `model:${m}`,
      onRemove: () => update({ models: filters.models.filter((x) => x !== m) }),
    }),
  )
  filters.datasets.forEach((d) =>
    activeFilters.push({
      key: `dataset:${d}`,
      label: `dataset:${d}`,
      onRemove: () => update({ datasets: filters.datasets.filter((x) => x !== d) }),
    }),
  )
  return (
    <div className="flex flex-col gap-2">
      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-2">
        <SearchInput
          value={filters.search}
          onChange={(v) => update({ search: v })}
          placeholder={t('reports.filters.search')}
          className="w-full sm:w-72"
        />

        <MultiSelectDropdown
          label={t('reports.filters.model')}
          options={availableModels}
          selected={filters.models}
          onChange={(models) => update({ models })}
        />

        <MultiSelectDropdown
          label={t('reports.filters.dataset')}
          options={availableDatasets}
          selected={filters.datasets}
          onChange={(datasets) => update({ datasets })}
        />

        <Button
          variant={filters.groupByModel ? 'outline' : 'ghost'}
          size="sm"
          onClick={() => update({ groupByModel: !filters.groupByModel })}
          className={cn('gap-1.5', filters.groupByModel && 'border-[var(--accent-dim)]')}
          title={t('reports.filters.groupByModelHint')}
          aria-pressed={filters.groupByModel}
        >
          <Layers size={14} />
          {t('reports.filters.groupByModel')}
        </Button>

        {/* Sort */}
        <div className="flex items-center gap-1 ml-auto">
          <span className="text-[var(--text-muted)] text-xs">{t('reports.filters.sortBy')}:</span>
          <select
            value={filters.sortBy}
            onChange={(e) => update({ sortBy: e.target.value as ReportFilters['sortBy'] })}
            className="appearance-none px-2 py-1.5 pr-6 text-xs rounded-[var(--radius-sm)] bg-[var(--bg-deep)] border border-[var(--border)] text-[var(--text)] focus:outline-none focus:border-[var(--accent)] cursor-pointer"
          >
            {sortOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => update({ sortOrder: filters.sortOrder === 'asc' ? 'desc' : 'asc' })}
            className="!px-1.5"
            title={filters.sortOrder === 'asc' ? 'Ascending' : 'Descending'}
          >
            <ArrowUpDown size={14} className={filters.sortOrder === 'desc' ? 'rotate-180' : ''} />
          </Button>
        </div>
      </div>

      {/* Active filter chips */}
      {activeFilters.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {activeFilters.map((f) => (
            <FilterChip key={f.key} label={f.label} onRemove={f.onRemove} />
          ))}
        </div>
      )}
    </div>
  )
}
