import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CustomerPriceArtifactPanel from '@/components/modules/sales/CustomerPriceArtifactPanel.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const artifactApi = vi.hoisted(() => ({
  list: vi.fn(),
  consume: vi.fn(),
  download: vi.fn(),
}))

vi.mock('@/api/customerPriceArtifact', () => ({
  customerPriceArtifactApi: artifactApi,
}))

const availableArtifact = {
  id: 'IQHAND-1',
  quote_id: 'quote-1',
  export_id: 'export-1',
  factory_id: 'huaxing',
  customer: '迪士尼',
  quote_no: 'IQ-HX-001',
  version_label: 'V2',
  release_revision: 3,
  status: 'available' as const,
  artifact_manifest: { product_name: '测试玩具' },
  file_name: 'IQ-HX-001_V2_内部报价.xlsx',
  content_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  size_bytes: 2048,
  sha256: 'sha-1',
  created_by: 'supervisor-2',
  created_by_name: '业务主管二',
  created_at: '2026-07-16T12:00:00+08:00',
  consumed_by: '',
  consumed_by_name: '',
  consumed_at: '',
  consumer_reference: '',
  revoked_at: '',
  revoke_reason: '',
}

function applyAuthorizedSession(factoryIds = ['huaxing']) {
  useAuthStore().applySession({
    id: 'sales-1',
    username: 'sales-1',
    display_name: '业务跟客',
    roles: ['车间业务跟客'],
    permissions: ['customer_price:import_internal_quote'],
    grants: factoryIds.map((factoryId) => ({
      role_id: `sales_customer_owner_${factoryId}`,
      role_code: 'sales_customer_owner',
      role_name: '车间业务跟客',
      factory_id: factoryId,
      department: 'sales-business',
      permissions: ['customer_price:import_internal_quote'],
      data_scope: 'department',
    })),
    factory_scopes: factoryIds,
    department_scopes: ['sales-business'],
    authz_mode: 'enforce',
    effective_access: factoryIds.map((factoryId) => ({
      permission_code: 'customer_price:import_internal_quote',
      factory_id: factoryId,
      department: 'sales-business',
      effect: 'allow',
      allowed: true,
      source_type: 'role',
      source_ids: [`sales_customer_owner_${factoryId}`],
    })),
    force_password_change: false,
  })
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve
  })
  return { promise, resolve }
}

