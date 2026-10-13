import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { reactive, ref } from 'vue'
import { parseDate } from '@internationalized/date'
import DateRangeFilter from '@/components/DateRangeFilter.vue'
import Workspace from '../FabricInventorySetup.vue'
import { inventorySearchKey } from '../inventorySearch'
import type { CountDocument } from '@/api/fabricInventorySetup'

const api=vi.hoisted(()=>({workspace:vi.fn(),template:vi.fn(),preview:vi.fn(),apply:vi.fn(),create:vi.fn(),act:vi.fn()}))
const warehouseApi=vi.hoisted(()=>({workspace:vi.fn()}))
vi.mock('@/api/fabricInventorySetup',()=>({fabricInventorySetupApi:api}))
vi.mock('@/api/warehouseOperations',()=>({warehouseOperationsApi:warehouseApi}))
const session=reactive({currentUser:{id:'keeper'},authorizationVersion:0})
vi.mock('@/stores/auth',()=>({useAuthStore:()=>session}))
const batch={id:'B1',item_code:'001',item_name:'白布',unit:'码',location:'A/A01',location_id:'A01',location_verified:true,warehouse_name:'A',lot:'0001',roll_no:'01',quantity:'10.000001',quality_status:'PENDING_INSPECTION',available_quantity:'10.000001',material_category:'FABRIC',process_state:'',source_no:'OLD',source_document:'O',received_on:'2026-10-01',counterparty:'纺织厂',production_no:''} as const
const count:CountDocument={id:'COUNT1',revision:1,status:'DRAFT',actor_name:'仓管',business_date:'2026-10-13',reason:'实物盘点',lines:[{batch_id:'B1',snapshot:{...batch},actual:'',reason:''}],events:[]}
const preview={filename:'opening.xlsx',token:'t'.repeat(64),new_count:1,skip_count:0,error_count:0,totals:{码:'10.000001'},rows:[{row_number:2,source_line:'1',item_code:'001',item_name:'白布',location:'A/A01',lot:'0001',roll_no:'01',quantity:'10.000001',unit:'码',action:'NEW',errors:[]}]}
let wrapper:VueWrapper
const search=ref('')
beforeEach(()=>{vi.resetAllMocks();search.value='';session.authorizationVersion=0;vi.spyOn(window,'confirm').mockReturnValue(true);api.workspace.mockResolvedValue({openings:[],counts:[structuredClone(count)],permissions:{read:true,operate:true,correct:true}});warehouseApi.workspace.mockResolvedValue({stock:[{...batch}],locations:[{id:'A01',warehouse:'A',code:'A01',label:'A/A01',status:'ACTIVE'}]});api.preview.mockResolvedValue(structuredClone(preview))})
afterEach(()=>{wrapper?.unmount();vi.restoreAllMocks()})
async function open(mode:'opening'|'stocktake'){wrapper=mount(Workspace,{props:{mode},global:{provide:{[inventorySearchKey as symbol]:{search,active:ref(true),submitted:ref(0)}}}});await flushPromises()}
function button(name:string){return wrapper.findAll('button').find(item=>item.text()===name)!}
async function inspect(){await wrapper.get('[aria-label="原始清单编号"]').setValue('OLD-1');const input=wrapper.get('[aria-label="期初库存文件"]');Object.defineProperty(input.element,'files',{value:[new File(['sample'],'opening.xlsx')],configurable:true});await input.trigger('change');await button('预览导入').trigger('click');await flushPromises()}

