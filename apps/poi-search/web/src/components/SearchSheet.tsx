import { useEffect, useRef } from 'react'
import type { Result } from '../types/api'
import { formatDistance } from '../lib/geo'
import { resultSubtitle } from '../lib/resultSubtitle'

type Field = 'origin' | 'destination'

type Props = {
  open: boolean
  query: string
  loading: boolean
  results: Result[]
  hoveredId: string | null
  selectedId: string | null
  activeField: Field
  originLabel: string
  destinationLabel: string
  originIsCurrent: boolean
  onActivate: (field: Field) => void
  onSelectCurrentLocation: () => void
  onClose: () => void
  onQueryChange: (v: string) => void
  onCompositionStart: () => void
  onCompositionEnd: (v: string) => void
  onHover: (id: string | null) => void
  onSelect: (id: string) => void
}

export function SearchSheet({
  open,
  query,
  loading,
  results,
  hoveredId,
  selectedId,
  activeField,
  originLabel,
  destinationLabel,
  originIsCurrent,
  onActivate,
  onSelectCurrentLocation,
  onClose,
  onQueryChange,
  onCompositionStart,
  onCompositionEnd,
  onHover,
  onSelect,
}: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open, activeField])

  const fields: { id: Field; label: string; value: string }[] = [
    { id: 'origin', label: 'Điểm đi', value: originLabel },
    { id: 'destination', label: 'Điểm đến', value: destinationLabel },
  ]

  return (
    <div className={`search-sheet${open ? ' is-open' : ''}`}>
      <div className="place-fields">
        {fields.map((field) => {
          const editing = open && activeField === field.id
          return (
            <div
              key={field.id}
              className={`place-field${editing ? ' is-active' : ''}`}
              onClick={() => onActivate(field.id)}
            >
              <span className={`place-dot ${field.id}`} aria-hidden />
              {editing ? (
                <input
                  ref={inputRef}
                  className="place-input"
                  value={query}
                  aria-label={field.label}
                  placeholder={field.id === 'origin' ? 'Điểm đi' : 'Điểm đến'}
                  onClick={(event) => event.stopPropagation()}
                  onChange={(e) => onQueryChange(e.target.value)}
                  onCompositionStart={onCompositionStart}
                  onCompositionEnd={(e) => onCompositionEnd((e.target as HTMLInputElement).value)}
                />
              ) : (
                <span className="place-value">{field.value}</span>
              )}
              {editing ? (
                <button
                  type="button"
                  className="place-clear"
                  aria-label="Đóng"
                  onClick={(event) => {
                    event.stopPropagation()
                    onClose()
                  }}
                >
                  ×
                </button>
              ) : null}
            </div>
          )
        })}
      </div>

      {open ? (
        <div className="search-body">
          {activeField === 'origin' ? (
            <button
              type="button"
              className={`result-item current-location${originIsCurrent ? ' is-selected' : ''}`}
              onClick={onSelectCurrentLocation}
            >
              <span className="result-name">Vị trí hiện tại</span>
            </button>
          ) : null}
          {loading ? <div className="result-empty">Đang tìm…</div> : null}
          {!loading && !query.trim() && activeField === 'destination' ? (
            <div className="result-empty">Gõ tên địa điểm để xem gợi ý.</div>
          ) : null}
          {!loading && query.trim() && !results.length ? (
            <div className="result-empty">
              Không có kết quả. Thử <code>highlands</code>, <code>lotte</code>, <code>ga</code>.
            </div>
          ) : null}
          {results.length ? (
            <ul className="result-list">
              {results.map((r) => (
                <li key={r.poi_id}>
                  <button
                    type="button"
                    className={`result-item${hoveredId === r.poi_id ? ' is-active' : ''}${
                      selectedId === r.poi_id ? ' is-selected' : ''
                    }`}
                    onMouseEnter={() => onHover(r.poi_id)}
                    onMouseLeave={() => onHover(null)}
                    onClick={() => onSelect(r.poi_id)}
                  >
                    <span className="result-body">
                      <span className="result-name-row">
                        <span className="result-name">{r.name}</span>
                        <span className="result-dist">
                          {formatDistance(r.ranking_distance_m)}
                        </span>
                      </span>
                      <span className="result-meta">{resultSubtitle(r)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
