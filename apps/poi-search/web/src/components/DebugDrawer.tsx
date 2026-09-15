import type { SuggestResponse } from '../types/api'

type Props = {
  open: boolean
  onToggle: () => void
  last: SuggestResponse | null
  error: string | null
  note: string | null
}

export function DebugDrawer({ open, onToggle, last, error, note }: Props) {
  return (
    <section className={`debug${open ? ' is-open' : ''}`}>
      <button type="button" className="debug-toggle" onClick={onToggle}>
        {open ? 'Thu gọn debug' : 'Mở debug'}
        {last ? ` · ${Math.round(last.timings_ms.total ?? 0)} ms · cand ${last.candidate_count}` : ''}
      </button>
      {open ? (
        <div className="debug-body">
          {error ? <p className="debug-error">{error}</p> : null}
          {note ? <p className="debug-note">{note}</p> : null}
          {last ? (
            <dl className="debug-grid">
              <dt>request_id</dt>
              <dd>{last.request_id}</dd>
              <dt>exposure_id</dt>
              <dd>{last.exposure_id ?? 'null'}</dd>
              <dt>context_revision</dt>
              <dd>{last.context_revision}</dd>
              <dt>scope</dt>
              <dd>
                {last.scope_summary.mode} · {last.scope_summary.coverage_id}
              </dd>
              <dt>ranker</dt>
              <dd>{last.versions.ranker_id}</dd>
              <dt>release</dt>
              <dd>{last.versions.release_id}</dd>
              <dt>degraded</dt>
              <dd>{last.degraded_reasons.length ? last.degraded_reasons.join(', ') : 'none'}</dd>
              <dt>notes</dt>
              <dd>{last.scope_summary.notes.join(' · ') || '—'}</dd>
            </dl>
          ) : (
            <p className="muted">Chưa có response suggest.</p>
          )}
        </div>
      ) : null}
    </section>
  )
}
