import { http } from '@/lib/http'

export type PresenceState = 'online' | 'away' | 'offline'
export type PresenceFilter = 'all' | PresenceState

export interface DirectoryMember {
  id: string
  display_name: string
  position: string
  primary_factory_id: string
  primary_department: string
  avatar_url: string
  avatar_version: string
  presence_state: PresenceState
  org_unit_id?: string
  org_name?: string
  org_kind?: string
  self_profile?: Partial<import('./collaboration').MemberProfile>
  actions?: { can_message: boolean; can_appreciate: boolean }
  is_contact?: boolean
  additional_assignments?: { org_name: string; department: string; position: string }[]
}

export interface DirectoryStateCounts {
  online: number
  away: number
  offline: number
}

export interface DirectorySummary {
  total_members: number
  state_counts: DirectoryStateCounts
  preview_members: DirectoryMember[]
}

export interface DirectoryMembersResponse {
  items: DirectoryMember[]
  total: number
  page: number
  page_size: number
  total_pages: number
  state_counts: DirectoryStateCounts
}

export interface DirectoryMembersParams {
  page?: number
  page_size?: number
  q?: string
  presence?: PresenceFilter
  factory_id?: string
  department?: string
  org_unit_id?: string
  contacts_only?: boolean
}

export interface DirectoryOrganization { id: string; name: string; kind: string; factory_id: string; parent_id: string; total: number; online: number; departments: { id: string; name: string }[] }

export interface DirectoryHeartbeatResponse {
  status: 'ok'
  written: boolean
  presence_state: 'online'
}

export const directoryApi = {
  async getSummary(signal?: AbortSignal) {
    const response = await http.get<DirectorySummary>('/directory/summary', { signal })
    return response.data
  },
  async getMembers(params: DirectoryMembersParams = {}, signal?: AbortSignal) {
    const response = await http.get<DirectoryMembersResponse>('/directory/members', { params, signal })
    return response.data
  },
  async getCatalog(signal?: AbortSignal) { return (await http.get<{ organizations: DirectoryOrganization[] }>('/directory/catalog', { signal })).data },
  async getMember(id: string, signal?: AbortSignal) { return (await http.get<DirectoryMember>(`/directory/members/${encodeURIComponent(id)}`, { signal })).data },
  async sendHeartbeat() {
    const response = await http.post<DirectoryHeartbeatResponse>('/directory/presence/heartbeat')
    return response.data
  },
}
