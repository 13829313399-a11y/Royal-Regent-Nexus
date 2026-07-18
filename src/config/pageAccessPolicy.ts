export interface PageAccessPolicy {
  /**
   * 临时全局浏览策略：已登录用户即使缺少页面权限，也允许进入页面查看。
   *
   * 页面内的新增、编辑、删除、审核、导出等操作仍必须继续使用
   * `authStore.can(...)` 和后端权限校验。后续需要恢复页面级 403 时，
   * 只需把此值改为 `false`。
   */
  allowAuthenticatedReadOnlyAccess: boolean
}

export const pageAccessPolicy: Readonly<PageAccessPolicy> = Object.freeze({
  allowAuthenticatedReadOnlyAccess: true,
})

type RoutePermissionMeta = Record<string, unknown>

export function shouldEnforcePagePermissions(
  meta: RoutePermissionMeta,
  policy: Readonly<PageAccessPolicy> = pageAccessPolicy,
) {
  return !policy.allowAuthenticatedReadOnlyAccess
    && meta.enforcePermissions === true
    && meta.allowAuthenticatedReadOnly !== true
}

export function shouldShowPageNavigation(
  permissions: readonly string[] | undefined,
  can: (permission: string) => boolean,
  policy: Readonly<PageAccessPolicy> = pageAccessPolicy,
) {
  return policy.allowAuthenticatedReadOnlyAccess
    || !permissions?.length
    || permissions.some((permission) => can(permission))
}

export function shouldRedirectForbiddenPageToHome(
  policy: Readonly<PageAccessPolicy> = pageAccessPolicy,
) {
  return policy.allowAuthenticatedReadOnlyAccess
}
