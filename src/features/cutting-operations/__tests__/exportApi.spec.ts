import { afterEach, describe, expect, it, vi } from 'vitest'
import { exportApi, saveReport, type ReportSelection } from '../exportApi'
import { http } from '@/lib/http'

vi.mock('@/lib/http',()=>({http:{post:vi.fn()}}))
const selection:ReportSelection={kind:'payments',month:'2026-10'}
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers()})
describe('report download file contract',()=>{
  it.each([['application/zip','zip'],['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','xlsx']])('uses %s download extension', (type,extension)=>{
    vi.useFakeTimers()
    const create=vi.fn(()=> 'blob:test'),revoke=vi.fn()
    vi.stubGlobal('URL',{createObjectURL:create,revokeObjectURL:revoke})
    let filename=''
    vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(function(this:HTMLAnchorElement){filename=this.download})
    saveReport(new Blob(['bytes'],{type}),selection,'123456789012abcdef')
    expect(filename).toBe(`cutting-payments-2026-10-123456789012.${extension}`)
    expect(document.querySelector('a')).toBeNull()
    vi.runAllTimers();expect(revoke).toHaveBeenCalledWith('blob:test')
  })
  it('retains structured server failures from binary requests',async()=>{
    const blob=new Blob(['unused'],{type:'application/json'})
    blob.text=async()=>JSON.stringify({detail:'完整报表超过在线下载上限；未返回部分文件'})
    const error={response:{status:413,data:blob}}
    vi.mocked(http.post).mockRejectedValueOnce(error)
    await expect(exportApi.download(selection,'token')).rejects.toMatchObject({response:{status:413,data:{detail:expect.stringContaining('未返回部分')}}})
  })
})
