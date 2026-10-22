import { Activity, CalendarDays, ClipboardCheck, Droplets, Gauge, Settings2, FileInput, Box, Layers3, Printer, FileCheck, CircleHelp, ShieldAlert, WifiOff, CircleCheck, TriangleAlert } from '@lucide/vue'

export const uvNavigation = [
  { path: 'live', title: '现场', icon: Activity },
  { path: 'planning', title: '任务与排程', icon: CalendarDays },
  { path: 'shifts', title: '班次与品质', icon: ClipboardCheck },
  { path: 'materials', title: '材料与设备', icon: Droplets },
  { path: 'analytics', title: '效益与核算', icon: Gauge },
  { path: 'settings', title: '基础设置', icon: Settings2 },
  { path: 'imports', title: '导入与导出', icon: FileInput },
]
export const uvCatalogIcons = { products: Box, fixtures: Layers3, 'process-versions': Settings2, machines: Printer, 'file-versions': FileCheck }
export const uvStatusIcons = { unknown: CircleHelp, denied: ShieldAlert, offline: WifiOff, completed: CircleCheck, conflict: TriangleAlert }
