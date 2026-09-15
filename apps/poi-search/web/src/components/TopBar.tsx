import type { Mode, Status } from '../types/api'

type Props = {
  mode: Mode
  onMode: (m: Mode) => void
  status: Status | null
}

export function TopBar({ mode, onMode, status }: Props) {
  return (
    <header className="topbar">
      <div className="brand">
        <strong>POI Search Demo</strong>
        <span className="brand-sub">console nghiên cứu · mock</span>
      </div>
      <div className="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'query_only'}
          className={mode === 'query_only' ? 'tab is-active' : 'tab'}
          onClick={() => onMode('query_only')}
        >
          Query-only
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'personalized'}
          className={mode === 'personalized' ? 'tab is-active' : 'tab'}
          onClick={() => onMode('personalized')}
        >
          Personalized
        </button>
      </div>
      <div className="chips">
        <span className="chip">{status?.versions.corpus_version ?? '…'}</span>
        <span className="chip">{status?.profile ?? '…'}</span>
        <span className="chip muted">Coverage: Hà Nội</span>
      </div>
    </header>
  )
}

/** Left search panel width as % of main row; grows with result count. */
export function panelWidthPercent(resultCount: number): number {
  if (resultCount <= 0) return 30
  if (resultCount <= 2) return 33
  if (resultCount <= 4) return 38
  return 42
}
