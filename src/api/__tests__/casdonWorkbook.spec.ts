import { describe,it,expect,vi } from 'vitest'
import { casdonWorkbookApi } from '../casdonWorkbook'
const post=vi.hoisted(()=>vi.fn())
vi.mock('@/lib/http',()=>({http:{post}}))
describe('Casdon workbook API',()=>{
  it('sends fingerprint and selected row ids with current factory',async()=>{
    post.mockResolvedValue({data:new Blob(['out']),headers:{'content-disposition':"attachment; filename*=UTF-8''%E6%8E%92%E6%9C%9F.xlsx",'x-export-audit-id':'AUD'}})
    const result=await casdonWorkbookApi.export('huadeng',new File(['x'],'source.xlsx'),'sha','restore',['14'],'核对恢复')
    const [url,data,config]=post.mock.calls.at(-1)!
    expect(url).toContain('factory_id=huadeng');expect(data.get('fingerprint')).toBe('sha')
    expect(data.get('selections')).toBe('["14"]');expect(data.get('confirmed')).toBe('true')
    expect(config.responseType).toBe('blob');expect(result.name).toBe('排期.xlsx');expect(result.auditId).toBe('AUD')
  })
})
