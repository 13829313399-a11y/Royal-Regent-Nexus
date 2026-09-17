export const qcInspectionPermissions = {
  read: 'qc_inspection:read',
  scheduleWrite: 'qc_inspection:schedule_write',
  orderWrite: 'qc_inspection:order_write',
  resultWrite: 'qc_inspection:result_write',
  problemWrite: 'qc_inspection:problem_write',
  reportExport: 'qc_inspection:report_export',
  customerManage: 'qc_inspection:customer_manage',
  auditRead: 'qc_inspection:audit_read',
  factorySummary: 'qc_inspection:factory_summary',
  groupSummary: 'qc_inspection:group_summary',
} as const

export type QcInspectionPermission = typeof qcInspectionPermissions[keyof typeof qcInspectionPermissions]
