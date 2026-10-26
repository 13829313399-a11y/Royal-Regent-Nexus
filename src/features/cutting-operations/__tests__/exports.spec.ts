import { afterEach,beforeEach,describe,expect,it,vi } from 'vitest'
import { mount,flushPromises,type VueWrapper } from '@vue/test-utils'
import CuttingReportExport from '../CuttingReportExport.vue'
import { cuttingApi,type Access } from '../api'
import { exportApi,saveReport,type ReportSelection,type ReportPreview } from '../exportApi'
import { advanceAuthenticationGeneration,announceSessionBoundary } from '@/lib/authenticationGeneration'

vi.mock('../api',()=>({cuttingApi:{access:vi.fn()},errorMessage:()=> '依据变化，请重新预览'}))
vi.mock('../exportApi',()=>({exportApi:{preview:vi.fn(),download:vi.fn()},saveReport:vi.fn()}))
const access:Access={enabled:true,schema_ready:true,permissions:['read','cost_read','settlement_read','payment_read']}
const selection:ReportSelection={kind:'period',month:'2026-09',event_id:'locked-1'}
const info:ReportPreview={token:'pinned-token',title:'内部月结冻结表',metadata:[['使用状态','历史失效冻结版本'],['版本',3]],sheets:[{name:'费用汇总',rows:2}]}
let wrapper:VueWrapper
beforeEach(()=>{vi.clearAllMocks();vi.mocked(cuttingApi.access).mockResolvedValue(access);vi.mocked(exportApi.preview).mockResolvedValue(info);vi.mocked(exportApi.download).mockResolvedValue(new Blob(['xlsx']))})
afterEach(()=>{wrapper?.unmount();vi.useRealTimers()})
async function open(props={}){wrapper=mount(CuttingReportExport,{props:{selection,access,...props}});await flushPromises()}
async function click(label:string){await wrapper.findAll('button').find(b=>b.text()===label)!.trigger('click');await flushPromises()}
describe('P4e controlled exports',()=>{
  it('shows elapsed preview waiting, cancels it and ignores the late response',async()=>{
    vi.useFakeTimers()
    let resolve!:(value:ReportPreview)=>void
    vi.mocked(exportApi.preview).mockImplementationOnce(()=>new Promise(r=>{resolve=r}))
    await open();await click('预览 Excel 导出');await vi.advanceTimersByTimeAsync(2100)
    expect(wrapper.text()).toContain('正在核对报表内容，已等待 2 秒')
    const signal=vi.mocked(exportApi.preview).mock.calls[0]![1]!
    await click('取消本次等待');expect(signal.aborted).toBe(true)
    expect(wrapper.text()).toContain('后台生成可能仍会短暂运行')
    expect(vi.getTimerCount()).toBe(0)
    await click('预览 Excel 导出');expect(wrapper.text()).toContain('确认下载 Excel')
    resolve({...info,title:'迟到的旧报表'});await flushPromises()
    expect(wrapper.text()).not.toContain('迟到的旧报表');expect(saveReport).not.toHaveBeenCalled()
  })
  it('cancels download waiting without saving a late binary and releases timers on selection changes',async()=>{
    vi.useFakeTimers()
    let resolve!:(blob:Blob)=>void
    vi.mocked(exportApi.download).mockImplementation(()=>new Promise(r=>{resolve=r}))
    await open();await click('预览 Excel 导出');await click('确认下载 Excel')
    await vi.advanceTimersByTimeAsync(3200)
    expect(wrapper.text()).toContain('正在等待完整报表文件，已等待 3 秒')
    await click('取消本次等待');resolve(new Blob(['late']));await flushPromises()
    expect(saveReport).not.toHaveBeenCalled();expect(wrapper.text()).not.toContain('确认下载 Excel')
    expect(vi.getTimerCount()).toBe(0)
    vi.mocked(exportApi.preview).mockImplementation(()=>new Promise(()=>{}))
    await click('预览 Excel 导出');await wrapper.setProps({selection:{...selection,event_id:'another'}})
    expect(vi.getTimerCount()).toBe(0)
  })
  it('distinguishes live payment balances from frozen versions before and after download',async()=>{
    await open({selection:{kind:'payments',month:'2026-09'}});await click('预览 Excel 导出')
    expect(wrapper.text()).toContain('不是所选月份的历史月末冻结余额')
    await click('确认下载 Excel')
    expect(wrapper.text()).toContain('付款报表已生成并发起下载')
    expect(wrapper.text()).toContain('本次导出时的当前全期余额')
    expect(wrapper.text()).not.toContain('金额按所选冻结版本')
  })
  it('shows automatic volumes and downloads the full package after preview',async()=>{
    vi.mocked(exportApi.preview).mockResolvedValue({...info,delivery:{format:'zip',volumes:3,manifest:[]}})
    const blob=new Blob(['package'],{type:'application/zip'})
    vi.mocked(exportApi.download).mockResolvedValue(blob)
    await open();await click('预览 Excel 导出')
    expect(wrapper.text()).toContain('共 3 卷');expect(wrapper.text()).toContain('保留全部 Excel 文件及清单')
    await click('确认下载压缩包')
    expect(saveReport).toHaveBeenCalledWith(blob,selection,'pinned-token')
  })
  it('requires a preview and sends the exact selected event and token',async()=>{await open();expect(wrapper.text()).not.toContain('确认下载');await click('预览 Excel 导出');expect(wrapper.text()).toContain('历史失效冻结版本');expect(wrapper.text()).toContain('费用汇总 2 行');await click('确认下载 Excel');expect(exportApi.download).toHaveBeenCalledWith(selection,'pinned-token',expect.any(AbortSignal));expect(saveReport).toHaveBeenCalledWith(expect.any(Blob),selection,'pinned-token');expect(cuttingApi.access).toHaveBeenCalledTimes(3)})
  it.each(['period','settlement','payments'] as const)('enforces the separate %s permission',async kind=>{await open({selection:{kind,month:'2026-09'},access:{...access,permissions:['read']}});expect(wrapper.find('button').exists()).toBe(false);expect(exportApi.preview).not.toHaveBeenCalled()})
  it('clears preview when month, version or parent operation changes',async()=>{await open();await click('预览 Excel 导出');await wrapper.setProps({selection:{...selection,event_id:'locked-2'}});expect(wrapper.text()).not.toContain('确认下载');await click('预览 Excel 导出');await wrapper.setProps({disabled:true});expect(wrapper.text()).not.toContain('确认下载');expect(wrapper.get('button').attributes('disabled')).toBeDefined()})
  it('blocks a late binary after revocation and never restores it',async()=>{let resolve!:(b:Blob)=>void;vi.mocked(exportApi.download).mockImplementation(()=>new Promise(r=>{resolve=r}));await open();await click('预览 Excel 导出');await click('确认下载 Excel');await wrapper.setProps({access:{...access,permissions:['read']}});resolve(new Blob(['secret']));await flushPromises();expect(saveReport).not.toHaveBeenCalled();await wrapper.setProps({access});expect(wrapper.text()).not.toContain('确认下载')})
  it('checks access after the binary response and refuses revoked downloads',async()=>{await open();await click('预览 Excel 导出');vi.mocked(cuttingApi.access).mockResolvedValueOnce(access).mockResolvedValueOnce({...access,permissions:['read']});await click('确认下载 Excel');expect(saveReport).not.toHaveBeenCalled();expect(wrapper.text()).toContain('文件未下载')})
  it('drops stale previews after a session boundary',async()=>{let resolve!:(p:ReportPreview)=>void;vi.mocked(exportApi.preview).mockImplementation(()=>new Promise(r=>{resolve=r}));await open();await click('预览 Excel 导出');advanceAuthenticationGeneration();announceSessionBoundary();resolve(info);await flushPromises();expect(wrapper.text()).not.toContain('确认下载');expect(saveReport).not.toHaveBeenCalled()})
  it('invalidates a failed version token without automatic download retries',async()=>{await open();await click('预览 Excel 导出');vi.mocked(exportApi.download).mockRejectedValue({response:{status:409}});await click('确认下载 Excel');expect(wrapper.text()).toContain('重新预览');expect(wrapper.text()).not.toContain('确认下载');expect(exportApi.download).toHaveBeenCalledTimes(1);expect(saveReport).not.toHaveBeenCalled()})
})
