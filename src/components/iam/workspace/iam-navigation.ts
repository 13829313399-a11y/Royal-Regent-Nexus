import { UsersRound, GitPullRequestArrow, ShieldCheck, History, UserRoundPlus } from '@lucide/vue'

export const identityUiEnabled = import.meta.env.VITE_IAM_IDENTITY_UI_ENABLED !== 'false'
export const iamNavigation = [
  { to: '/system/users', label: '人员中心', icon: UsersRound, permissions: ['system:user_manage'] },
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
export function iamPageGroup(path: string) {
  if (path.endsWith('/access')) return 'access'
  return path.split('/').at(-1) || 'users'
}
