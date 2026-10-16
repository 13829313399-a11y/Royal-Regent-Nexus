import { http } from '@/lib/http'
import { CUTTING_FACTORY } from './navigation'

export interface ReportSelection {kind:'period'|'settlement'|'payments';month:string;event_id?:string;document_id?:string}
export interface ReportPreview {token:string;title:string;metadata:Array<[string,string|number|null]>;sheets:Array<{name:string;rows:number}>;
  delivery?:{format:'xlsx'|'zip';volumes:number;manifest:Array<{volume:number;sheet:string;source:string;first:number;last:number;rows:number;total:number}>}}
export const exportApi={
  async preview(selection:ReportSelection,signal?:AbortSignal):Promise<ReportPreview>{
    return(await http.post('/cutting-operations/exports/preview',{...selection,factory_id:CUTTING_FACTORY},{signal,timeout:120000})).data
  },
  async download(selection:ReportSelection,token:string,signal?:AbortSignal):Promise<Blob>{
    try{return(await http.post('/cutting-operations/exports/download',{...selection,factory_id:CUTTING_FACTORY,token},{signal,responseType:'blob',timeout:120000})).data}
    catch(error){
      const response=(error as {response?:{data?:unknown}}).response
      if(response?.data instanceof Blob){try{response.data=JSON.parse(await response.data.text())}catch{/* Keep the standard error fallback. */}}
      throw error
    }
  },
}
export function saveReport(blob:Blob,selection:ReportSelection,token:string){
  const url=URL.createObjectURL(blob),link=document.createElement('a')
  const extension=blob.type.split(';')[0]==='application/zip'?'zip':'xlsx'
  link.href=url;link.download=`cutting-${selection.kind}-${selection.month}-${token.slice(0,12)}.${extension}`
  document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)
}
