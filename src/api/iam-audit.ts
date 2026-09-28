import { http } from '@/lib/http'
export interface AuditEventOut {
  id: string
  event_type: string
  actor_user_id: string
  actor_name: string
  target_user_id: string
  target_user_name: string
  permission_code: string
  factory_id: string
  department: string
  reason: string
  before_value: unknown
  after_value: unknown
  request_id: string
  ip_address: string
  created_at: string
}
export interface AuditFilters {
  actor_user_id: string
  target_user_id: string
  module_code: string
  factory_id: string
  department: string
  from: string
  to: string
  limit: number
}
export function auditParams(filters: AuditFilters) {
  const { from, to, ...rest } = filters
  // The existing server compares naive wall-time strings directly (iam.list_audit_events).
  // Its audit writer uses YYYY-MM-DD HH:mm:ss, so an ISO Z boundary would sort incorrectly.
  const boundary = (value: string) =>
    `${value.length === 16 ? value + ':00' : value}`.replace('T', ' ')
  return { ...rest, ...(from ? { from: boundary(from) } : {}), ...(to ? { to: boundary(to) } : {}) }
}
export async function getAuditEvents(filters: AuditFilters) {
  return (await http.get<AuditEventOut[]>('/iam/audit-events', { params: auditParams(filters) }))
    .data
}
