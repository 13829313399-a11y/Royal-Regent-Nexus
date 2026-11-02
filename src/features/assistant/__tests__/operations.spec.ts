import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AssistantOperations from '../AssistantOperations.vue'
import { assistantApi } from '../api'
import type { OperationalSummary } from '../types'
const report=(days=7):OperationalSummary=>({checked_at:'2026-10-26T00:00:00Z',window_days:days,runs:5,instrumented_runs:1,unmeasured_runs:4,active_runs:0,states:{completed:1},errors:{},usage_states:{unknown:1},counters:{business_completed:null,business_attempts:null,business_permission_errors:null,freshness_stale:null,freshness_unknown:null},timings:{elapsed_seconds:{samples:1,min:1,max:1,p50:null,p95:null}},recovery:{after_seq_attempts:2,client_confirmed_progress:1,missing_client_receipt:1},feedback:{total:1,categories:{factual:0,off_topic:0,sources:1,experience:0}},files_current_parse_states:{ready:1},definitions:{legacy:'未采集的旧记录不当作零。'},registered_source_ratio:{numerator:0,denominator:0,value:null},citation_binding_ratio:{numerator:1,denominator:2,value:.5},no_source_ratio:{numerator:1,denominator:1,value:1}})
const wrappers:ReturnType<typeof mount>[]=[]
const button=(w:ReturnType<typeof mount>,s:string)=>w.findAll('button').find(b=>b.text()===s)!
beforeEach(()=>{vi.restoreAllMocks();vi.spyOn(assistantApi,'operations').mockResolvedValue(report());vi.spyOn(assistantApi,'operationsTrace').mockResolvedValue({metadata_only:true,run:{id:'valid-run-123',state:'completed'}})})
afterEach(()=>{wrappers.forEach(w=>w.unmount());wrappers.length=0})
function panel(available=true){const w=mount(AssistantOperations,{props:{available}});wrappers.push(w);return w}
it('reports unknown samples and denominators without an answer confidence score',async()=>{
 const w=panel();await button(w,'读取运行统计').trigger('click');await flushPromises()
 expect(w.text()).toContain('已采集 1，未采集 4');expect(w.text()).toContain('尚未采集')
 expect(w.text()).toContain('缺确认 1 次');expect(w.text()).toContain('p95 样本不足或未测')
 expect(w.text()).not.toContain('答案可信度');expect(w.text()).toContain('北京时间')
 expect(w.text()).toContain('暂无可测分母');expect(w.text()).toContain('1 / 2；仅表示定位成功')
 expect(w.text()).toContain('1 / 1；包含正常普通聊天，未测不计入')
})
it('rejects a stale window result and keeps the selected interval authoritative',async()=>{
 let finish!:(v:OperationalSummary)=>void
 vi.mocked(assistantApi.operations).mockReturnValueOnce(new Promise(resolve=>{finish=resolve})).mockResolvedValueOnce(report(30))
 const w=panel();await button(w,'读取运行统计').trigger('click');await w.get('select').setValue('30');await flushPromises()
 finish(report(1));await flushPromises()
 expect(w.text()).toContain('最近 30 天');expect(w.text()).not.toContain('最近 1 天 ·')
})
it('only looks up a valid reported run ID and clears a late result after input changes',async()=>{
 let finish!:(v:Record<string,unknown>)=>void
 vi.mocked(assistantApi.operationsTrace).mockReturnValueOnce(new Promise(resolve=>{finish=resolve}))
 const w=panel();await w.get('input').setValue('..');await w.get('form').trigger('submit')
 expect(assistantApi.operationsTrace).not.toHaveBeenCalled();expect(w.text()).toContain('有效的运行编号')
 await w.get('input').setValue('valid-run-123');await w.get('form').trigger('submit')
 await w.get('input').setValue('other-run-456');finish({metadata_only:true,run:{id:'valid-run-123'}});await flushPromises()
 expect(w.find('[aria-label="脱敏运行诊断"]').exists()).toBe(false)
})
it('does not call unavailable endpoints on an old backend',async()=>{
 const w=panel(false);expect(w.text()).toContain('运行统计尚未准备完成')
 expect(assistantApi.operations).not.toHaveBeenCalled();expect(assistantApi.operationsTrace).not.toHaveBeenCalled()
})
