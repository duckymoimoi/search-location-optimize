import { useState } from 'react'
import type { DemoUser, Mode, Status } from '../types/api'
import { BACKENDS, type BackendId } from '../api/client'

type Props = {
  mode: Mode
  onMode: (m: Mode) => void
  backendId: BackendId
  onBackend: (id: BackendId) => void
  status: Status | null
  users: DemoUser[]
  demoUserId: string
  onDemoUser: (id: string) => void
}

export function TopBar({ mode, onMode, backendId, onBackend, status, users, demoUserId, onDemoUser }: Props) {
  const [open, setOpen] = useState(false)
  const personalized = mode === 'personalized'
  const options = users.length
    ? users
    : [{ demo_user_id: demoUserId, label: 'Đang tải người dùng…' }]
  if (!open) {
    return (
      <header className="topbar is-collapsed">
        <button
          type="button"
          className="context-toggle"
          aria-expanded={false}
          onClick={() => setOpen(true)}
        >
          Ngữ cảnh
        </button>
        <span className="chip">{personalized ? 'Personalized' : 'Query-only'}</span>
        <label className="chip model-switch">
          Mô hình
          <select
            aria-label="Mô hình tìm kiếm"
            value={backendId}
            onChange={(event) => onBackend(event.target.value as BackendId)}
          >
            {BACKENDS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </header>
    )
  }
  return (
    <header className="topbar">
      <button
        type="button"
        className="context-toggle"
        aria-expanded
        onClick={() => setOpen(false)}
      >
        Đóng
      </button>
      <div className="brand">
        <strong>POI Search Demo</strong>
        <span className="brand-sub">ngữ cảnh demo</span>
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
          aria-selected={personalized}
          className={personalized ? 'tab is-active' : 'tab'}
          onClick={() => onMode('personalized')}
        >
          Personalized
        </button>
      </div>
      <div className="chips">
        <label className="chip model-switch">
          Mô hình
          <select
            aria-label="Mô hình tìm kiếm"
            value={backendId}
            onChange={(event) => onBackend(event.target.value as BackendId)}
          >
            {BACKENDS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <span className="chip">{status?.versions.index_version ?? status?.coverage_id ?? '…'}</span>
        <span className="chip">{status?.profile ?? '…'}</span>
      </div>
      <div className="context-fields">
        <label>
          Người dùng demo
          <select
            value={demoUserId}
            disabled={!personalized}
            onChange={(event) => onDemoUser(event.target.value)}
          >
            {options.map((user) => (
              <option key={user.demo_user_id} value={user.demo_user_id}>
                {user.label}
              </option>
            ))}
          </select>
        </label>
        <p className="context-note">
          {personalized
            ? 'Lịch sử lấy theo thời điểm mỗi lần chọn, và chỉ đổi thứ tự trong nhóm tên tương đương.'
            : 'Query-only khóa vị trí và người dùng. Phạm vi cố định toàn corpus.'}
        </p>
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
