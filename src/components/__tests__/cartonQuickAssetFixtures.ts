import type { AuthMeResponse, AuthGrant } from '@/api/auth'
import type { AssetDepartment, QuickAsset, QuickTarget } from '@/api/cartonQuickAssets'

export function quickSession(departments: AssetDepartment[] = ['sales-business'], confirm = true): AuthMeResponse {
  const permissions = ['carton_asset:read', 'carton_asset:manage', ...(confirm ? ['carton_asset:confirm'] : [])]
  return { id: 'quick-user', username: 'quick-user', display_name: '测试经办人', roles: [], permissions,
    factory_scopes: ['huaxing'], department_scopes: departments, force_password_change: false, authz_mode: 'enforce', authorization_version: 1,
    grants: departments.map(department => ({ role_id: `position-${department}`, role_name: department,
      factory_id: 'huaxing', department, permissions, data_scope: 'department', unrestricted_department: true,
      scope_mode: 'own_factory' }) as AuthGrant),
    effective_access: departments.flatMap(department => permissions.map(permission_code => ({ permission_code,
      factory_id: 'huaxing', department, effect: 'allow', allowed: true, source_type: 'role_binding', source_ids: [department] }))),
  }
}
export function supplierQuickSession(): AuthMeResponse {
  const permissions = ['carton_asset:read', 'carton_asset:manage', 'carton_supplier:read', 'carton_supplier:edit']
  return { ...quickSession(), id: 'supplier-user', username: 'supplier-user', grants: [], permissions,
    effective_access: permissions.map(permission_code => ({ permission_code, factory_id: '*', department: '*',
      effect: 'allow', allowed: true, source_type: 'user_override', source_ids: [permission_code] })),
  }
}
export function quickAsset(values: Partial<QuickAsset> = {}): QuickAsset {
  return { id: 'asset-one', factory_id: 'huaxing', owner_department: 'sales-business', purpose: 'MATERIAL', kind: 'text',
    file_name: '文字资料.txt', content_type: 'text/plain', sha256: 'sha', revision: 1, contract_number: '', text: '文字', targets: [], warning: '',
    workflow: { status: 'PENDING', version: 1, note: '', previous_asset_id: '', superseded_by_asset_id: '', updated_by_name: '',
      updated_at: '', confirmed_by_name: '', confirmed_at: '', confirmation_note: '' }, ...values }
}
export function quickTarget(values: Partial<QuickTarget> = {}): QuickTarget {
  return { kind: 'SCHEDULE', id: 'batch-one', sheet: '待生产', row: 9, fingerprint: 'a'.repeat(64), contract_no: 'QUICK-1234',
    item_no: 'ITEM-1', customer_name: '测试客户', ...values }
}
