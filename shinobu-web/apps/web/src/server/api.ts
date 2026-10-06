import { rrTranslationEntry } from '../runtime/rrIntegration';

export type Artifact = { id: string; role: string; format: string; filename: string; size: number };
export type Job = { id: string; source_id: string; source_name: string; operation: string; execution_status: string;
  stage: string; completed_units: number; total_units: number | null; revision: number; error_message?: string;
  options: Record<string, unknown>; artifacts: Artifact[]; created_at: string };
export type Source = { id: string; inspection_status: string; error_message?: string; inspection_job_id: string;
  manifest: { pages?: { page_index: number; width_pt: number; height_pt: number;
    image_resize?: { original_size: number[]; processing_size: number[] } }[] }; artifacts: Artifact[] };
export type Capabilities = { worker: { online: boolean }; image_translation?: { available: boolean; reason: string };
  limits: { max_file_bytes: number; max_pages: number };
  translation: { offline_available: boolean; online_available: boolean; online_model: string } };
export type Options = { translation_direction: 'en_to_zh' | 'zh_to_en'; translation_engine: 'offline' | 'online'; glossary: string; page_selection: string };
export type Review = { pages: {page_index:number;width_pt:number;height_pt:number}[];
  regions: {id:string;source:string;translation:string;page_index:number;bbox_pt:number[]|null;rendered:boolean;reason:string}[]; issues:string[] };
export const preserveLabel: Record<string,string> = { protected:'数字 / 编号保留', 'not-source-language':'保留原文',
  vertical:'竖排待核对', 'low-confidence':'识别不确定', 'invalid-text':'原文字体编码异常', overlap:'相邻文字重叠',
  'too-small':'字号过小', 'complex-background':'复杂背景保留', 'styled-text':'标志 / 彩色文字保留', illustration:'图案区域保留', 'does-not-fit':'译文空间不足', unchanged:'译文待核对' };

export function requestId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}
export async function request<T>(path: string, signal: AbortSignal, body?: unknown, method?: string): Promise<T> {
  const form = body instanceof FormData;
  const response = await fetch(`/api/tools${path}`, { signal, credentials: 'same-origin', cache: 'no-store',
    method: method ?? (body === undefined ? 'GET' : 'POST'),
    headers: body === undefined || form ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : form ? body : JSON.stringify(body) });
  if (response.status === 401 || response.status === 403) {
    location.replace(`/login?${new URLSearchParams({ redirect: rrTranslationEntry() })}`);
    throw new Error('登录状态已失效，请重新登录。');
  }
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(typeof error?.detail?.message === 'string' ? error.detail.message : typeof error?.detail === 'string' ? error.detail : `请求失败（${response.status}）`);
  }
  return response.status === 204 ? undefined as T : response.json();
}
export const artifactUrl = (artifact: Artifact, download = false) => `/api/tools/artifacts/${encodeURIComponent(artifact.id)}/${download ? 'download' : 'content'}`;
export const activeJob = (job?: Job) => !!job && ['queued', 'running'].includes(job.execution_status);
/** A delayed poll must not restore a replaced task or undo acknowledged withdrawal. */
export function canApplyJobPoll(current: Job | undefined, incoming: Job): boolean {
  return current?.id === incoming.id && !(!activeJob(current) && activeJob(incoming));
}
export const stateLabel: Record<string, string> = { uploading: '上传中', inspecting: '检查文件', ready: '待翻译', queued: '等待处理', running: '处理中', succeeded: '已完成', failed: '处理失败', cancelled: '已撤回', awaiting_input: '需要密码' };
export const stageLabel: Record<string, string> = { inspect: '检查文件', extract: '展开页面', recognize: '识别文字', translate: '翻译文字', rebuild: '擦字与排版', validate: '核验结果', package: '汇总 PDF' };
