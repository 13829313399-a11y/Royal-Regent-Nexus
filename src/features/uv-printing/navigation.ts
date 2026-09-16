import type { UvPermissionCode } from './contracts'
import { UV_PERMISSIONS } from './contracts'

/**
 * 二级分段导航：驾驶舱、生产记录、机台、墨水、人员班次、产品定价、经营报表。
 * 顶栏只承载「返回华康A生产部、模块名、日期/班次、数据新鲜度、当前角色、主要操作」，
 * 具体业务导航固定在这一条。
 */

export interface UvNavEntry {
  key: string
  label: string
  path: string
  /** 现场人员也需要的高频入口。 */
  fieldFriendly: boolean
  /** 需要的最低权限码；正式路由以服务端为准。 */
  permission?: UvPermissionCode
  description: string
}

export const UV_NAV: UvNavEntry[] = [
  {
    key: 'overview',
    label: '驾驶舱',
    path: 'overview',
    fieldFriendly: true,
    permission: UV_PERMISSIONS.read,
    description: '现在要处理什么、哪些机器需要关注',
  },
  {
    key: 'production',
    label: '生产记录',
    path: 'production',
    fieldFriendly: true,
    permission: UV_PERMISSIONS.read,
    description: '待核作业、有效报工与入库核数',
  },
  {
    key: 'machines',
    label: '机台',
    path: 'machines',
    fieldFriendly: true,
    permission: UV_PERMISSIONS.read,
    description: '行政状态、采集新鲜度与当天任务',
  },
  {
    key: 'ink',
    label: '墨水',
    path: 'ink',
    fieldFriendly: true,
    permission: UV_PERMISSIONS.read,
    description: 'SKU 库存、阈值与收发流水',
  },
  {
    key: 'workforce',
    label: '人员班次',
    path: 'workforce',
    fieldFriendly: false,
    permission: UV_PERMISSIONS.read,
    description: '机台×班次排班与工资预览',
  },
  {
    key: 'catalog',
    label: '产品定价',
    path: 'catalog',
    fieldFriendly: false,
    permission: UV_PERMISSIONS.read,
    description: '产品工艺版本、价规与定价测算',
  },
  {
    key: 'reports',
    label: '经营报表',
    path: 'reports',
    fieldFriendly: false,
    permission: UV_PERMISSIONS.read,
    description: '日/月口径、费用结构与下钻',
  },
]

/** 现场人员一键切换的紧凑入口（现场模式）。 */
export const UV_FIELD_NAV_KEYS = ['overview', 'production', 'machines', 'ink']
