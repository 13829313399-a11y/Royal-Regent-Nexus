import type { FabricGroupIssue, FabricIssueGroupSave } from '@/api/warehouseOperations'
// Account-isolated tab memory, including uncertain requests interrupted by login redirects.
export type PendingGroupCommand = { kind: 'group'; body: FabricIssueGroupSave } | { kind: 'issue'; body: FabricGroupIssue }
export const pendingGroupCommands = new Map<string, PendingGroupCommand>()
