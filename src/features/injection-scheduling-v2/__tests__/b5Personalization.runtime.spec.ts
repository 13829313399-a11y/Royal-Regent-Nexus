import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import type { AuthMeResponse } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import ColumnPresetMenu from '../components/ColumnPresetMenu.vue'
import {
  createSchedulingPreferencesKey,
  loadSchedulingPreferences,
  schedulingPreferencesVersion,
} from '../config/schedulingPreferences'
import { schedulingDefaultColumnOrder, schedulingPlannerColumnKeys } from '../composables/useSchedulingColumns'
import { schedulingFrozenWidth } from '../composables/useSchedulingColumns'
import { useInjectionSchedulingV2Store } from '../stores/useInjectionSchedulingV2Store'

function session(id: string): AuthMeResponse {
  return {
    id,
    username: id,
    display_name: id,
    roles: [],
    permissions: [],
    factory_scopes: [],
    department_scopes: [],
    grants: [],
    force_password_change: false,
  }
}

function personalizedStore(userId = 'planner-a') {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore(pinia).applySession(session(userId))
  return useInjectionSchedulingV2Store(pinia)
}

beforeEach(() => window.localStorage.clear())

describe('B5 personalization runtime', () => {
  it('uses a versioned user/factory key and ignores corrupt or obsolete documents', () => {
    const key = createSchedulingPreferencesKey('planner/a', 'huakang-b')
    expect(key).toBe('rr:injection-scheduling:layout:v1:planner%2Fa:huakang-b')

    window.localStorage.setItem(key, '{broken')
    expect(loadSchedulingPreferences(window.localStorage, 'planner/a', 'huakang-b')).toBeNull()
    window.localStorage.setItem(key, JSON.stringify({ version: schedulingPreferencesVersion + 1 }))
    expect(loadSchedulingPreferences(window.localStorage, 'planner/a', 'huakang-b')).toBeNull()
  })

  it('preserves an intentionally empty frozen set and trims oversized stored partitions', () => {
    const key = createSchedulingPreferencesKey('planner-a', 'huaxing')
    const base = {
      version: schedulingPreferencesVersion,
      preset: 'planner',
      density: 'comfortable',
      customVisibleColumns: {},
      columnWidths: {},
      columnOrder: schedulingDefaultColumnOrder,
      customPresets: [],
      activeCustomPresetId: null,
    }
    window.localStorage.setItem(key, JSON.stringify({ ...base, frozenKeys: [] }))
    expect(loadSchedulingPreferences(window.localStorage, 'planner-a', 'huaxing')?.frozenKeys).toEqual([])

    window.localStorage.setItem(key, JSON.stringify({ ...base, frozenKeys: schedulingPlannerColumnKeys }))
    const loaded = loadSchedulingPreferences(window.localStorage, 'planner-a', 'huaxing')!
    expect(schedulingFrozenWidth(loaded.frozenKeys, loaded.columnWidths)).toBeLessThanOrEqual(554)
  })

  it('persists density and column layout independently for each user and factory', () => {
    const store = personalizedStore()
    store.setDensity('compact')
    store.resizeColumn('remark', 260)
    store.toggleColumn('material')

    store.setFactory('huakang-b')
    expect(store.density).toBe('comfortable')
    expect(store.columnWidths).toEqual({})
    store.resizeColumn('remark', 190)

    store.setFactory('huaxing')
    expect(store.density).toBe('compact')
    expect(store.columnWidths.remark).toBe(260)
    expect(store.visibleColumns.some((column) => column.key === 'material')).toBe(true)

    const otherUser = personalizedStore('planner-b')
    expect(otherUser.density).toBe('comfortable')
    expect(otherUser.columnWidths).toEqual({})
  })

  it('keeps a custom frozen partition continuous and within the 1280 px budget', () => {
    const store = personalizedStore()
    expect(store.frozenColumnKeys).toEqual(['status', 'machineCode', 'moldNo', 'productName'])
    expect(store.frozenWidth).toBe(554)
    expect(store.frozenToggleDecision('sequence')).toMatchObject({ allowed: false, reason: expect.stringContaining('冻结宽度') })

    store.toggleFrozenColumn('productName')
    store.toggleFrozenColumn('sequence')
    expect(store.frozenColumnKeys).toEqual(['status', 'machineCode', 'moldNo', 'sequence'])
    expect(store.visibleColumns.slice(0, 4).map((column) => column.key)).toEqual(store.frozenColumnKeys)
    expect(store.visibleColumns.slice(4).every((column) => !column.frozen)).toBe(true)
    expect(store.frozenWidth).toBeLessThanOrEqual(554)
  })

  it('saves, applies and removes a named custom preset without changing domain data', () => {
    const store = personalizedStore()
    store.setDensity('compact')
    store.toggleColumn('material')
    store.toggleFrozenColumn('productName')
    const custom = store.saveCustomPreset('晨会视图')

    expect(custom?.name).toBe('晨会视图')
    expect(store.customPresets).toHaveLength(1)
    store.setPreset('full')
    expect(store.visibleColumns).toHaveLength(50)

    store.applyCustomPreset(custom!.id)
    expect(store.activeCustomPresetId).toBe(custom!.id)
    expect(store.density).toBe('compact')
    expect(store.visibleColumns.some((column) => column.key === 'material')).toBe(true)
    expect(store.frozenColumnKeys).not.toContain('productName')

    store.deleteCustomPreset(custom!.id)
    expect(store.customPresets).toHaveLength(0)
    expect(store.activeCustomPresetId).toBeNull()
  })

  it('exposes accessible density, freeze and custom-preset controls with local-only copy', async () => {
    const wrapper = mount(ColumnPresetMenu, {
      props: {
        open: true,
        preset: 'planner',
        visibleKeys: [...schedulingPlannerColumnKeys],
        widths: {},
        columnOrder: schedulingDefaultColumnOrder,
        density: 'comfortable',
        frozenKeys: ['status', 'machineCode', 'moldNo', 'productName'],
        customPresets: [],
        activeCustomPresetId: null,
      },
    })

    expect(wrapper.text()).toContain('仅保存在当前浏览器，不跨设备同步')
    await wrapper.get('button[aria-label="使用紧凑密度"]').trigger('click')
    expect(wrapper.emitted('density')?.[0]).toEqual(['compact'])
    await wrapper.get('button[aria-label="取消冻结状态"]').trigger('click')
    expect(wrapper.emitted('toggleFreeze')?.[0]).toEqual(['status'])
    await wrapper.get<HTMLInputElement>('[data-testid="custom-preset-name"]').setValue('交接班')
    await wrapper.get('button[aria-label="保存当前布局为自定义视图"]').trigger('click')
    expect(wrapper.emitted('saveCustomPreset')?.[0]).toEqual(['交接班'])
  })
})
