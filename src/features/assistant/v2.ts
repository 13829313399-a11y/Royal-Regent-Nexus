/**
 * 曜灵 v2 本地实现合同；生产启用须独立完成迁移与能力配置。
 * 与 types.ts / schemas/assistant.py 共用，保留 legacy 字段与行为。
 * fixtures 使用本文件中的 snake_case；SSE名称来自 event 字段。
 */
export type ISOTime = string;
export type SearchMode = 'off' | 'auto' | 'on';
export type RunState = 'connecting' | 'thinking' | 'tool_running' | 'answering'
  | 'completed' | 'failed' | 'cancelled' | 'interrupted';
export type ThinkingMode = 'auto' | 'on' | 'off';

export interface PageContext {
  module_id: string;
  route_name: string;
  factory_id: string | null;
  help_id: string | null;
}
export interface ResourceRef {
  module_id: string;
  resource_type: string;
  resource_id: string;
  revision?: string;
}
export interface Scope {
  factory_id: string | null;
  scope_label: string;
  authorization: 'current_user';
}
export interface ContextSelection {
  selection_id: string;
  resources: ResourceRef[];
  filters: Record<string, string | number | boolean | null>;
  // 这是选择描述；服务端必须按当前身份再查询业务事实。
}
export interface SendMessageV2 {
  protocol_version: 2;
  client_request_id: string;
  text: string;
  attachment_ids: string[];
  document_ids?: string[]; // P1文档；后端缺省[]，不混用图像附件表。
  intent: 'chat' | 'explain_page' | 'explain_element' | 'my_work' | 'research' | 'analyze_files';
  profile_id: 'default';
  thinking: ThinkingMode;
  web_search: SearchMode;
  page_context: PageContext | null;
  context_selection: ContextSelection | null;
}
export interface SearchTrace {
  requested_mode: SearchMode;
  execution: 'not_requested' | 'pending' | 'confirmed' | 'unconfirmed' | 'skipped' | 'failed';
  evidence_level: 'none' | 'results_returned' | 'pages_fetched';
  search_count: number | null;
  reason_code: string | null;
  attempted?: boolean;
  sources_returned?: number;
  pages_read?: number;
  research_summary?: string;
  page_failures?: Array<{url: string; code: string}>;
}
interface SourceBase {
  source_id: string;
  run_id: string;
  title: string;
  origin?: { run_id: string; source_id: string }; // 沿用旧资料，保留原检索时间。
}
export interface WebSource extends SourceBase {
  kind: 'web';
  step_id: string;
  provider: 'dashscope_multimodal' | 'qwen_responses' | 'custom_search' | 'public_reader';
  provider_ref: string;
  provider_request_id: string | null;
  url: string;
  site_name: string | null;
  retrieved_at: ISOTime;
  published_at: ISOTime | null;
  evidence_level: 'search_result' | 'page_content';
  excerpt?: string;
  excerpt_truncated?: boolean;
  final_url?: string;
  content_hash?: string;
  read_status?: 'completed' | 'failed' | 'not_attempted';
  read_error?: string | null;
  locator?: {kind: 'extracted_lines'; start: number; end: number};
}
export interface HelpSource extends SourceBase {
  kind: 'help';
  help_id: string;
  knowledge_version: string;
  source_fingerprint?: string | null;
  route_name: string;
  anchor_id: string | null;
}
export interface BusinessSource extends SourceBase {
  kind: 'business';
  tool_name: 'get_my_work' | 'get_injection_overview' | 'get_printer_status' | 'list_customer_orders' | 'get_carton_overview' | 'get_internal_quote_overview' | 'get_uv_operations_snapshot' | 'get_spray_operations_snapshot';
  resources: ResourceRef[];
  scope: Scope;
  as_of: ISOTime;
  data_mode: 'live' | 'snapshot' | 'synthetic';
  unknown_fields: string[];
}
export interface FileSource extends SourceBase {
  kind: 'file';
  file_ref: { kind: 'document' | 'image_attachment'; id: string };
  extracted_at: ISOTime;
  document_version?: string;
  excerpt_range?: { start: number; end: number; total: number };
  citation_eligible?: boolean;
  retrieval?: { selected_chunks: number; total_chunks: number; coverage: string; notice: string };
  ocr?: { signal_score: number | null; uncertain: boolean; uncertainty_reasons: string[]; engine: string };
  locator:
    | { kind: 'document' }
    | { kind: 'page'; page: number }
    | { kind: 'sheet'; sheet: string; cells: string }
    | { kind: 'paragraph'; paragraph: number }
    | { kind: 'lines'; start: number; end: number }
    | { kind: 'ocr_region'; page: number; region: number; bbox: { x: number; y: number; width: number; height: number; coordinate_system: 'normalized_0_1' } }
    | { kind: 'image' };
}
export type SourceRecord = WebSource | HelpSource | BusinessSource | FileSource;
export interface CitationBinding {
  binding_id: string;
  part_id: string;
  marker: string;
  source_ids: string[];
  resolution: 'pending' | 'resolved' | 'unresolved';
}
export interface Activity {
  step_id: string;
  kind: 'search' | 'read_page' | 'read_file' | 'query_business' | 'read_help' | 'synthesize';
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  label: string;
  started_at: ISOTime;
  finished_at: ISOTime | null;
}
export interface EvidencePart {
  type: 'evidence';
  schema_version: 2;
  run_id: string;
  revision: number;
  search: SearchTrace;
  sources: SourceRecord[];
  citations: CitationBinding[];
  activities: Activity[];
}
export type ContentPart =
  | { type: 'text'; text: string; part_id?: string }
  | { type: 'reasoning'; text: string; part_id?: string }
  | { type: 'image_ref'; attachment_id: string }
  | { type: 'document_ref'; file_id: string; document_version?: string } // P1用户消息保留原文档归属。
  | { type: 'tool_call'; calls: unknown[] }
  | { type: 'tool_result'; call_id: string; name: string; arguments: unknown; result: unknown }
  | EvidencePart
  | { type: 'actions'; schema_version: 2; revision: number; items: UIAction[] };
