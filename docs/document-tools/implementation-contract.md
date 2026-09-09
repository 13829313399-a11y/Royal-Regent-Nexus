# 文档工作台集成契约

实现依据为用户提供的《RR-Nexus_Document-Tools_Codex-Spec.md》。用户原件保持只读。

## HTTP

均为已有 Cookie 登录，URL 前缀 `/api/tools`，仅当前上传者可读取文件、任务和产物。操作名 `word_to_pdf`, `pdf_to_word`, `word_to_excel`, `excel_to_word`, `pdf_to_excel`, `excel_to_pdf`, `pdf_split`。后台额外有 `inspect`, `package`, `revise`。

- GET capabilities: `{operations: [{id,label,available,reason}], worker: {online}, engines: {...}, limits: {max_file_bytes,max_pages}}`。
- POST uploads: multipart `file`, 可选 `factory_id`，202 `{source_id,inspection_job_id}`。
- GET sources/:id: `{id,original_name,detected_type,inspection_status,manifest,artifacts,inspection_job_id}`。manifest 含 pages、sheets、issues、supported_operations。artifact 列表与任务一致。
- POST sources/:id/password: `{password}`，202 `{job_id}`。密码不返回、不写日志。
- POST jobs: `{source_id,operation,options,client_request_id,batch_id?}` → 202 `{job_id}`。
- GET jobs: query `page=1,page_size=20,batch_id?,status?` → `{items: Job[],total,page,page_size}`。
- GET jobs/:id: Job = `{id,source_id,source_name,operation,execution_status,quality_status,stage,completed_units,total_units,revision,options,summary,error_code,error_message,created_at,finished_at,cancel_requested,artifacts}`。
- Job.artifacts = `[{id,role,format,filename,size,revision,expires_at}]`。role 为 source, result, preview, report, mapping, ir, package。
- GET jobs/:id/issues: query page/page_size → `{items:Issue[],total,page,page_size}`。
- GET jobs/:id/result: query table_id?,offset=0,limit=200 → `{schema_version,source_type,pages,blocks,tables,mappings,issues,total_cells,offset,limit}`。table 元数据完整，cells 按范围窗口加载；前端不用整份 OCR 轮询。
- POST jobs/:id/cancel → Job；POST jobs/:id/retry → 202 `{job_id}`。
- POST jobs/:id/revise: `{base_revision,corrections:[{target_id,new_value,reason}],region?:{page_index,bbox_pt},options?}` → 202 `{job_id}`。
- GET artifacts/:id/content、/download，content 支持 Range，二进制带准确 MIME。
- POST packages: `{artifact_ids,client_request_id}` → 202 `{job_id}`。
- GET sources/:id/split-suggestions: query page_index,target_height_pt?,axis=y → `{cuts_pt,protected_regions,page}`。

## 操作选项

由后端按操作严格校验；缺省值由服务端决定。所有转换接受 `page_selection="all"`, `ai_mode="auto"|"off"`, `output_name?`。Word→Excel: `include_notes_sheet=true`, `word_mode="tables"|"structure"`, `include_headers_footers=false`, `merge_continuation_tables=false`。Excel→Word/PDF: `sheets: string[]`, `range?`, `include_hidden=false`, `formula_mode="display"|"formula"`, `paper="original"|"A4"|"A3"`, `orientation="auto"|"portrait"|"landscape"`, `print_mode="original"|"fit_width"|"selection"`。PDF→Word: `layout_mode="editable"|"layout"`。PDF→Excel: `merge_continuation_tables=false`, `preserve_merges=true`, `include_notes_sheet=true`, `numeric_locale="preserve_ambiguous"|"dot_decimal"|"comma_decimal"`。

PDF split: `split_mode="groups"|"each"|"every_n"|"extract"|"double"|"crop"`, `groups="1-3;4,6,5"`, `every_n=1`, `duplicate_policy="keep"|"deduplicate"`, `axis="y"|"x"`, `page_index=0`, `cuts_pt:number[]`。裁切坐标统一可见页面左上角 point，不对底层隐藏内容作物理删除声明。

## 引擎 Python

共享模型 `app.services.document_tools.document_ir` 已落地。两组引擎分别提供 `office_engine.inspect_office(path, options, work_dir, progress, cancelled) -> EngineResult` / `office_engine.convert_office(path, operation, options, work_dir, progress, cancelled, ir=None) -> EngineResult`；`pdf_engine.inspect_pdf(...)` / `pdf_engine.convert_pdf(..., ir=None)`，签名同上。渲染器可复用 `office_engine.write_docx(ir,path,options)`、`write_xlsx(ir,path,options)`，PDF 引擎无需重复实现 Office 写出。最终 `EngineResult.files` 中每个 `{path:Path,role,format,filename}` 指向 work_dir 下完整文件，由主任务管线负责原子发布。

inspect 返回 IR、可选 preview PDF 和摘要（pages/sheets 等）；不改变原件。每个引擎调用 progress(stage,completed,total) 及 cancelled()。取消抛 Cancelled；可行动错误抛 ToolError。错误 PASSWORD_REQUIRED 使任务 awaiting_input。所有 OCR 只增强不可靠区域。修订接收已修正的 ir，不能重新覆盖已人工确认值。
