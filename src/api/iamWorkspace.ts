import { http } from '@/lib/http'
import type { WorkspaceTaskPage } from '@/features/identity-management/workspace/contracts'
import type { PasswordResetRequestDetail } from '@/api/system'
import type { ChangeRecord } from '@/api/identity'
export type WorkspacePasswordDetail = PasswordResetRequestDetail & { available_actions: string[] }
export const iamWorkspaceApi = {
  change: async (id: string) => (await http.get<ChangeRecord>(`/iam/workspace/identity-changes/${encodeURIComponent(id)}`)).data,
  tasks: async (params: Record<string, string | number>) =>
    (await http.get<WorkspaceTaskPage>('/iam/workspace/tasks', { params })).data,
  passwordReset: async (id: string) =>
    (await http.get<WorkspacePasswordDetail>(`/iam/workspace/password-resets/${encodeURIComponent(id)}`)).data,
}