describe('CustomerPriceArtifactPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    setActivePinia(createPinia())
    artifactApi.list.mockReset().mockResolvedValue([availableArtifact])
    artifactApi.consume.mockReset().mockResolvedValue({ ...availableArtifact, status: 'consumed' })
    artifactApi.download.mockReset().mockResolvedValue({
      blob: new Blob(['p4']),
      releaseStage: 'p4_final_approved',
      sha256: 'sha-1',
    })
    vi.stubGlobal('crypto', {})
    Object.defineProperty(window.URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:p4') })
    Object.defineProperty(window.URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('loads available P4 handoffs and passes status/customer filters to the API', async () => {
    applyAuthorizedSession()
    const wrapper = mount(CustomerPriceArtifactPanel, {
      props: {
        customers: [{ id: 'disney', name: '迪士尼' }],
        selectedCustomerId: 'disney',
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('内部报价交接池')
    expect(wrapper.text()).toContain('IQ-HX-001')
    expect(wrapper.text()).toContain('P4 · R3')
    expect(artifactApi.list).toHaveBeenCalledWith({
      factoryId: 'huaxing',
      status: 'available',
      customer: '',
      keyword: '',
    })

    await wrapper.get('[data-testid="artifact-status-revoked"]').trigger('click')
    expect(artifactApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'revoked' }))
  })

  it('preflights, consumes exactly once, downloads the controlled file and selects the matched customer', async () => {
    applyAuthorizedSession()
    artifactApi.list.mockResolvedValueOnce([availableArtifact]).mockResolvedValueOnce([])
    const prepareArtifact = vi.fn().mockResolvedValue(undefined)
    const wrapper = mount(CustomerPriceArtifactPanel, {
      props: {
        customers: [{ id: 'disney', name: '迪士尼' }],
        selectedCustomerId: 'buzzbee',
        prepareArtifact,
      },
    })
    await flushPromises()

    await wrapper.get('[data-testid="consume-artifact-IQHAND-1"]').trigger('click')
    await flushPromises()

    expect(artifactApi.consume).toHaveBeenCalledTimes(1)
    expect(artifactApi.consume).toHaveBeenCalledWith('IQHAND-1', 'customer-price-ui:IQHAND-1')
    expect(artifactApi.download).toHaveBeenCalledWith('IQHAND-1')
    expect(prepareArtifact).toHaveBeenCalledWith(availableArtifact, expect.any(Blob))
    expect(wrapper.emitted('selectCustomer')).toEqual([['disney']])
    expect(wrapper.emitted('artifactConsumed')).toEqual([['IQHAND-1']])
    expect(wrapper.text()).toContain('转换预览已生成')
  })

  it('keeps an authoritative duplicate-consume conflict visible after verified preflight', async () => {
    applyAuthorizedSession()
    artifactApi.list.mockResolvedValueOnce([availableArtifact]).mockResolvedValueOnce([])
    artifactApi.consume.mockRejectedValueOnce(new Error('内部报价 artifact 已被客价转换台导入'))
    const wrapper = mount(CustomerPriceArtifactPanel, {
      props: {
        customers: [{ id: 'disney', name: '迪士尼' }],
        selectedCustomerId: 'disney',
      },
    })
    await flushPromises()

    await wrapper.get('[data-testid="consume-artifact-IQHAND-1"]').trigger('click')
    await flushPromises()

    expect(artifactApi.consume).toHaveBeenCalledTimes(1)
    expect(artifactApi.download).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('接收或转换预检失败：内部报价 artifact 已被客价转换台导入')
  })

  it('does not consume an artifact when the customer mapping preflight fails', async () => {
    applyAuthorizedSession()
    const prepareArtifact = vi.fn().mockRejectedValue(new Error('缺少客户模板必需字段'))
    const wrapper = mount(CustomerPriceArtifactPanel, {
      props: {
        customers: [{ id: 'disney', name: '迪士尼' }],
        selectedCustomerId: 'disney',
        prepareArtifact,
      },
    })
    await flushPromises()

    await wrapper.get('[data-testid="consume-artifact-IQHAND-1"]').trigger('click')
    await flushPromises()

    expect(artifactApi.download).toHaveBeenCalledTimes(1)
    expect(artifactApi.consume).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('缺少客户模板必需字段')
  })

  it('restores a consumed handoff from its controlled source without consuming it again', async () => {
    applyAuthorizedSession()
    const consumedArtifact = {
      ...availableArtifact,
      status: 'consumed' as const,
      consumed_by: 'sales-1',
      consumed_by_name: '业务跟客',
      consumed_at: '2026-07-17T10:00:00+08:00',
      consumer_reference: 'customer-price-ui:IQHAND-1',
    }
    artifactApi.list.mockResolvedValue([consumedArtifact])
    const prepareArtifact = vi.fn().mockResolvedValue(undefined)
    const wrapper = mount(CustomerPriceArtifactPanel, {
      props: {
        customers: [{ id: 'disney', name: '迪士尼' }],
        selectedCustomerId: 'buzzbee',
        prepareArtifact,
      },
    })
    await flushPromises()

    await wrapper.get('[data-testid="restore-artifact-IQHAND-1"]').trigger('click')
    await flushPromises()

    expect(artifactApi.download).toHaveBeenCalledWith('IQHAND-1')
    expect(prepareArtifact).toHaveBeenCalledWith(consumedArtifact, expect.any(Blob))
    expect(artifactApi.consume).not.toHaveBeenCalled()
    expect(wrapper.emitted('selectCustomer')).toEqual([['disney']])
    expect(wrapper.text()).toContain('后端接收记录未重复生成')
  })

  it('ignores a late C-factory response after switching to D and clears the old list immediately', async () => {
    applyAuthorizedSession(['huakang-c', 'huakang-d'])
    const appStore = useAppStore()
    appStore.setActiveFactory('huakang-c')
    const cRequest = deferred<typeof availableArtifact[]>()
    const dRequest = deferred<typeof availableArtifact[]>()
    const cArtifact = {
      ...availableArtifact,
      id: 'IQHAND-C',
      factory_id: 'huakang-c',
      quote_no: 'IQ-HKC-001',
    }
    const dArtifact = {
      ...availableArtifact,
      id: 'IQHAND-D',
      factory_id: 'huakang-d',
      quote_no: 'IQ-HKD-001',
    }
    artifactApi.list.mockImplementation(({ factoryId }: { factoryId: string }) => (
      factoryId === 'huakang-c' ? cRequest.promise : dRequest.promise
    ))

    const wrapper = mount(CustomerPriceArtifactPanel, {
      props: {
        customers: [{ id: 'disney', name: '迪士尼' }],
        selectedCustomerId: 'disney',
      },
    })
    await Promise.resolve()

    appStore.setActiveFactory('huakang-d')
    await flushPromises()
    expect(wrapper.text()).not.toContain('IQ-HKC-001')

    dRequest.resolve([dArtifact])
    await flushPromises()
    expect(wrapper.text()).toContain('IQ-HKD-001')

    cRequest.resolve([cArtifact])
    await flushPromises()
    expect(wrapper.text()).toContain('IQ-HKD-001')
    expect(wrapper.text()).not.toContain('IQ-HKC-001')
  })
})
