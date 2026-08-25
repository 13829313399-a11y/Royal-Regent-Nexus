import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')
const workspaceSource = readFileSync(join(process.cwd(), 'src/views/CartonMarkWorkspaceView.vue'), 'utf8')
const templateViewSource = readFileSync(join(process.cwd(), 'src/views/CartonMarkTemplateView.vue'), 'utf8')
const verificationViewSource = readFileSync(join(process.cwd(), 'src/views/CartonMarkVerificationView.vue'), 'utf8')
const qcVerificationViewSource = readFileSync(join(process.cwd(), 'src/views/CartonMarkQcVerificationView.vue'), 'utf8')
const cartonPanelSource = readFileSync(join(process.cwd(), 'src/components/modules/qa/CartonMarkCheckPanel.vue'), 'utf8')
const moduleDetailSource = readFileSync(join(process.cwd(), 'src/views/ModuleDetailView.vue'), 'utf8')

describe('carton mark standalone workspaces', () => {
  it('routes warehouse, canonical QC verification, and the legacy QA entry to dedicated full-page views', () => {
    const genericModuleRouteIndex = routerSource.indexOf("path: '/modules/:department/:module'")
    const templateRouteIndex = routerSource.indexOf("path: '/modules/pmc-warehouse/carton-mark-check'")
    const verificationRouteIndex = routerSource.indexOf("path: '/modules/qa/carton-mark-check'")
    const qcVerificationRouteIndex = routerSource.indexOf("path: '/modules/qc/carton-mark-check'")

    expect(templateRouteIndex).toBeGreaterThan(-1)
    expect(verificationRouteIndex).toBeGreaterThan(-1)
    expect(qcVerificationRouteIndex).toBeGreaterThan(-1)
    expect(templateRouteIndex).toBeLessThan(genericModuleRouteIndex)
    expect(verificationRouteIndex).toBeLessThan(genericModuleRouteIndex)
    expect(qcVerificationRouteIndex).toBeLessThan(genericModuleRouteIndex)
    expect(routerSource).toMatch(/name: 'carton-mark-template'[\s\S]{0,220}CartonMarkTemplateView\.vue[\s\S]{0,160}fullPage: true/)
    expect(routerSource).toMatch(/name: 'carton-mark-check'[\s\S]{0,220}CartonMarkVerificationView\.vue[\s\S]{0,160}fullPage: true/)
    expect(routerSource).toMatch(/name: 'qc-carton-mark-check'[\s\S]{0,220}CartonMarkQcVerificationView\.vue[\s\S]{0,160}fullPage: true/)
    expect(templateViewSource).toContain('<CartonMarkWorkspaceView workspace-mode="warehouse" />')
    expect(verificationViewSource).toContain('<CartonMarkWorkspaceView workspace-mode="qa" />')
    expect(qcVerificationViewSource).toContain('<CartonMarkWorkspaceView workspace-mode="qc" />')
  })

  it('keeps one visual shell but removes cross-module navigation around the core panel', () => {
    for (const requiredCopy of [
      'CartonMarkCheckPanel',
      'AccountMenu',
      '返回{{ returnDepartmentLabel }}',
      ':workspace-mode="workspaceMode"',
    ]) {
      expect(workspaceSource).toContain(requiredCopy)
    }

    expect(workspaceSource).not.toContain('箱唛业务切换')
    expect(workspaceSource).not.toContain('templateWorkspaceRoute')
    expect(workspaceSource).not.toContain('verificationWorkspaceRoute')
    expect(workspaceSource).not.toContain('当前待办')
    expect(workspaceSource).not.toContain('模块路径')
    expect(workspaceSource).not.toContain('角色与权限矩阵')
    expect(moduleDetailSource).not.toContain('CartonMarkCheckPanel')
  })

  it('keeps the selected factory in warehouse, QC, and legacy QA return links', () => {
    expect(workspaceSource).toContain('const activeFactory = computed(() => appStore.activeProductionFactory)')
    expect(workspaceSource).toMatch(/const departmentRoute = computed\(\(\) => getFactoryScopedRoute\([\s\S]{0,120}getDepartmentRoute\(currentDepartmentId\.value\),[\s\S]{0,80}activeFactory\.value\.id/)
    expect(workspaceSource).toContain(':to="departmentRoute"')
    expect(workspaceSource).not.toMatch(/<RouterLink[^>]+to="\/modules\/(?:pmc-warehouse|qa|qc)"/)
  })

  it('removes the non-workflow QA summary banner and statistics from the shared panel', () => {
    expect(cartonPanelSource).not.toContain('Carton Mark</p>')
    expect(cartonPanelSource).not.toContain('>Templates</p>')
    expect(cartonPanelSource).not.toContain('>Photos</p>')
    expect(cartonPanelSource).not.toContain('>Customers</p>')
    expect(cartonPanelSource).not.toContain('>Latest</p>')
    expect(cartonPanelSource).toContain('上传客人 Excel 与打印 PDF')
    expect(cartonPanelSource).toContain('上传实际收到箱唛图片')
    expect(cartonPanelSource).toContain('自动核对结果')
  })

  it('keeps the QA library scrollable at the top and reserves the full row below for verification results', () => {
    expect(cartonPanelSource).toContain('grid items-start gap-6')
    expect(cartonPanelSource).toContain('max-h-[520px] overflow-y-auto')
    expect(cartonPanelSource).toContain('QC Results')
    expect(cartonPanelSource).toContain('xl:col-span-2')
  })

  it('combines single and batch uploads into independent multi-file front and side selectors', () => {
    for (const requiredCopy of [
      '可一次选择多张',
      '无需文件配对',
      '选择正唛',
      '选择侧唛',
      '开始批量核对',
      '上一张正唛',
      '下一张侧唛',
      'switchActiveBatchPhoto',
      'getBatchPhotoPositionLabel',
      'handleBatchPhotoFileChange',
      'handleBatchPhotoDrop',
      'rotateActiveBatchPhoto',
      'rotateImageBlob',
      '当前正唛向左旋转 90 度',
      '当前侧唛向右旋转 90 度',
      'submitBatchPhoto',
      'batchAutoCheck',
    ]) {
      expect(cartonPanelSource).toContain(requiredCopy)
    }

    expect(cartonPanelSource).toContain('multiple')
    expect(cartonPanelSource).toContain(':disabled="!canSubmitBatchPhoto || isSavingBatchPhoto"')
    expect(cartonPanelSource).toContain('batchPhotoCount.value === 1')
    expect(cartonPanelSource).toContain('当前照片可框选箱唛区域')
    expect(cartonPanelSource).toContain('files[getActiveBatchPhotoIndex(side)] = croppedFile')
    expect(cartonPanelSource).toContain("@drop.prevent=\"handleBatchPhotoDrop($event, 'front')\"")
    expect(cartonPanelSource).toContain("@drop.prevent=\"handleBatchPhotoDrop($event, 'side')\"")
    expect(cartonPanelSource).toContain('files[requestedIndex] = rotatedFile')
    expect(cartonPanelSource).not.toContain('selectedFrontBatchFiles.value = [croppedFile]')
    expect(cartonPanelSource).not.toContain('selectedSideBatchFiles.value = [croppedFile]')
    expect(cartonPanelSource).not.toContain('批量核验同一箱唛')
    expect(cartonPanelSource).not.toContain('批量上传正唛')
    expect(cartonPanelSource).not.toContain('批量上传侧唛')
  })

  it('binds asynchronous verification results to the factory and files that started the request', () => {
    for (const requiredContract of [
      'let factoryGeneration = 0',
      'isCurrentFactoryTask',
      'const requestedFactoryId = activeFactoryId.value',
      'const requestedFactoryGeneration = factoryGeneration',
      'const requestedFrontFiles = [...selectedFrontBatchFiles.value]',
      'const requestedSideFiles = [...selectedSideBatchFiles.value]',
      'template.factoryId !== requestedFactoryId',
      'photo.factoryId !== requestedFactoryId',
      'factoryId: requestedFactoryId',
      'factoryName: requestedFactoryName',
      "const LEGACY_CARTON_MARK_FACTORY_ID: ProductionFactoryContextId = 'huaxing'",
      'factoryId: record.factoryId ?? LEGACY_CARTON_MARK_FACTORY_ID',
    ]) {
      expect(cartonPanelSource).toContain(requiredContract)
    }

    expect(cartonPanelSource).toMatch(/watch\(activeFactoryId,[\s\S]{0,120}factoryGeneration \+= 1/)
    expect(cartonPanelSource).toMatch(/createBatchPhotoRecords\([\s\S]{0,180}requestedFactoryId,[\s\S]{0,100}requestedFrontFiles,[\s\S]{0,100}requestedSideFiles/)
  })

  it('keeps the warehouse template route focused on customer, ITEM, and contract imports plus customer collections', () => {
    for (const requiredCopy of [
      '客名',
      'ITEM',
      '合同号',
      '客户箱唛集合',
      '按客户查看客人 Excel、打印 PDF 与纸箱部文字核对记录。',
      '请选择一个客户',
      '查看核对',
    ]) {
      expect(cartonPanelSource).toContain(requiredCopy)
    }

    expect(cartonPanelSource).not.toContain('采购订单号')
    expect(cartonPanelSource).toContain('客名由当前厂区纸箱部主管以上维护')
    expect(cartonPanelSource).toContain('维护客户')
    expect(cartonPanelSource).toContain('cartonMarkApi.listCustomers')
    expect(cartonPanelSource).toContain('for (const customer of customerOptions.value)')
    expect(cartonPanelSource).toContain('count: 0')
    expect(cartonPanelSource).toContain("carton_mark:customer_manage")
    expect(cartonPanelSource).toContain('v-model="form.customerName"')
    expect(cartonPanelSource).toContain('v-for="customer in customerOptions"')
    expect(cartonPanelSource).toContain('当前厂区尚未添加箱唛客户')
    expect(cartonPanelSource).not.toContain('内部报价台客户读取失败')
    expect(cartonPanelSource).toContain('customerOptionsRequestController?.abort()')
    expect(cartonPanelSource).toContain("if (props.workspaceMode) return props.workspaceMode === 'warehouse'")
    expect(cartonPanelSource).toContain('form.contractNumber')
  })

  it('requires the customer Excel and print PDF before archiving the warehouse document check', () => {
    for (const requiredContract of [
      'selectedExcelFile',
      'excelFileInput',
      'handleExcelFileDrop',
      'handlePdfFileDrop',
      'isExcelFile',
      '客人提供的 PO 箱唛 Excel',
      '选择打印 PDF',
      '上传并核对 Excel 与 PDF',
      'cartonMarkApi.createTemplate',
      'cartonMarkApi.listTemplates',
      'cartonMarkApi.recheckTemplate',
      'cartonMarkApi.deleteTemplate',
      'cartonMarkApi.downloadTemplateDocument',
      'factoryId: requestedFactoryId',
      'excelContract: currentExcelFile',
      'printPdf: currentFile',
      'documentCheckResult.summary.changed_count',
      'documentCheckResult.summary.missing_count',
      'documentCheckResult.summary.unexpected_count',
      'record.qcReady',
    ]) {
      expect(cartonPanelSource).toContain(requiredContract)
    }

    expect(cartonPanelSource).toContain('accept=".xls,.xlsx,.xlsm,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"')
    expect(cartonPanelSource).toContain('可点击选择或拖拽 Excel 到此处')
    expect(cartonPanelSource).toContain('可点击选择或拖拽 PDF 到此处')
    expect(cartonPanelSource).toContain('只有核对通过的 PDF 才可供 QC 现场核验')
    expect(cartonPanelSource).toContain('图形内文字不参与比较')
    expect(cartonPanelSource).toContain('排版与图形内文字不报差异')
    expect(cartonPanelSource).toContain("recheckingDocumentId === documentComparisonRecord.id ? '核对中' : '重新核对'")
    expect(cartonPanelSource).toContain('documentCheckedAt: record.updated_at')
    expect(cartonPanelSource).toContain('templateRequestController?.abort()')
    expect(cartonPanelSource).toContain('if (!isCurrentFactoryTask(factoryId, generation) || !isPanelMounted) return')
    expect(cartonPanelSource).not.toContain("const LOCAL_STORAGE_KEY = 'rr-carton-mark-library-records'")
    expect(cartonPanelSource).not.toContain("const STORE_NAME = 'cartonMarkTemplates'")
    expect(cartonPanelSource).not.toContain('readRecordsFromDb')
    expect(cartonPanelSource).not.toContain('writeRecordsToLocalStorage')
  })

  it('renders warehouse document checks as success, difference, or independent manual review states', () => {
    const statusBranchStart = cartonPanelSource.indexOf("if (record.checkStatus === '核对通过')")
    const statusBranchEnd = cartonPanelSource.indexOf('resetForm()', statusBranchStart)
    const statusBranches = cartonPanelSource.slice(statusBranchStart, statusBranchEnd)
    const reviewBranch = statusBranches.slice(statusBranches.lastIndexOf('} else {'))

    expect(cartonPanelSource).toContain("const documentReviewMessage = ref('')")
    expect(cartonPanelSource).toMatch(/if \(record\.checkStatus === '核对通过'\) \{[\s\S]{0,350}successMessage\.value/)
    expect(cartonPanelSource).toMatch(/else if \(record\.checkStatus === '发现差异'\) \{[\s\S]{0,350}errorMessage\.value/)
    expect(cartonPanelSource).toMatch(/else \{[\s\S]{0,400}documentReviewMessage\.value/)
    expect(reviewBranch).toContain('documentReviewMessage.value')
    expect(reviewBranch).toContain('请纸箱部人工确认 Excel 与打印 PDF 内容')
    expect(reviewBranch).not.toContain('errorMessage.value')
    expect(reviewBranch).not.toContain('请修正打印 PDF')
    expect(cartonPanelSource).toContain('v-if="documentReviewMessage"')
    expect(cartonPanelSource).toContain('border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800')
    expect(cartonPanelSource).toContain('border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700')
    expect(cartonPanelSource).toContain('border-green-100 bg-green-50 px-4 py-3 text-sm text-green-700')
    expect(cartonPanelSource).toContain('return records.value.filter((record) => record.qcReady)')
  })

  it('separates successful page-match extraction information from warnings', () => {
    expect(cartonPanelSource).toContain('documentCheckExtractionInfoMessages')
    expect(cartonPanelSource).toContain('documentCheckExtractionWarningMessages')
    expect(cartonPanelSource).toContain('/需复核|无法|失败|未识别/')
    expect(cartonPanelSource).toContain('border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800')
    expect(cartonPanelSource).toContain('border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-800')
    expect(cartonPanelSource).toContain('v-for="(status, index) in documentCheckExtractionInfoMessages"')
    expect(cartonPanelSource).toContain('v-for="(status, index) in documentCheckExtractionWarningMessages"')
    expect(cartonPanelSource).toContain(':key="`document-info-${status.source}-${status.engine}-${index}`"')
    expect(cartonPanelSource).toContain(':key="`document-warning-${status.source}-${status.engine}-${index}`"')
  })

  it('opens the exact PDF page selected from the现场照片 anchors', () => {
    expect(cartonPanelSource).toContain('const autoCheckMatchedPage = computed')
    expect(cartonPanelSource).toContain("find((status) => status.matched_page)?.matched_page ?? null")
    expect(cartonPanelSource).toContain('`${url}#page=${pdfPage}`')
    expect(cartonPanelSource).toContain("openTemplateDocument(comparisonTemplate, 'print_pdf', autoCheckMatchedPage)")
    expect(cartonPanelSource).toContain('`打开 PDF 第 ${autoCheckMatchedPage} 页`')
    expect(cartonPanelSource).toContain('autoCheckExtractionInfoMessages')
    expect(cartonPanelSource).toContain('autoCheckExtractionWarningMessages')
    expect(cartonPanelSource).toContain('status.requires_review')
    expect(cartonPanelSource).toContain('页面匹配信息')
  })

  it('keeps QC verification bound to the approved PDF and现场照片 rather than the source Excel', () => {
    expect(cartonPanelSource).toContain('v-if="!isWarehouseWorkspace"')
    expect(cartonPanelSource).toContain('上传实际收到箱唛图片')
    expect(cartonPanelSource).toContain('选择箱唛模板')
    expect(cartonPanelSource).toContain('打印 PDF 长框 vs QC 现场正唛')
    expect(cartonPanelSource).toContain('打印 PDF 短框 vs QC 现场侧唛')
    expect(cartonPanelSource).toContain('cartonMarkApi.batchAutoCheck')
    expect(cartonPanelSource).toContain('const pdfTemplate = await ensureTemplatePdfBlob(template)')
    expect(cartonPanelSource).toContain('pdfTemplate,')
    expect(cartonPanelSource).toMatch(/cartonMarkApi\.batchAutoCheck\(\{[\s\S]*?frontPhotos,[\s\S]*?sidePhotos,[\s\S]*?\}\)/)
  })
})
