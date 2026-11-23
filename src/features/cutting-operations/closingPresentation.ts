import type { InjectionKey } from 'vue'
import { formatBusinessDateTime } from '@/lib/dateTime'

export interface ClosingReadLocation {month:string;id?:string;eventId?:string}

export function closingReadTime(value:string):string {
  const time=formatBusinessDateTime(value,{includeSeconds:true,fallback:''})
  return time?`${time}（北京时间）`:'未记录'
}

export const closingReportTabs={
  production:'生产与外发数量',
  materials:'领退料及耗用',
  costs:'材料费用试算',
  trace:'来源及更正追溯',
} as const
export type ClosingReportTab=keyof typeof closingReportTabs

export function readClosingReportTab(value:unknown):ClosingReportTab {
  return value==='materials'||value==='costs'||value==='trace'?value:'production'
}

// Parent-owned URL bookkeeping does not navigate or discard any business form.
// External routes and browser Back still run the ordinary draft/unknown-write guards.
export const closingPresentationKey:InjectionKey<(path:string)=>boolean>=Symbol('cutting-closing-presentation')
