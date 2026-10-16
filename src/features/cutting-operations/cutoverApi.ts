import { http } from '@/lib/http'
import { CUTTING_FACTORY } from './navigation'
import type { Access } from './api'

export type CutoverScope = 'internal' | 'finance'
export interface CutoverTarget {workspace:string;id:string;month:string;event_id?:string;line_id?:string;kind?:'task'|'issue'|'report'}
export interface CutoverTrace {key:string;document_id:string;kind:string;label?:string;state:string;effective:boolean;target:CutoverTarget;replacements?:Array<{id:string;target:CutoverTarget}>;history:Array<{id:string;action:string;day:string;actor:string;actor_id:string;date:string;reason:string;reference?:string;amount:string;currency:string;replaces_document_id?:string|null;target:CutoverTarget}>}
export interface CutoverRow {key:string;category:string;label:string;value:string|null;unit:string;sources:string[];line_id:string;note:string;status:string;declared?:string;evidence?:string;difference?:string|null;target?:CutoverTarget|null}
export interface CutoverComparison {key:string;value:string;unit:string;evidence:string}
export interface ExternalOpening {description:string;evidence:string}
export interface CutoverPreview {month:string;start:string;cutoff:string;scope:CutoverScope;generated_at:string;token:string;rows:CutoverRow[];notices:Array<{message:string;line_id:string}>;external:ExternalOpening[];counts:Record<string,number>;state:'preparation_only';can_post:false;history?:CutoverTrace[];batch?:{number:number;size:number;total:number;pages:number;unit:string;query:string}}
export function canReadCutover(access:Access|undefined,scope:CutoverScope){
  return !!access?.enabled&&access.permissions.includes('read')&&(scope==='internal'?['cost_read']:['settlement_read','payment_read']).every(p=>access.permissions.includes(p))
}
export const cutoverApi={
  async preview(month:string,scope:CutoverScope,options:{token?:string;comparisons?:CutoverComparison[];external?:ExternalOpening[];batch?:number;batch_size?:number;query?:string}={},signal?:AbortSignal):Promise<CutoverPreview>{
    return (await http.post('/cutting-operations/cutover/preview',{factory_id:CUTTING_FACTORY,month,scope,...options},{signal,timeout:120000})).data
  },
}
