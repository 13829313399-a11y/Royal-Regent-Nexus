export type RunState = 'idle' | 'connecting' | 'thinking' | 'answering' | 'tool_running' | 'completed' | 'cancelled' | 'interrupted' | 'failed'
export type PanelMode = 'edge' | 'side' | 'focus'
export interface PageContext { module_id: string; route_name: string; factory_id?: string | null; help_id?: string | null }
export interface HelpArticle {
  id: string; module_id: string; title: string; summary: string; content: string; anchor_id: string
  status: string; source_label: string; knowledge_version: string; route_names: string[]
  factory_ids?: string[]
  verification?: { fingerprint: string; verified_commit: string; sources: { path: string; symbol: string; expected_sha256: string; current_sha256: string | null; matches: boolean }[] }
  steps: { title: string; description: string; anchor_id: string; precondition: string; completion: string }[]
}
export interface Capabilities {
  reason_code?: string | null
  status_label?: string
  diagnostics_available?: boolean
  execution_status?: { last_result: import('./v2').ExecutionResult | null; last_success: import('./v2').ExecutionResult | null; last_failure: import('./v2').ExecutionResult | null }
  search?: import('./v2').SearchCapability
  materials?: { available: boolean; max_file_bytes: number; extensions: string[] }
  business_modules?: { module_id: string; label: string; coverage_state: string; tools: string[]; read_only: boolean; reason: string | null }[]
  enabled: boolean; configuration_status: string; schema_status: string; connection_status: string
  verified_at: string | null; provider: string; model: string | null; help_status: string
  profiles: { id: string; label: string; thinking: 'unknown' | 'toggle' | 'always' | 'none'; vision: boolean; web_search: boolean; function_calling: boolean }[]
}
export type ModuleCoverageState = 'business_read' | 'guide_only' | 'disabled' | 'not_connected' | 'forbidden'
export interface ModuleCoverage {
  factory_id: string; checked_at: string; catalog_scope: 'registered_modules'
  items: { module_id: string; label: string; state: ModuleCoverageState; reason: string; read_only: boolean; guide_count: number; verification: string }[]
}
export interface Conversation { id: string; title: string; revision: number; deletion_state: string; created_at: number; updated_at: number; favorite?: boolean; snippet?: string }
export interface Citation { id: string; version: string; source_fingerprint?: string }
export interface ContentPart { type: string; text?: string; attachment_id?: string; [key: string]: unknown }
export interface Message {
  unavailable?: boolean
  id: string; run_id: string; seq: number; role: string; content_parts: ContentPart[]; status: RunState
  help_citations: Citation[]; context_descriptor: PageContext | null; created_at: number
  help_verification?: 'legacy_version_only'
}
export interface MessagePage { session: Conversation; items: Message[]; next_cursor: number | null; active_run_id: string | null }
export interface Snapshot { run_id: string; session_id: string; state: RunState; usage: Record<string, number> | null; error_code: string | null; context_window: { omitted_turns?: number }; items: Message[] }
export interface SendPayload {
  protocol_version?: 1 | 2; document_ids?: string[]; context_selection?: import('./v2').ContextSelection | null
  client_request_id: string; text: string; attachment_ids: string[]; intent: 'chat' | 'explain_page' | 'explain_element' | 'my_work' | 'research' | 'analyze_files'
  profile_id: 'default'; thinking: 'auto' | 'on' | 'off'; web_search: 'off' | 'on' | 'auto'; page_context: PageContext | null
}
export interface DraftAttachment { id: string; url: string; name: string }
export interface DocumentFile { id: string; name: string; parse_status: string; session_id?: string; document_version?: string; indexed_segments?: number; error_code?: string; parse_index?: import('./v2').FileSource['locator'][] }
export interface DocumentSearchResult {
  materials: Array<import('./documentFormat').DocumentSegment & { source_id: string; name: string; document_version: string; excerpt_range: { start: number; end: number; total: number } }>
  report: { selected_chunks: number; total_chunks: number; matched_chunks: number; coverage: string; notice: string; unmatched_identifiers: string[] }
}
export interface DraftScope { page: PageContext | null; title: string; selection: import('./v2').ContextSelection | null }
export interface Draft { text: string; attachments: DraftAttachment[]; documents: DocumentFile[]; scope?: DraftScope; search?: import('./v2').SearchMode; thinking?: import('./v2').ThinkingMode; publicQuery?: string }
export interface Artifact { id: string; title: string; kind: string; current_revision: number; revision: number; content: string; source_refs: import('./v2').SourceRecord[]; export_formats: string[] }
export interface StreamEvent { event: string; data: { run_id: string; seq: number; [key: string]: unknown } }
export interface LocalRun { runId: string; sessionId: string; state: RunState; payload: SendPayload; lastSeq: number; error: string; controller: AbortController; omittedTurns: number; retryable?: boolean }
export const activeStates: RunState[] = ['connecting', 'thinking', 'answering', 'tool_running']
export const stateLabels: Record<RunState, string> = { idle: '随时问我', connecting: '正在连接', thinking: '正在思考', answering: '正在回答', tool_running: '正在查阅说明', completed: '回答完成', cancelled: '已停止', interrupted: '连接中断', failed: '本次未完成' }
