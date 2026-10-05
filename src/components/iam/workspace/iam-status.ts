export type StatusPresentation = {
  label: string
  tone: 'success' | 'warning' | 'neutral' | 'info' | 'danger'
}
const present = (state: string, map: Record<string, StatusPresentation>): StatusPresentation =>
  map[state] ?? { label: state || '待核实', tone: 'neutral' }
export const personStatusPresentation = (state: string) =>
  present(state, {
    active: { label: '在用', tone: 'success' },
    suspended: { label: '已冻结', tone: 'warning' },
    pending: { label: '待审核', tone: 'warning' },
    left: { label: '已离职', tone: 'neutral' },
    retired: { label: '已停用', tone: 'neutral' },
  })
export const assignmentStatusPresentation = (state: string) =>
  present(state, {
    current: { label: '当前任职', tone: 'success' },
    scheduled: { label: '未来生效', tone: 'info' },
    future: { label: '未来生效', tone: 'info' },
    ended: { label: '已结束', tone: 'neutral' },
    revoked: { label: '已撤销', tone: 'neutral' },
  })
export const changeStatusPresentation = (state: string) =>
  present(state, {
    draft: { label: '草稿', tone: 'neutral' },
    pending_approval: { label: '待有权管理员审核', tone: 'warning' },
    scheduled: { label: '已预约', tone: 'info' },
    applied: { label: '已生效', tone: 'success' },
    cancelled: { label: '已撤回', tone: 'neutral' },
    rejected: { label: '已驳回', tone: 'danger' },
  })
export const handoverStatusPresentation = (state: string) =>
  present(state, {
    pending: { label: '待接管', tone: 'warning' },
    completed: { label: '已接管', tone: 'success' },
    manual_review_required: { label: '需人工核实', tone: 'warning' },
    no_longer_required: { label: '业务已结束', tone: 'neutral' },
    changed_externally: { label: '责任已由业务流程调整', tone: 'info' },
  })
