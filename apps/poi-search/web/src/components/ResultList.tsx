import type { Result } from '../types/api'
import { formatDistance } from '../lib/geo'
import { resultSubtitle } from '../lib/resultSubtitle'

type Props = {
  results: Result[]
  hoveredId: string | null
  selectedId: string | null
  loading: boolean
  onHover: (id: string | null) => void
  onSelect: (id: string) => void
}

export function ResultList({
  results,
  hoveredId,
  selectedId,
  loading,
  onHover,
  onSelect,
}: Props) {
  if (loading) {
    return <div className="result-empty">Đang tìm…</div>
  }
  if (!results.length) {
    return (
      <div className="result-empty">
        Không có kết quả. Thử <code>highlands</code>, <code>lotte</code>, <code>ga</code>,{' '}
        <code>aeon</code>.
      </div>
    )
  }

  return (
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
                <span className="result-dist">{formatDistance(r.ranking_distance_m)}</span>
              </span>
              <span className="result-meta">{resultSubtitle(r)}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}
