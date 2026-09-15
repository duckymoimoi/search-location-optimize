import { useEffect, useRef } from 'react'
import type { Result } from '../types/api'
import { formatDistance } from '../lib/geo'
import { resultSubtitle } from '../lib/resultSubtitle'

type Props = {
  open: boolean
  query: string
  loading: boolean
  results: Result[]
  hoveredId: string | null
  selectedId: string | null
  gpsLabel: string
  gpsOk: boolean
  onOpen: () => void
  onClose: () => void
  onQueryChange: (v: string) => void
  onCompositionStart: () => void
  onCompositionEnd: (v: string) => void
  onHover: (id: string | null) => void
  onSelect: (id: string) => void
  onRecenterGps: () => void
}

export function SearchSheet({
  open,
  query,
  loading,
  results,
  hoveredId,
  selectedId,
  gpsLabel,
  gpsOk,
  onOpen,
  onClose,
  onQueryChange,
  onCompositionStart,
  onCompositionEnd,
  onHover,
  onSelect,
  onRecenterGps,
}: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  return (
    <div className={`search-sheet${open ? ' is-open' : ''}`}>
      <div className="search-bar">
        {open ? (
          <button type="button" className="search-icon-btn" onClick={onClose} aria-label="Đóng">
            ←
          </button>
        ) : (
          <span className="search-icon" aria-hidden>
            ⌕
          </span>
        )}
        <input
          ref={inputRef}
          className="search-input"
          value={query}
          placeholder="Tìm địa điểm, địa chỉ…"
          onFocus={onOpen}
          onClick={onOpen}
          onChange={(e) => onQueryChange(e.target.value)}
          onCompositionStart={onCompositionStart}
          onCompositionEnd={(e) => onCompositionEnd((e.target as HTMLInputElement).value)}
        />
        {query ? (
          <button
            type="button"
            className="search-icon-btn"
            aria-label="Xóa"
            onClick={() => onQueryChange('')}
          >
            ×
          </button>
        ) : null}
      </div>

      {open ? (
        <div className="search-body">
          <div className="search-gps-row">
            <span className={gpsOk ? 'gps-ok' : 'gps-bad'}>{gpsLabel}</span>
            <button type="button" className="linkish" onClick={onRecenterGps}>
              Dùng vị trí hiện tại
            </button>
          </div>
          {loading ? <div className="result-empty">Đang tìm…</div> : null}
          {!loading && open && !query.trim() ? (
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
                    <span className="result-rank">{r.rank}</span>
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
