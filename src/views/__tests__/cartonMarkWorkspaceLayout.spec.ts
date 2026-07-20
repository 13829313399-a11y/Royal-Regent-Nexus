import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')
const workspaceSource = readFileSync(join(process.cwd(), 'src/views/CartonMarkWorkspaceView.vue'), 'utf8')
const templateViewSource = readFileSync(join(process.cwd(), 'src/views/CartonMarkTemplateView.vue'), 'utf8')
const verificationViewSource = readFileSync(join(process.cwd(), 'src/views/CartonMarkVerificationView.vue'), 'utf8')
const cartonPanelSource = readFileSync(join(process.cwd(), 'src/components/modules/qa/CartonMarkCheckPanel.vue'), 'utf8')
const moduleDetailSource = readFileSync(join(process.cwd(), 'src/views/ModuleDetailView.vue'), 'utf8')

describe('carton mark standalone workspaces', () => {
  it('routes warehouse templates and QA verification to separate dedicated full-page views', () => {
    const genericModuleRouteIndex = routerSource.indexOf("path: '/modules/:department/:module'")
    const templateRouteIndex = routerSource.indexOf("path: '/modules/pmc-warehouse/carton-mark-check'")
    const verificationRouteIndex = routerSource.indexOf("path: '/modules/qa/carton-mark-check'")

    expect(templateRouteIndex).toBeGreaterThan(-1)
    expect(verificationRouteIndex).toBeGreaterThan(-1)
    expect(templateRouteIndex).toBeLessThan(genericModuleRouteIndex)
    expect(verificationRouteIndex).toBeLessThan(genericModuleRouteIndex)
    expect(routerSource).toMatch(/name: 'carton-mark-template'[\s\S]{0,220}CartonMarkTemplateView\.vue[\s\S]{0,160}fullPage: true/)
    expect(routerSource).toMatch(/name: 'carton-mark-check'[\s\S]{0,220}CartonMarkVerificationView\.vue[\s\S]{0,160}fullPage: true/)
    expect(templateViewSource).toContain('<CartonMarkWorkspaceView workspace-mode="warehouse" />')
    expect(verificationViewSource).toContain('<CartonMarkWorkspaceView workspace-mode="qa" />')
  })

  it('keeps one visual shell but removes cross-module navigation around the core panel', () => {
    for (const requiredCopy of [
      'CartonMarkCheckPanel',
      'AccountMenu',
      '返回{{ isWarehouseWorkspace ? \'PMC / 仓管\' : \'QA 部\' }}',
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

  it('keeps the selected factory in warehouse and QA return links', () => {
    expect(workspaceSource).toContain('const activeFactory = computed(() => appStore.activeProductionFactory)')
    expect(workspaceSource).toMatch(/const departmentRoute = computed\(\(\) => getFactoryScopedRoute\([\s\S]{0,120}getDepartmentRoute\(currentDepartmentId\.value\),[\s\S]{0,80}activeFactory\.value\.id/)
    expect(workspaceSource).toContain(':to="departmentRoute"')
    expect(workspaceSource).not.toMatch(/<RouterLink[^>]+to="\/modules\/(?:pmc-warehouse|qa)"/)
  })

  it('removes the non-workflow QA summary banner and statistics from the shared panel', () => {
    expect(cartonPanelSource).not.toContain('Carton Mark</p>')
    expect(cartonPanelSource).not.toContain('>Templates</p>')
    expect(cartonPanelSource).not.toContain('>Photos</p>')
    expect(cartonPanelSource).not.toContain('>Customers</p>')
    expect(cartonPanelSource).not.toContain('>Latest</p>')
    expect(cartonPanelSource).toContain('上传客人箱唛资料模板')
    expect(cartonPanelSource).toContain('上传实际收到箱唛图片')
    expect(cartonPanelSource).toContain('自动核对结果')
  })

  it('keeps the QA library scrollable at the top and reserves the full row below for verification results', () => {
    expect(cartonPanelSource).toContain('grid items-start gap-6')
    expect(cartonPanelSource).toContain('max-h-[520px] overflow-y-auto')
    expect(cartonPanelSource).toContain('QA Results')
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
      '点击一个客户，查看该客户已上传的全部箱唛 PDF。',
      '请选择一个客户',
      '查看PDF',
    ]) {
      expect(cartonPanelSource).toContain(requiredCopy)
    }

    expect(cartonPanelSource).not.toContain('采购订单号')
    expect(cartonPanelSource).not.toContain('当前厂区客名库')
    expect(cartonPanelSource).not.toContain('新增客名')
    expect(cartonPanelSource).toContain("if (props.workspaceMode) return props.workspaceMode === 'warehouse'")
    expect(cartonPanelSource).toContain('form.contractNumber')
  })
})
