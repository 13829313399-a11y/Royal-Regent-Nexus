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
}

export interface DirectoryHeartbeatResponse {
  status: 'ok'
  written: boolean
  presence_state: 'online'
}

export const directoryApi = {
  async getSummary() {
    const response = await http.get<DirectorySummary>('/directory/summary')
    return response.data
  },
  async getMembers(params: DirectoryMembersParams = {}) {
    const response = await http.get<DirectoryMembersResponse>('/directory/members', { params })
    return response.data
  },
  async sendHeartbeat() {
    const response = await http.post<DirectoryHeartbeatResponse>('/directory/presence/heartbeat')
    return response.data
  },
}
