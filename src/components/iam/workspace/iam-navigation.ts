import { UsersRound, GitPullRequestArrow, ShieldCheck, History, UserRoundPlus } from '@lucide/vue'

export const identityUiEnabled = import.meta.env.VITE_IAM_IDENTITY_UI_ENABLED !== 'false'
// Enable only after additive migration and compatible workers are deployed.
export const positionWorkbenchEnabled = import.meta.env.VITE_POSITION_WORKBENCH_ENABLED === 'true'
export const consolidatedIamEnabled = import.meta.env.VITE_IAM_CONSOLIDATED_UI_ENABLED === 'true' && identityUiEnabled && positionWorkbenchEnabled
const legacyNavigation = [
  { to: '/system/users', label: '人员与权限', icon: UsersRound, permissions: ['system:user_manage'] },
  {
    to: '/system/iam/requests',
    label: '变更办理',
    icon: GitPullRequestArrow,
    permissions: ['system:access_manage'],
    v2: true,
  },
  {
    to: '/system/iam/roles',
    label: '权限方案',
    icon: ShieldCheck,
    permissions: ['system:permission_catalog_read'],
  },
  {
    to: '/system/iam/audit',
    label: '授权与人员记录',
    icon: History,
    permissions: ['system:audit_read'],
    v2: true,
  },
  {
    to: '/system/users/registration',
    label: '账号办理',
    icon: UserRoundPlus,
    permissions: ['system:user_manage'],
  },
]
export const iamNavigation = consolidatedIamEnabled ? [
  { to: '/system/users', label: '人员与权限', icon: UsersRound, permissions: ['system:user_manage', 'system:access_manage'] },
  { to: '/system/iam/roles', label: '权限方案', icon: ShieldCheck, permissions: ['system:permission_catalog_read'] },
  { to: '/system/iam/audit', label: '操作记录', icon: History, permissions: ['system:user_manage', 'system:access_manage', 'system:audit_read'] },
] : legacyNavigation
export function iamPageGroup(path: string) {
  if (path.endsWith('/access')) return 'access'
  return path.split('/').at(-1) || 'users'
}
