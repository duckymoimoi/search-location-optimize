import type { Result } from '../types/api'

function field(parts: string[], label: string): string | null {
  const value = parts.find((part) => part.startsWith(label))?.slice(label.length).trim()
  return value || null
}

export function resultSubtitle(result: Result): string {
  if (result.address_text.trim()) return result.address_text.trim()

  const parts = result.context_text.split('|').map((part) => part.trim())
  const container = field(parts, 'Khuôn viên:')
  const nearby = field(parts, 'Gần:')
  const admin = field(parts, 'Vùng theo polygon OSM:')
  const context = [
    container ? `Trong ${container}` : null,
    nearby ? `Gần ${nearby}` : null,
    admin,
  ].filter((value): value is string => Boolean(value))

  return context.slice(0, 2).join(' · ') || 'Chưa có địa chỉ chi tiết'
}