describe('fabric opening and stocktaking',()=>{
  it('refreshes an untouched count to the latest cancelled version',async()=>{
    await open('stocktake');await button('继续盘点').trigger('click')
    api.workspace.mockResolvedValue({openings:[],counts:[{...structuredClone(count),revision:2,status:'CANCELLED'}],permissions:{read:true,operate:true,correct:true}})
    await button('刷新').trigger('click');await flushPromises()
    expect(wrapper.get('.setup-count-heading').text()).toContain('已取消')
    expect(button('保存实盘草稿')).toBeUndefined()
    expect(api.act).not.toHaveBeenCalled()
  })
  it('preserves local actuals on a version conflict and requires an explicit reload before saving',async()=>{
    await open('stocktake');await button('继续盘点').trigger('click')
    await wrapper.get('[aria-label="实盘数量 1"]').setValue('9')
    const latest={...structuredClone(count),revision:2,lines:[{...structuredClone(count.lines[0]!),actual:'8',reason:'另一人已核对'}]}
    api.act.mockRejectedValueOnce({isAxiosError:true,response:{status:409,data:{detail:'盘点单已变化'}}})
    api.workspace.mockResolvedValue({openings:[],counts:[latest],permissions:{read:true,operate:true,correct:true}})
    await button('保存实盘草稿').trigger('click');await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[aria-label="实盘数量 1"]').element.value).toBe('9')
    expect(wrapper.text()).toContain('盘点单已被其他操作更新')
    expect(button('保存实盘草稿').attributes('disabled')).toBeDefined()
    vi.mocked(window.confirm).mockReturnValueOnce(false)
    await button('打开最新盘点单').trigger('click')
    expect(wrapper.get<HTMLInputElement>('[aria-label="实盘数量 1"]').element.value).toBe('9')
    await button('打开最新盘点单').trigger('click');await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[aria-label="实盘数量 1"]').element.value).toBe('8')
    api.act.mockResolvedValue({...latest,revision:3})
    await button('保存实盘草稿').trigger('click');await flushPromises()
    expect(api.act).toHaveBeenLastCalledWith('COUNT1',expect.objectContaining({expected_revision:2,lines:[{batch_id:'B1',actual:'8',reason:'另一人已核对'}]}))
  })
  it('refreshes permissions for the same account without retaining old posting controls',async()=>{
    await open('stocktake');await button('继续盘点').trigger('click')
    await wrapper.get('[aria-label="实盘数量 1"]').setValue('9')
    api.workspace.mockResolvedValue({openings:[],counts:[structuredClone(count)],permissions:{read:true,operate:false,correct:false}})
    session.authorizationVersion++;await flushPromises()
    expect(wrapper.get('[aria-label="实盘数量 1"]').attributes('disabled')).toBeDefined()
    expect(button('确认盘点并入账').attributes('disabled')).toBeDefined()
    expect(button('保存实盘草稿').attributes('disabled')).toBeDefined()
    expect(api.act).not.toHaveBeenCalled()
  })
  it('keeps the original in-flight request available for replay after authorization refresh',async()=>{
    let resolve!:(value:unknown)=>void
    api.act.mockImplementationOnce(()=>new Promise(r=>{resolve=r}))
    await open('stocktake');await button('继续盘点').trigger('click')
    await wrapper.get('[aria-label="实盘数量 1"]').setValue('9')
    await button('保存实盘草稿').trigger('click');await flushPromises()
    const original=api.act.mock.calls[0]![1]
    session.authorizationVersion++;await flushPromises()
    const saved={...structuredClone(count),revision:2,lines:[{...structuredClone(count.lines[0]!),actual:'9'}]}
    resolve(saved);await flushPromises()
    expect(button('用原请求重试')).toBeDefined()
    api.act.mockResolvedValue(saved)
    await button('用原请求重试').trigger('click');await flushPromises()
    expect(api.act.mock.calls[1]![1]).toBe(original)
    expect(wrapper.text()).not.toContain('用原请求重试')
  })
  it('filters count history by an inclusive range and clears it without changing stock selection or posting',async()=>{
    api.workspace.mockResolvedValue({openings:[],counts:[
      {...structuredClone(count),id:'BEFORE',business_date:'2026-10-12'},
      structuredClone(count),
      {...structuredClone(count),id:'AFTER',business_date:'2026-10-14'},
    ],permissions:{read:true,operate:true,correct:true}})
    await open('stocktake')
    await wrapper.get('[aria-label="选择本页全部批次"]').setValue(true)
    wrapper.getComponent(DateRangeFilter).vm.$emit('update:modelValue',{start:parseDate('2026-10-13'),end:parseDate('2026-10-13')});await flushPromises()
    expect(wrapper.findAll('.setup-history tbody tr')).toHaveLength(1)
    expect(wrapper.get('.setup-history tbody').text()).toContain('COUNT1')
    expect(wrapper.text()).toContain('已选 1 个批次')
    wrapper.getComponent(DateRangeFilter).vm.$emit('update:modelValue',{start:undefined,end:undefined});await flushPromises()
    expect(wrapper.findAll('.setup-history tbody tr')).toHaveLength(3)
    expect(api.act).not.toHaveBeenCalled()
    expect(api.create).not.toHaveBeenCalled()
  })
  it('marks only changed batches on refresh without discarding typed actuals, and requires recounting before post',async()=>{
    await open('stocktake');await button('继续盘点').trigger('click')
    await wrapper.get('[aria-label="实盘数量 1"]').setValue('9')
    await wrapper.get('[aria-label="差异原因 1"]').setValue('现场少料')
    await wrapper.get('.confirm-count input').setValue(true)
    api.workspace.mockResolvedValue({openings:[],counts:[{...structuredClone(count),stale:true,changed_batch_ids:['B1']}],permissions:{read:true,operate:true,correct:true}})
    await button('刷新').trigger('click');await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[aria-label="实盘数量 1"]').element.value).toBe('9')
    expect(wrapper.text()).toContain('所选范围内 1 个批次的记录已变化')
    expect(wrapper.text()).toContain('盘点期间有变动')
    expect(button('确认盘点并入账').attributes('disabled')).toBeDefined()
    expect(api.act).not.toHaveBeenCalled()
    const refreshed={...structuredClone(count),revision:2,stale:false,changed_batch_ids:[]}
    api.act.mockResolvedValue(refreshed)
    api.workspace.mockResolvedValue({openings:[],counts:[refreshed],permissions:{read:true,operate:true,correct:true}})
    await button('更新账面并重盘').trigger('click');await flushPromises()
    expect(api.act).toHaveBeenCalledWith('COUNT1',expect.objectContaining({action:'REFRESH',expected_revision:1}))
    expect(wrapper.get<HTMLInputElement>('[aria-label="实盘数量 1"]').element.value).toBe('')
    expect(wrapper.text()).not.toContain('盘点期间有变动')
    expect(button('确认盘点并入账').attributes('disabled')).toBeDefined()
  })
  it('allows a correction-only reviewer to post saved counts without editing them',async()=>{
    const saved={...structuredClone(count),lines:[{...structuredClone(count.lines[0]!),actual:'9',reason:'已核实差额'}]}
    api.workspace.mockResolvedValue({openings:[],counts:[saved],permissions:{read:true,operate:false,correct:true}})
    api.act.mockResolvedValue({...saved,status:'POSTED',revision:2})
    await open('stocktake');await button('继续盘点').trigger('click')
    expect(wrapper.get('[aria-label="实盘数量 1"]').attributes('disabled')).toBeDefined()
    await wrapper.get('.confirm-count input').setValue(true)
    expect(button('确认盘点并入账').attributes('disabled')).toBeUndefined()
    await button('确认盘点并入账').trigger('click');await flushPromises()
    expect(api.act).toHaveBeenCalledWith('COUNT1',expect.objectContaining({action:'POST',lines:[{batch_id:'B1',actual:'9',reason:'已核实差额'}]}))
  })
  it('requires a successful preview and acknowledgement before importing, and resets preview when source changes',async()=>{await open('opening');await inspect();expect(button('确认导入期初库存').attributes('disabled')).toBeDefined();await wrapper.get('.setup-footer input[type=checkbox]').setValue(true);expect(button('确认导入期初库存').attributes('disabled')).toBeUndefined();await wrapper.get('[aria-label="原始清单编号"]').setValue('OLD-2');expect(wrapper.find('.setup-preview').exists()).toBe(false);expect(api.apply).not.toHaveBeenCalled()})
  it('blocks an import with row errors and preserves leading-zero identity in preview',async()=>{api.preview.mockResolvedValue({...preview,error_count:1,rows:[{...preview.rows[0],action:'ERROR',errors:['仓位无效']}]});await open('opening');await inspect();expect(wrapper.text()).toContain('0001 / 01');expect(wrapper.text()).toContain('仓位无效');expect(button('确认导入期初库存').attributes('disabled')).toBeDefined()})
  it('locks an unknown import outcome and retries the identical form and request ID',async()=>{api.apply.mockRejectedValueOnce({isAxiosError:true,response:{status:408}}).mockResolvedValueOnce({id:'O',source_no:'OLD-1',posted_count:1,skipped_count:0,rows:[]});await open('opening');await inspect();await wrapper.get('.setup-footer input[type=checkbox]').setValue(true);await button('确认导入期初库存').trigger('click');await flushPromises();const original=api.apply.mock.calls[0]![0] as FormData;expect(original.get('request_id')).toBeTruthy();expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined();await button('用原请求重试').trigger('click');await flushPromises();expect(api.apply.mock.calls[1]![0]).toBe(original);expect(wrapper.text()).toContain('期初导入完成')})
  it('opens a reactive saved draft, leaves uncounted blank, and posts explicit zero with a reason',async()=>{api.act.mockImplementation(async(_id,body)=>({...structuredClone(count),status:'POSTED',revision:2,lines:[{...structuredClone(count.lines[0]),actual:body.lines[0].actual,reason:body.lines[0].reason}]}));await open('stocktake');await button('继续盘点').trigger('click');expect(wrapper.get<HTMLInputElement>('[aria-label="实盘数量 1"]').element.value).toBe('');await wrapper.get('[aria-label="实盘数量 1"]').setValue('0');await wrapper.get('[aria-label="差异原因 1"]').setValue('实物已用完');expect(wrapper.text()).toContain('-10.000001');await wrapper.get('.confirm-count input').setValue(true);await button('确认盘点并入账').trigger('click');await flushPromises();expect(api.act).toHaveBeenCalledWith('COUNT1',expect.objectContaining({action:'POST',confirmed:true,lines:[{batch_id:'B1',actual:'0',reason:'实物已用完'}]}));expect(wrapper.text()).toContain('盘点已入账')})
  it('clears selection on header filter changes and does not duplicate a search field',async()=>{await open('stocktake');await wrapper.get('[aria-label="选择本页全部批次"]').setValue(true);expect(wrapper.text()).toContain('已选 1 个批次');search.value='找不到';await flushPromises();expect(wrapper.text()).toContain('已选 0 个批次');expect(wrapper.find('input[type=search]').exists()).toBe(false);expect(api.create).not.toHaveBeenCalled()})
  it('keeps read-only users from drafting or posting inventory changes',async()=>{api.workspace.mockResolvedValue({openings:[],counts:[],permissions:{read:true,operate:false,correct:false}});await open('stocktake');expect(button('生成盘点单').attributes('disabled')).toBeDefined();await wrapper.setProps({mode:'opening'});await flushPromises();expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined();expect(wrapper.text()).toContain('库存更正权限')})
})
