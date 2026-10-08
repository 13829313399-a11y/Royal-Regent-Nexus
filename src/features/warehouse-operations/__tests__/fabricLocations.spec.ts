import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import Locations from '../FabricLocationSettings.vue'
import Master from '../FabricMasterWorkspace.vue'
import type { MasterRecord } from '@/api/fabricMaster'
const api = vi.hoisted(() => ({ list: vi.fn(), candidates: vi.fn(), save: vi.fn(), history: vi.fn(), previewLocations: vi.fn(), applyLocations: vi.fn(), renameWarehouse: vi.fn(), previewLocationFile: vi.fn(), locationTemplate: vi.fn() }))
vi.mock('@/api/fabricMaster', () => ({ fabricMasterApi: api }))
let wrapper: VueWrapper | undefined
const body = () => new DOMWrapper(document.body)
const click = async (name: string) => { await body().findAll('button').find(row => row.text() === name)!.trigger('click'); await flushPromises() }
const records: MasterRecord[] = ['A01','A02','B01'].map((code,index) => ({ id: code, code, name: code, kind: 'LOCATION', status: index === 1 ? 'INACTIVE' : 'ACTIVE', revision: index + 1, updated_at: '2026-10-07', data: { warehouse: index === 2 ? '辅料仓' : '布料仓' } }))
async function router() { const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] }); await router.push('/'); await router.isReady(); return router }
async function open() { wrapper = mount(Locations,{ props: { records, warehouseTokens:{'布料仓':'GROUP'}, canManage:true, busy:false, search:'', status:'ALL' }, attachTo:document.body, global:{ plugins:[await router()] } }); await flushPromises() }
beforeEach(() => { vi.clearAllMocks(); api.list.mockResolvedValue({ items: [], can_manage:true }); api.candidates.mockResolvedValue([]); api.previewLocations.mockResolvedValue({ items:[{warehouse:'布料仓',code:'A03',action:'NEW',status:'ACTIVE'}], errors:[],new:1,unchanged:0,preview_token:'TOKEN',stock_posted:false }) })
afterEach(() => { wrapper?.unmount(); wrapper=undefined; document.body.innerHTML=''; vi.restoreAllMocks() })
describe('carton-style fabric master setup', () => {
  it('groups clickable bins by warehouse and retains full rename revisions when filtered', async () => {
    await open()
    expect(wrapper!.findAll('.fabric-warehouse-group')).toHaveLength(2)
    expect(wrapper!.find('[data-status=INACTIVE]').text()).toContain('停用')
    await wrapper!.setProps({search:'A01'})
    expect(wrapper!.findAll('.fabric-location-chip')).toHaveLength(1)
    await wrapper!.get('[aria-label="修改仓库 布料仓"]').trigger('click'); await flushPromises()
    await body().get('[aria-label="仓库名称"]').setValue('布料新仓')
    api.renameWarehouse.mockResolvedValue({updated:2})
    await body().get('form.fabric-master-form').trigger('submit'); await flushPromises()
    expect(api.renameWarehouse).toHaveBeenCalledWith(expect.objectContaining({warehouse:'布料仓',name:'布料新仓',expected_group_token:'GROUP'}))
    expect(wrapper!.emitted('refresh')).toHaveLength(1)
  })
  it('previews range first and freezes one payload for retry after an unknown outcome', async () => {
    await open(); await wrapper!.get('[aria-label="添加 布料仓 仓位"]').trigger('click'); await flushPromises()
    expect(body().get('[aria-label="仓库名称"]').attributes('readonly')).toBeDefined()
    await body().get('[aria-label="仓位或范围"]').setValue('A03-A05')
    await body().get('form').trigger('submit'); await flushPromises()
    expect(api.applyLocations).not.toHaveBeenCalled()
    expect(api.previewLocations).toHaveBeenCalledWith([{warehouse:'布料仓',bins:'A03-A05'}])
    api.applyLocations.mockRejectedValueOnce({isAxiosError:true,message:'network'}).mockResolvedValueOnce({new:3})
    await click('确认保存')
    const payload=JSON.parse(JSON.stringify(api.applyLocations.mock.calls[0]![0]))
    expect(body().get('fieldset').attributes('disabled')).toBeDefined()
    await click('重试保存')
    expect(api.applyLocations.mock.calls[1]![0]).toEqual(payload)
  })
  it('invalidates stale previews when expression changes and disables conflict saving', async () => {
    await open(); await wrapper!.get('[aria-label="添加 布料仓 仓位"]').trigger('click'); await flushPromises()
    await body().get('[aria-label="仓位或范围"]').setValue('C01')
    await body().get('form').trigger('submit'); await flushPromises()
    expect(body().text()).toContain('确认保存')
    await body().get('[aria-label="仓位或范围"]').setValue('C02')
    expect(body().findAll('button').some(row=>row.text()==='确认保存')).toBe(false)
    api.previewLocations.mockResolvedValueOnce({items:[],errors:['跨仓冲突'],new:1,unchanged:0,preview_token:'OTHER'})
    await body().get('form').trigger('submit'); await flushPromises()
    expect(body().findAll('button').find(row=>row.text()==='确认保存')!.attributes('disabled')).toBeDefined()
  })
  it('protects dirty dismissal and hides mutation controls for read-only users', async () => {
    await open(); await click('添加仓库')
    await body().get('[aria-label="仓库名称"]').setValue('一仓')
    const confirm=vi.spyOn(window,'confirm').mockReturnValue(false)
    await click('关闭'); expect(confirm).toHaveBeenCalled(); expect(body().find('[role=dialog]').exists()).toBe(true)
    wrapper!.unmount(); wrapper=undefined; document.body.innerHTML=''
    wrapper=mount(Locations,{props:{records,warehouseTokens:{'布料仓':'GROUP'},canManage:false,busy:false,search:'',status:'ALL'},global:{plugins:[await router()]}})
    expect(wrapper.findAll('button').some(row=>row.text().includes('添加'))).toBe(false)
    expect(wrapper.get('[aria-label="修改仓位 布料仓 A01"]').attributes('disabled')).toBeDefined()
  })
  it('keeps standard units short and exposes conversion evidence only for conversions', async () => {
    wrapper=mount(Master,{props:{view:'units'},attachTo:document.body,global:{plugins:[await router()]}}); await flushPromises()
    await click('新增资料')
    expect(body().find('[aria-label="换算依据"]').exists()).toBe(false)
    await click('关闭'); await click('新增物料换算')
    expect(body().get('[aria-label="换算依据"]').attributes('required')).toBeDefined()
    expect(body().get('[aria-label="适用物料编码"]').element.tagName).toBe('SELECT')
    await body().get('form.fabric-master-form').trigger('submit'); await flushPromises()
    expect(api.save).not.toHaveBeenCalled()
    expect(body().text()).toContain('换算资料须补齐')
  })
})
