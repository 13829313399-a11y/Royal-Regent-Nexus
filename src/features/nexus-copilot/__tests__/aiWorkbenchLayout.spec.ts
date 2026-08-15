import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ConversationList from '../components/ConversationList.vue'
import InspectorPanel from '../workbench/InspectorPanel.vue'
import WorkbenchShell from '../workbench/WorkbenchShell.vue'

const conversation = {
  id: 'aicv-11111111111111111111111111111111',
  mode: 'PERSISTENT' as const,
  status: 'ACTIVE' as const,
  title: '注塑排产复盘',
  factory_scope: 'huaxing',
  revision: 2,
  created_at: '2026-08-14T08:00:00+08:00',
  updated_at: '2026-08-14T08:03:00+08:00',
  expires_at: null,
  message_count: 2,
  last_message_at: '2026-08-14T08:03:00+08:00',
  pinned_at: '2026-08-14T08:04:00+08:00',
  archived_at: null,
  context_binding: {
    factory_scope: 'huaxing',
    module_id: 'injection-scheduling' as const,
    route_name: 'injection-scheduling-v2' as const,
    path: '/modules/production/injection-scheduling' as const,
    context_version: 1,
    selected_entity_type: '',
    selected_entity_id: '',
    selected_entity_revision: null,
    updated_at: '2026-08-14T08:02:00+08:00',
  },
}

describe('AI Workbench V2 layout', () => {
  it('collapses the rail and inspector without removing the conversation canvas', async () => {
    const wrapper = mount(WorkbenchShell, {
      props: { railCollapsed: false, inspectorOpen: true, inspectorWidth: 360 },
      slots: {
        rail: '<div data-rail-content>rail</div>',
        default: '<main data-canvas>canvas</main>',
        inspector: '<div data-inspector-content>inspector</div>',
      },
    })

    expect(wrapper.get('[data-canvas]').text()).toBe('canvas')
    await wrapper.get('button[aria-label="折叠会话栏"]').trigger('click')
    await wrapper.get('button[aria-label="收起上下文检查器"]').trigger('click')
    expect(wrapper.emitted('toggleRail')).toHaveLength(1)
    expect(wrapper.emitted('toggleInspector')).toHaveLength(1)
  })

  it('provides keyboard-selectable inspector tabs with per-tab counts', async () => {
    const wrapper = mount(InspectorPanel, {
      props: {
        activeTab: 'sources',
        counts: { sources: 2, tasks: 1, artifacts: 0, actions: 0 },
      },
      slots: { sources: '<p>来源内容</p>' },
    })
    expect(wrapper.get('[role="tab"][aria-selected="true"]').text()).toContain('来源2')
    await wrapper.findAll('[role="tab"]')[1]!.trigger('click')
    expect(wrapper.emitted('tab')?.[0]).toEqual(['tasks'])
  })

  it('searches, groups and emits conversation management actions', async () => {
    const wrapper = mount(ConversationList, {
      props: {
        items: [conversation],
        activeId: conversation.id,
        loading: false,
        hasMore: false,
        runtimeStatuses: {
          [conversation.id]: {
            taskCount: 2,
            taskState: 'RUNNING',
            taskLabel: '任务运行中',
            actionCount: 1,
            actionState: 'PENDING',
            actionLabel: '待确认操作',
          },
        },
      },
    })
    expect(wrapper.text()).toContain('已固定')
    expect(wrapper.text()).toContain('注塑排产')
    expect(wrapper.get('[data-conversation-task-status]').text()).toContain('任务运行中 · 2')
    expect(wrapper.get('[data-conversation-action-status]').text()).toContain('待确认操作')
    await wrapper.get('input[type="search"]').setValue('不存在')
    expect(wrapper.text()).toContain('没有匹配会话')
    await wrapper.get('input[type="search"]').setValue('排产')
    await wrapper.get(`button[aria-label^="取消固定会话"]`).trigger('click')
    await wrapper.get(`button[aria-label^="归档会话"]`).trigger('click')
    expect(wrapper.emitted('pin')?.[0]).toEqual([conversation.id, false])
    expect(wrapper.emitted('archive')?.[0]).toEqual([conversation.id, true])
  })
})
