import { http } from '@/lib/http'
import { CUTTING_FACTORY } from './navigation'
import type { Command } from './api'
export interface ScheduleRow { sheet:string; row:number; data:Record<string,string>; errors:string[]; status:'new'|'duplicate'|'conflict'|'invalid'; line_id:string|null }
export interface ScheduleSheet { sheet:string;status:'ready'|'empty'|'blocked';header_row:number|null;row_count:number;message:string }
export interface SchedulePreview { file_name:string;file_sha256:string;fingerprint:string;rows:ScheduleRow[];sheets:ScheduleSheet[];can_confirm:boolean;new_count:number;duplicate_count:number }
export interface ScheduleResult { batch_id:string;file_name:string;file_sha256:string;created:number;skipped:number;rows:Array<{line_id:string;sheet:string;row:number;reference_no:string;product_no:string;status:string;version:number}> }
export interface ScheduleCommand extends Command {file_name:string;file_sha256:string;fingerprint:string;confirmed:boolean}
const base='/cutting-operations/schedule-import'
function form(file:File,command?:ScheduleCommand) {
  const body=new FormData();body.append('factory_id',CUTTING_FACTORY);body.append('schedule_file',file)
  if(command)for(const key of ['operation_id','reason','fingerprint','file_sha256','confirmed'] as const)body.append(key,String(command[key]))
  return body
}
const options={headers:{'Content-Type':'multipart/form-data'},timeout:60000}
export const scheduleImportApi={
  async preview(file:File):Promise<SchedulePreview>{return(await http.post(`${base}/preview`,form(file),options)).data},
  async confirm(file:File,command:ScheduleCommand):Promise<ScheduleResult>{return(await http.post(`${base}/confirm`,form(file,command),options)).data},
  async recover(command:ScheduleCommand):Promise<{state:'committed';result:ScheduleResult}|{state:'abandoned'}>{return(await http.post(`${base}/recover`,{command})).data},
  async template():Promise<Blob>{return(await http.get(`${base}/template`,{params:{factory_id:CUTTING_FACTORY},responseType:'blob'})).data},
}