export interface TokenUsage {
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
}
export interface StepUsage {
  step_id: string;
  provider_request_id: string | null;
  tokens: TokenUsage | null;
  search_count: number | null;
}
export interface UsageSummary {
  schema_version: 2;
  complete: boolean;
  tokens: TokenUsage | null;
  search_count: number | null;
  steps: StepUsage[];
}
export type UIAction =
  | { type: 'highlight'; help_id: string; label: string }
  | { type: 'open_record'; label: string; route_name: string; params: Record<string, string>; query: Record<string, string>; resource: ResourceRef }
  | { type: 'open_draft'; label: string; route_name: string; draft_id: string };
interface EventBase { run_id: string; seq: number }
export type AssistantEvent = EventBase & (
  | { event: 'run.started'; message_id: string; protocol_version?: 1 | 2 }
  | { event: 'response.phase'; phase: 'connecting' | 'thinking' | 'tool_running' | 'answering' }
  | { event: 'response.delta'; channel: 'answer' | 'reasoning'; text: string; part_id?: string }
  | { event: 'evidence.updated'; evidence: EvidencePart }
  | { event: 'help.citations'; items: Array<{ id: string; version: string }> }
  | { event: 'ui.actions'; items: UIAction[] }
  | { event: 'context.window'; omitted_turns: number; character_budget: number; first_seq: number | null; strategy: string; version: number }
  | { event: 'run.completed'; finish_reason: string; outcome?: 'answered' | 'limited' | 'no_sources'; usage: TokenUsage | null; usage_summary?: UsageSummary; evidence_revision?: number }
  | { event: 'run.failed' | 'run.cancelled' | 'run.interrupted'; code: string; message: string; retryable: boolean }
);

export interface VerifiedSearchCombination {
  protocol: 'dashscope_multimodal' | 'qwen_responses' | 'custom_search';
  model: string;
  input: 'text' | 'text_image';
  thinking: ThinkingMode;
  strategy: 'turbo' | 'max' | 'agent' | 'agent_max' | 'provider_default';
  forced_search: boolean;
  source_return: boolean;
  inline_citations: boolean;
  verified_at: ISOTime;
}
export interface SearchCapability {
  reason_code?: string | null;
  status_label?: string;
  configured: boolean;
  verification: 'unverified' | 'verified' | 'failed';
  verified_at: ISOTime | null;
  supported_modes: SearchMode[];
  supported_protocols: Array<'dashscope_multimodal' | 'qwen_responses' | 'custom_search'>;
  verified_combinations: VerifiedSearchCombination[];
  source_return: boolean;
  inline_citations: boolean;
  page_fetch: boolean;
  last_result: ExecutionResult | null;
  last_success?: ExecutionResult | null;
  last_failure?: ExecutionResult | null;
}

export interface ExecutionResult {
  at: ISOTime; run_id?: string; state?: string; status?: 'success' | 'failed' | 'unconfirmed'; code: string | null;
  execution?: SearchTrace['execution']; evidence_level?: SearchTrace['evidence_level']; search_count?: number | null;
}

// GET /api/assistant/capabilities在既有返回对象上新增search字段。
// 旧profiles[].web_search保持false；v2读取search及其精确组合。
export interface SearchCapabilityExtension { search: SearchCapability }

// 注意：这里只提供类型；线上仍须Pydantic/运行时解析，不以TS类型代替校验。
