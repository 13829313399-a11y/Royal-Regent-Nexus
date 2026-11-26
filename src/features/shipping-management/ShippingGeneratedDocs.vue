<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ChevronDown, Download, FileSpreadsheet, Mail, RefreshCw, Trash2 } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import { productNameForCode } from './productName'
import {
  deleteGeneratedDoc,
  getGeneratedDoc,
  listGeneratedDocs,
  searchScheduleProducts,
  updateGeneratedDoc,
  type GeneratedDoc,
  type GeneratedDocDetail,
} from '@/api/shippingMail'

const props = defineProps<{ factoryId: string; module: 'so' | 'truck' | 'supplement'; label?: string; heading?: string; compact?: boolean }>()
const emit = defineEmits<{
  'import-cabinet': [payload: { taskId: string; filename: string; header: Record<string, unknown>; lines: Array<Record<string, unknown>> }]
  'import-truck': [payload: { mode: 'buzzbee' | 'bulk'; taskId: string; filename: string; header: Record<string, unknown>; lines: Array<Record<string, unknown>> }]
}>()

const docs = ref<GeneratedDoc[]>([])
const loading = ref(false)
const message = ref('')
const lookupWarning = ref('')
const docIssues = ref<Record<string, boolean>>({})
const pendingId = ref('')
const busyId = ref('')
const selectedDocIds = ref<string[]>([])
const bulkDeleteArmed = ref(false)
const bulkDeleting = ref(false)
const imported = ref<Record<string, boolean>>({})
const selectedId = ref('')
const detail = ref<GeneratedDocDetail | null>(null)
const showDetail = ref(false)
const loadingDetail = ref(false)
const saving = ref(false)

const isSo = computed(() => props.module === 'so')
const selectedDoc = computed(() => docs.value.find((doc) => doc.id === selectedId.value) ?? null)
const allDocsSelected = computed(() => docs.value.length > 0 && docs.value.every((doc) => selectedDocIds.value.includes(doc.id)))

function toggleDoc(docId: string) {
  selectedDocIds.value = selectedDocIds.value.includes(docId)
    ? selectedDocIds.value.filter((id) => id !== docId)
    : [...selectedDocIds.value, docId]
  bulkDeleteArmed.value = false
}

function onToggleAllDocs(event: Event) {
  selectedDocIds.value = (event.target as HTMLInputElement).checked ? docs.value.map((doc) => doc.id) : []
  bulkDeleteArmed.value = false
}

async function bulkDeleteDocs() {
  if (!selectedDocIds.value.length) return
  if (!bulkDeleteArmed.value) {
    bulkDeleteArmed.value = true
    window.setTimeout(() => { bulkDeleteArmed.value = false }, 5000)
    return
  }
  bulkDeleting.value = true
  try {
    let deleted = 0
    for (const docId of [...selectedDocIds.value]) {
      try {
        await deleteGeneratedDoc(props.factoryId, docId)
        deleted += 1
      } catch {
        // continue with the rest
      }
    }
    selectedDocIds.value = []
    bulkDeleteArmed.value = false
    selectedId.value = ''
    await load()
    message.value = `已删除 ${deleted} 份生成文件。`
  } finally {
    bulkDeleting.value = false
  }
}

type CabinetField = {
  key: string
  label: string
  hint: string
  type?: 'date' | 'select'
  options?: readonly string[]
}

const fields: CabinetField[] = [
  { key: 'number', label: '柜', hint: '手动' },
  { key: 'shipper', label: '发货商', hint: '固定' },
  { key: 'consignee', label: '收货商', hint: '邮件自动识别' },
  { key: 'cutoff', label: '到货截止日期', hint: '邮件自动识别' },
  { key: 'contractNo', label: '合同号', hint: '邮件自动识别' },
  { key: 'vesselName', label: '船名', hint: '邮件自动识别' },
  { key: 'voyageNo', label: '航次', hint: '邮件自动识别' },
  { key: 'transportCompany', label: '运输公司', hint: '邮件自动识别' },
  { key: 'containerType', label: '柜型', hint: '邮件自动识别' },
  { key: 'tradeTerm', label: '成交方式', hint: '手动', type: 'select', options: ['FOB', 'EXW', 'CIF'] },
  { key: 'country', label: '出口国家', hint: '邮件自动识别' },
  { key: 'originPort', label: '出港口', hint: '邮件自动识别', type: 'select', options: ['盐田', '蛇口'] },
  { key: 'bookingNo', label: '订舱号/SO', hint: '邮件自动识别' },
  { key: 'containerNo', label: '柜号', hint: '邮件自动识别' },
  { key: 'tareWeight', label: '柜重', hint: '手动' },
  { key: 'brandNote', label: '品牌', hint: '邮件识别/合同带出' },
  { key: 'poNo', label: 'PO（箱唛）', hint: '邮件识别/合同带出' },
  { key: 'shippingClerk', label: '船务', hint: '手动', type: 'select', options: ['农建壮', '小美'] },
]

const truckFields: CabinetField[] = [
  { key: 'shipper', label: '发货商', hint: '源固定' },
  { key: 'consignee', label: '收货商', hint: '邮件自动识别' },
  { key: 'contractNo', label: '合同号', hint: '邮件识别·合同带出' },
  { key: 'bookingNo', label: '订舱号', hint: '邮件自动识别' },
  { key: 'filingCode', label: '备案货号', hint: '手动' },
  { key: 'poNo', label: '箱唛（PO）', hint: '邮件识别·合同带出' },
  { key: 'country', label: '国家', hint: '邮件自动识别' },
  { key: 'brandName', label: '品牌', hint: '邮件识别/合同带出' },
  { key: 'vehicle', label: '车头注明（车次）', hint: '手动' },
  { key: 'arrivalCutoff', label: '到货截止日期', hint: '邮件自动识别' },
  { key: 'sailingDate', label: '发车日期', hint: '邮件自动识别', type: 'date' },
  { key: 'transportCompany', label: '运输公司', hint: '邮件自动识别' },
  { key: 'tradeTerm', label: '成交方式', hint: '邮件自动识别', type: 'select', options: ['FOB', 'EXW', 'CIF'] },
  { key: 'originPort', label: '出港口', hint: '邮件自动识别' },
  { key: 'tableName', label: '表格名称', hint: '手动' },
  { key: 'cutoff', label: '截单日期', hint: '邮件自动识别' },
]

const displayFields = computed(() => props.module === 'truck' ? truckFields : fields)

const form = reactive<Record<string, string>>({})

function importedKey(id: string) {
  return `shipping-cabinet-imported:${props.factoryId}:${id}`
}

function markImported(docId: string) {
  imported.value = { ...imported.value, [docId]: true }
  window.localStorage.setItem(importedKey(docId), '1')
}

function isImported(doc: GeneratedDoc | null) {
  return Boolean(doc && imported.value[doc.id])
}

function displayName(doc: GeneratedDoc) {
  if (props.module === 'truck' && doc.brand_name?.trim()) return doc.brand_name.trim()
  return doc.email_name?.trim() || doc.filename
}

function attachmentLabel(doc: GeneratedDoc) {
  return doc.email_name?.trim() || doc.filename
}

function attachmentIssue(doc: GeneratedDoc) {
  return Boolean(docIssues.value[doc.id])
}

function downloadName(doc: GeneratedDoc) {
  const ext = doc.filename.match(/\.[^.]+$/)?.[0] || ''
  if (doc.id === selectedId.value && form.filingCode?.trim()) {
    return `${form.filingCode.trim()}${ext}`
  }
  return doc.filename
}

function downloadUrl(doc: GeneratedDoc) {
  return `/api/shipping/generated-docs/${doc.id}/download?factory_id=${encodeURIComponent(props.factoryId)}`
}

function value(value: unknown) {
  return value == null ? '' : String(value)
}

function fillForm(source: GeneratedDocDetail) {
  const header = source.header ?? {}
  form.number = value(header.number)
  form.shipper = value(header.shipper) || '华兴玩具制品（河源）有限公司'
  form.consignee = value(header.consignee)
  form.cutoff = value(header.cutoff)
  const lineContracts = [...new Set((source.lines ?? []).map((line) => value(line.contract).trim()).filter(Boolean))]
  form.contractNo = value(header.contractNo).trim() || lineContracts[0] || ''
  form.vesselName = value(header.vessel)
  form.voyageNo = value(header.voyage)
  form.transportCompany = value(header.transportCompany)
  form.containerType = value(header.containerType)
  form.tradeTerm = value(header.tradeTerm) || 'FOB'
  form.country = value(header.destinationCountry)
  form.originPort = value(header.originPort) || '盐田'
  form.bookingNo = value(header.bookingNo) || value(header.soNo)
  form.containerNo = value(header.containerNo)
  form.tareWeight = value(header.tareWeight)
  form.shippingClerk = value(header.shippingClerk) || value(header.preparer)
  form.soNo = value(header.soNo)
  form.poNo = value(header.poNo)
  form.bookingNo = value(header.bookingNo)
  form.orderNo = value(header.orderNo)
  form.productionNo = value(header.productionNo)
  form.filingCode = value(header.filingCode)
  form.carrierName = value(header.carrierName)
  form.sailingDate = value(header.sailingDate) || value(header.sheetDate)
  form.remark = value(header.remark)
  form.brandNote = value(header.brandNote)
  form.brandName = value(header.brandName) || value(header.brandNote)
  form.warehouseNo = value(header.warehouseNo) || value(header.warehouse_no)
  form.country = value(header.country) || value(header.destinationCountry)
  form.arrivalCutoff = value(header.arrivalCutoff) || value(header.cutoff)
  form.vehicle = value(header.vehicle)
  form.truckType = value(header.truckType)
  form.carrierName = value(header.transportCompanyName) || value(header.carrierName)
  form.transportCompany = value(header.transport) || value(header.transportCompany)
  const cleanTransport = String(form.transportCompany || '').trim().replace(/[，,\s]+$/, '')
  const carrier = cleanTransport ? (cleanTransport.endsWith('运输') ? cleanTransport : `${cleanTransport}运输`) : ''
  const port = String(form.originPort || '').trim()
  const formattedTableName = carrier && port ? `${carrier}，出${port}` : (port ? `出${port}` : carrier)
  form.tableName = formattedTableName || value(header.tableName)
}

async function enrichFromSchedule() {
  const query = [form.soNo, form.bookingNo, form.contractNo, form.filingCode, form.poNo]
    .map((item) => String(item || '').trim())
    .find(Boolean)
  if (!query) return
  try {
    const items = await searchScheduleProducts(props.factoryId, query)
    const item = items[0]
    if (!item) return
    if (!String(form.contractNo || '').trim() && item.contract_no) form.contractNo = String(item.contract_no)
    if (!String(form.poNo || '').trim() && item.customer_po) form.poNo = String(item.customer_po)
    if (!String(form.filingCode || '').trim() && item.product_code) form.filingCode = String(item.product_code)
    if (!String(form.country || '').trim() && item.country) form.country = String(item.country)
    if (!String(form.brandName || '').trim() && item.brand) form.brandName = String(item.brand)
    if (!String(form.brandNote || '').trim() && item.brand) form.brandNote = String(item.brand)
    form.soNo = String(form.soNo || item.so_number || '')
    if (form.contractNo || form.poNo) lookupWarning.value = ''
  } catch {
    // silent enrichment: manual fields remain editable
  }
}

async function loadDetail(doc: GeneratedDoc | null) {
  detail.value = null
  lookupWarning.value = ''
  if (!doc) return
  loadingDetail.value = true
  try {
    detail.value = await getGeneratedDoc(props.factoryId, doc.id)
    fillForm(detail.value)
    void enrichFromSchedule()
    if (!String(form.poNo || '').trim() && String(form.contractNo || '').trim()) {
      void onContractChange()
    } else if (!String(form.contractNo || '').trim() && String(form.filingCode || '').trim()) {
      void onFilingCodeChange()
    } else if (String(form.contractNo || '').trim() && !String(form.brandNote || '').trim()) {
      void onContractChange()
    }
  } catch (error) {
    const text = getApiErrorMessage(error)
    if (text.includes('生成文件不存在')) {
      docs.value = docs.value.filter((item) => item.id !== doc.id)
      selectedId.value = docs.value[0]?.id ?? ''
      detail.value = null
    }
    message.value = `读取文件详情失败：${text}`
  } finally {
    loadingDetail.value = false
  }
}

async function load() {
  loading.value = true
  try {
    docs.value = await listGeneratedDocs(props.factoryId, props.module)
    const ids = new Set(docs.value.map((doc) => doc.id))
    selectedDocIds.value = selectedDocIds.value.filter((id) => ids.has(id))
    imported.value = Object.fromEntries(docs.value.map((doc) => [doc.id, window.localStorage.getItem(importedKey(doc.id)) === '1']))
    if (!docs.value.some((doc) => doc.id === selectedId.value)) selectedId.value = docs.value[0]?.id ?? ''
    await loadDetail(selectedDoc.value)
    message.value = ''
  } catch (error) {
    message.value = getApiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

async function selectDoc(doc: GeneratedDoc) {
  if (selectedId.value === doc.id) return
  selectedId.value = doc.id
  showDetail.value = false
  await loadDetail(doc)
}

function buildHeader(): Record<string, unknown> {
  if (!detail.value) return {}
  return {
    ...(detail.value.header ?? {}),
    shipper: form.shipper,
    consignee: form.consignee,
    contractNo: form.contractNo,
    vessel: form.vesselName,
    voyage: form.voyageNo,
    cutoff: form.cutoff,
    number: form.number,
    bookingNo: form.bookingNo,
    transportCompany: form.transportCompany,
    containerType: form.containerType,
    tradeTerm: form.tradeTerm,
    destinationCountry: form.country,
    originPort: form.originPort,
    containerNo: form.containerNo,
    tareWeight: form.tareWeight,
    shippingClerk: form.shippingClerk,
    soNo: form.soNo || form.bookingNo,
    poNo: form.poNo,
    orderNo: form.orderNo,
    productionNo: form.productionNo,
    filingCode: form.filingCode,
    carrierName: form.carrierName,
    sailingDate: form.sailingDate,
    remark: form.remark,
    brandNote: form.brandNote,
    brandName: form.brandName,
    country: form.country,
    arrivalCutoff: form.arrivalCutoff,
    vehicle: form.vehicle,
    truckType: form.truckType,
    tableName: form.tableName,
    warehouseNo: form.warehouseNo,
    transportCompanyName: form.carrierName,
    preparer: form.shippingClerk,
  }
}

async function resolveValidatedScheduleLines(
  contractValue: string,
  lines: Array<Record<string, unknown>>,
  fallbackCode?: string,
): Promise<Array<Record<string, unknown>> | null> {
  const contract = String(contractValue || '').trim()
  if (!contract) {
    message.value = '请先填写与厂区总排期一致的合同号再导入'
    return null
  }
  const lineCodes = [...new Set(lines.map((line) => String(line.product_code || line.filingCode || line.declareCode || '').trim()).filter(Boolean))]
  const fallback = String(fallbackCode || '').trim()
  const codes = lineCodes.length ? lineCodes : (fallback ? [fallback] : [])
  try {
    const items = await searchScheduleProducts(props.factoryId, contract)
    const matched = items.filter((item) => String(item.contract_no || '').trim().toLowerCase() === contract.toLowerCase())
    if (!matched.length) {
      message.value = `合同号 ${contract} 在厂区总排期不存在，不能导入`
      return null
    }
    const nameByCode = new Map<string, string>()
    const contractByCode = new Map<string, string>()
    for (const item of matched) {
      const code = String(item.product_code || '').trim()
      if (code && item.product_name && !nameByCode.has(code)) nameByCode.set(code, String(item.product_name))
    }
    if (codes.length) {
      const missing = codes.filter((code) => !matched.some((item) => String(item.product_code || '').trim() === code))
      if (missing.length) {
        const unresolved: string[] = []
        for (const code of missing) {
          const found = await searchScheduleProducts(props.factoryId, code)
          const hit = found.find((item) => (String(item.product_code || '').replace(/\s+/g, '') === code.replace(/\s+/g, '') || String(item.product_name || '').includes(code)) && String(item.contract_no || '').trim())
          if (hit) {
            contractByCode.set(code, String(hit.contract_no || '').trim())
            if (hit.product_name && !nameByCode.has(code)) nameByCode.set(code, String(hit.product_name))
          } else {
            unresolved.push(code)
          }
        }
        if (unresolved.length) {
          message.value = `产品编号 ${unresolved.join('、')} 在厂区总排期不存在，不能导入`
          return null
        }
      }
      if (lineCodes.length) {
        return lines.map((line) => {
          const code = String(line.product_code || line.filingCode || line.declareCode || '').trim()
          const lineContract = String(line.contract || line.contract_no || '').trim()
          const productName = String(line.description || line.name || line.product_name || nameByCode.get(code) || '').trim()
          return {
            ...line,
            contract: lineContract || contractByCode.get(code) || contract,
            product_name: productName,
            name: productName,
            description: productName,
          }
        })
      }
    }
    const scheduleItems = codes.length
      ? matched.filter((item) => codes.includes(String(item.product_code || '').trim()))
      : matched.filter((item) => String(item.product_code || '').trim())
    if (!scheduleItems.length) {
      message.value = '该文件没有备案货号/产品编号，不能从厂区总排期导入'
      return null
    }
    if (!form.filingCode && scheduleItems[0]?.product_code) {
      form.filingCode = String(scheduleItems[0].product_code)
    }
    return scheduleItems.map((item) => ({
      contract: item.contract_no || contract,
      filingCode: item.product_code,
      declareCode: item.product_code,
      product_code: item.product_code,
      description: item.product_name || '',
      name: item.product_name || '',
      quantity: item.quantity ?? null,
      cartons: item.cartons ?? null,
      coefficient: item.coefficient ?? null,
      grossWeight: item.gross_weight ?? null,
      netWeight: item.net_weight ?? null,
      cbm: item.cbm ?? null,
      country: item.country || form.country || '',
      brand: item.brand || form.brandName || form.brandNote || '',
      so: item.so_number || form.bookingNo || form.soNo || '',
      po: item.customer_po || form.poNo || '',
      cartonMark: item.customer_po || form.poNo || '',
    }))
  } catch (error) {
    message.value = `校验厂区总排期失败：${getApiErrorMessage(error)}`
    return null
  }
}

async function fillProductNames(lines: Array<Record<string, unknown>>): Promise<Array<Record<string, unknown>>> {
  const names = new Map<string, string>()
  for (const line of lines) {
    const code = String(line.product_code || line.filingCode || line.declareCode || '').trim()
    const contract = String(line.contract || line.contract_no || '').trim()
    if (!code) continue
    const found = await searchScheduleProducts(props.factoryId, code)
    const candidates = found.filter((item) => item.product_name && (String(item.product_code || '').replace(/\s+/g, '') === code.replace(/\s+/g, '') || String(item.product_name).includes(code)))
    const hit = candidates.find((item) => contract && String(item.contract_no || '').trim() === contract) || candidates[0]
    if (hit?.product_name) names.set(`${contract}|${code}`, String(hit.product_name))
  }
  return lines.map((line) => {
    const code = String(line.product_code || line.filingCode || line.declareCode || '').trim()
    const contract = String(line.contract || line.contract_no || '').trim()
    const productName = productNameForCode(line.description || line.name || line.product_name || names.get(`${contract}|${code}`) || '', code)
    return { ...line, product_name: productName, name: productName, description: productName }
  })
}

async function importCabinet() {
  if (!detail.value) return
  const lines = detail.value.lines ?? []
  const contractSet = new Set(lines.map((line) => String((line as Record<string, unknown>).contract_no || (line as Record<string, unknown>).contract || '').trim()).filter(Boolean))
  let resolvedLines: Array<Record<string, unknown>> | null = null
  if (contractSet.size <= 1) {
    resolvedLines = await resolveValidatedScheduleLines(
      form.contractNo || String(detail.value.header?.contractNo || ''),
      lines as Array<Record<string, unknown>>,
      form.filingCode,
    )
    if (!resolvedLines) return
  } else {
    resolvedLines = await fillProductNames(lines as Array<Record<string, unknown>>)
    message.value = ''
  }
  const header = buildHeader()
  if (contractSet.size > 1) header.contractNo = [...contractSet][0]
  emit('import-cabinet', {
    taskId: detail.value.task_id,
    filename: detail.value.filename,
    header,
    lines: resolvedLines,
  })
  imported.value = { ...imported.value, [detail.value.id]: true }
  window.localStorage.setItem(importedKey(detail.value.id), '1')
  message.value = `已把 ${detail.value.filename} 的表头与明细导入柜货单。`
}

async function saveData() {
  if (!selectedDoc.value || !detail.value) return
  saving.value = true
  try {
    detail.value = await updateGeneratedDoc(props.factoryId, selectedDoc.value.id, buildHeader(), detail.value.lines ?? [])
    message.value = `已保存 ${selectedDoc.value.filename} 的资料。`
  } catch (error) {
    message.value = `保存失败：${getApiErrorMessage(error)}`
  } finally {
    saving.value = false
  }
}

async function importTruck(mode: 'buzzbee' | 'bulk') {
  if (!selectedDoc.value || !detail.value) return
  const lines = detail.value.lines ?? []
  const contractSet = new Set(lines.map((line) => String((line as Record<string, unknown>).contract_no || (line as Record<string, unknown>).contract || '').trim()).filter(Boolean))
  let resolvedLines: Array<Record<string, unknown>> | null = null
  const warehouseDoc = String(detail.value.header?.shipment_mode || '').toLowerCase() === 'warehouse'
  if (contractSet.size <= 1) {
    resolvedLines = await resolveValidatedScheduleLines(
      form.contractNo || String(detail.value.header?.contractNo || ''),
      lines as Array<Record<string, unknown>>,
      form.filingCode,
    )
    if (!resolvedLines) {
      if (!warehouseDoc) return
      resolvedLines = await fillProductNames(lines as Array<Record<string, unknown>>)
      message.value = ''
    }
  } else {
    resolvedLines = await fillProductNames(lines as Array<Record<string, unknown>>)
    message.value = ''
  }
  const header = buildHeader()
  if (contractSet.size > 1) header.contractNo = [...contractSet][0]
  emit('import-truck', {
    mode,
    taskId: detail.value.task_id,
    filename: detail.value.filename,
    header,
    lines: resolvedLines,
  })
  markImported(detail.value.id)
  message.value = `已把 ${detail.value.filename} 导到${mode === 'buzzbee' ? '运输公司派车' : '盐田散货W车'}。`
}

function onFieldChange(key: string) {
  if (key === 'filingCode') void onFilingCodeChange()
  if (key === 'contractNo') void onContractChange()
}

async function onContractChange() {
  const contract = String(form.contractNo || '').trim()
  if (!contract) return
  lookupWarning.value = ''
  try {
    const items = await searchScheduleProducts(props.factoryId, contract)
    const matched = items.find((item) => String(item.contract_no || '').trim().toLowerCase() === contract.toLowerCase())
    if (!matched) {
      if (String(form.filingCode || '').trim()) {
        await onFilingCodeChange()
        if (String(form.contractNo || '').trim()) return
      }
      lookupWarning.value = `未找到合同号 ${contract} 对应的厂区总排期`
      if (selectedDoc.value) docIssues.value = { ...docIssues.value, [selectedDoc.value.id]: true }
      return
    }
    if (!String(form.poNo || '').trim()) form.poNo = String(matched.customer_po || '')
    if (!form.filingCode) form.filingCode = String(matched.product_code || '')
    if (!String(form.brandNote || '').trim() && matched.brand) form.brandNote = String(matched.brand)
    if (!String(form.brandName || '').trim() && matched.brand) form.brandName = String(matched.brand)
    if (selectedDoc.value) {
      const next = { ...docIssues.value }
      delete next[selectedDoc.value.id]
      docIssues.value = next
    }
    message.value = `已按合同号 ${contract} 带出 PO（箱唛）和品牌。`
  } catch (error) {
    lookupWarning.value = `合同号 ${contract} 识别失败：${getApiErrorMessage(error)}`
  }
}

async function onFilingCodeChange() {
  const code = String(form.filingCode || '').trim()
  if (!code) return
  try {
    const items = await searchScheduleProducts(props.factoryId, code)
    const item = items[0]
    if (!item) {
      message.value = `未找到备案货号 ${code} 对应的业务排期`
      return
    }
    form.contractNo = String(item.contract_no || '')
    if (!String(form.poNo || '').trim()) form.poNo = String(item.customer_po || '')
    if (!String(form.brandNote || '').trim() && item.brand) form.brandNote = String(item.brand)
    if (!String(form.brandName || '').trim() && item.brand) form.brandName = String(item.brand)
    form.soNo = String(item.so_number || form.soNo || '')
    form.country = String(item.country || form.country || '')
    message.value = `已按备案货号 ${code} 带出合同号、PO、SO。`
  } catch (error) {
    message.value = `识别备案货号失败：${getApiErrorMessage(error)}`
  }
}

async function importTruckDoc(doc: GeneratedDoc) {
  try {
    const data = await getGeneratedDoc(props.factoryId, doc.id)
    const resolvedLines = await resolveValidatedScheduleLines(
      String(data.header?.contractNo || ''),
      (data.lines ?? []) as Array<Record<string, unknown>>,
      String(data.header?.filingCode || ''),
    )
    if (!resolvedLines) return
    emit('import-truck', {
      mode: 'bulk',
      taskId: data.task_id,
      filename: data.filename,
      header: data.header ?? {},
      lines: resolvedLines,
    })
    markImported(data.id)
    message.value = `已把 ${doc.filename} 导入盐田散货W车。`
  } catch (error) {
    message.value = `导入失败：${getApiErrorMessage(error)}`
  }
}

function exportEmail() {
  if (!selectedDoc.value || !detail.value) return
  const subject = form.subject || `${props.module === 'truck' ? 'Truck' : 'Shipment'} Advice ${form.soNo || form.contractNo || ''}`.trim()
  const lines = detail.value.lines ?? []
  const summary = lines.map((line) => {
    const row = line as Record<string, unknown>
    return `- ${String(row.product_code || row.filingCode || '')} | ${String(row.product_name || row.description || '')} | qty ${String(row.quantity ?? '')} | ctns ${String(row.cartons ?? '')}`
  }).join('\n')
  const body = [
    `合同号: ${form.contractNo || ''}`,
    `订单号: ${form.orderNo || ''}`,
    `备案货号: ${form.filingCode || ''}`,
    `PO（箱唛）: ${form.poNo || ''}`,
    `SO: ${form.soNo || ''}`,
    `订舱号: ${form.bookingNo || ''}`,
    `船名: ${form.vesselName || ''}`,
    `航次: ${form.voyageNo || ''}`,
    `运输公司: ${form.transportCompany || ''}`,
    `截单日期: ${form.sailingDate || form.cutoff || ''}`,
    `装货港: ${form.originPort || ''}`,
    `出口国家: ${form.country || ''}`,
    '',
    '明细:',
    summary,
  ].join('\n')
  const eml = [
    `From: ${form.shipper || 'shipping@example.com'}`,
    `To: ${form.consignee || 'customer@example.com'}`,
    `Subject: ${subject}`,
    `Date: ${new Date().toUTCString()}`,
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=UTF-8',
    '',
    body,
  ].join('\r\n')
  const blob = new Blob([eml], { type: 'message/rfc822' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${selectedDoc.value.filename.replace(/\.[^.]+$/, '')}_邮件资料.eml`
  link.click()
  URL.revokeObjectURL(url)
  message.value = `已导出邮件 ${link.download}`
}

async function exportEmailDoc(doc: GeneratedDoc) {
  try {
    const data = await getGeneratedDoc(props.factoryId, doc.id)
    const header = data.header ?? {}
    const lines = data.lines ?? []
    const value = (key: string) => String(header[key] ?? '').trim()
    const subject = doc.email_name?.trim() || `Shipment Advice ${value('soNo') || value('contractNo')}`
    const summary = lines.map((line) => {
      const row = line as Record<string, unknown>
      return `- ${String(row.product_code || row.filingCode || '')} | ${String(row.product_name || row.description || '')} | qty ${String(row.quantity ?? '')} | ctns ${String(row.cartons ?? '')}`
    }).join('\n')
    const body = [
      `合同号: ${value('contractNo')}`,
      `订单号: ${value('orderNo')}`,
      `备案货号: ${value('filingCode')}`,
      `PO（箱唛）: ${value('poNo')}`,
      `SO: ${value('soNo')}`,
      `订舱号: ${value('bookingNo')}`,
      `截单日期: ${value('sailingDate') || value('cutoff')}`,
      `出口国家: ${value('destinationCountry') || value('country')}`,
      '', '明细:', summary,
    ].join('\n')
    const eml = [
      `From: ${value('shipper') || 'shipping@example.com'}`,
      `To: ${value('consignee') || 'customer@example.com'}`,
      `Subject: ${subject}`,
      `Date: ${new Date().toUTCString()}`,
      'MIME-Version: 1.0',
      'Content-Type: text/plain; charset=UTF-8',
      '', body,
    ].join('\r\n')
    const url = URL.createObjectURL(new Blob([eml], { type: 'message/rfc822' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `${subject}.eml`
    link.click()
    URL.revokeObjectURL(url)
    message.value = `已导出邮件 ${link.download}`
  } catch (error) {
    message.value = `导出邮件失败：${getApiErrorMessage(error)}`
  }
}

function askDelete(doc: GeneratedDoc) {
  pendingId.value = doc.id
  window.setTimeout(() => {
    if (pendingId.value === doc.id) pendingId.value = ''
  }, 5000)
}

async function confirmDelete(doc: GeneratedDoc) {
  busyId.value = doc.id
  try {
    await deleteGeneratedDoc(props.factoryId, doc.id)
    pendingId.value = ''
    selectedId.value = ''
    await load()
  } catch (error) {
    message.value = `删除失败：${getApiErrorMessage(error)}`
  } finally {
    busyId.value = ''
  }
}

onMounted(load)
watch(() => props.factoryId, load)
watch(
  () => `${form.transportCompany || ''}|${form.originPort || ''}`,
  (current, previous) => {
    if (!detail.value || current === previous) return
    const cleanTransport = String(form.transportCompany || '').trim().replace(/[，,\s]+$/, '')
    const carrier = cleanTransport ? (cleanTransport.endsWith('运输') ? cleanTransport : `${cleanTransport}运输`) : ''
    const port = String(form.originPort || '').trim()
    form.tableName = carrier && port ? `${carrier}，出${port}` : (port ? `出${port}` : carrier)
  },
)
</script>

<template>
  <section class="rounded-xl border border-emerald-100/80 bg-white" aria-label="自动生成文件">
    <header class="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
      <div class="flex items-center gap-2">
        <FileSpreadsheet class="size-4 text-emerald-600" aria-hidden="true" />
        <h3 class="text-[13px] font-bold text-slate-800">{{ heading || (isSo ? '邮件信息资料' : `已自动生成${label ? ` · ${label}` : ''}`) }}</h3>
        <span class="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold tabular-nums text-emerald-700">{{ docs.length }}</span>
      </div>
      <div class="flex items-center gap-2">
        <label v-if="docs.length" class="inline-flex items-center gap-1 text-[10px] font-medium text-slate-500">
          <input type="checkbox" aria-label="全选生成文件" :checked="allDocsSelected" @change="onToggleAllDocs">
          全选
        </label>
        <button
          type="button"
          class="inline-flex h-7 items-center gap-1 rounded border px-2 text-[11px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-40"
          :class="bulkDeleteArmed ? 'border-rose-300 bg-rose-50 text-rose-700' : 'border-rose-200 text-rose-600 hover:bg-rose-50'"
          :disabled="!selectedDocIds.length || bulkDeleting"
          @click="bulkDeleteDocs"
        >
          <Trash2 class="size-3" />{{ bulkDeleteArmed ? `确认删除 ${selectedDocIds.length} 份` : `删除${selectedDocIds.length ? ` (${selectedDocIds.length})` : ''}` }}
        </button>
        <button
          v-if="bulkDeleteArmed"
          type="button"
          class="inline-flex h-7 items-center rounded border border-slate-200 px-2 text-[11px] font-semibold text-slate-600 hover:bg-slate-50"
          @click="bulkDeleteArmed = false"
        >取消删除</button>
        <button type="button" class="inline-flex h-7 items-center gap-1 rounded border border-slate-200 px-2 text-[11px] text-slate-600" @click="load">
          <RefreshCw class="size-3" :class="loading ? 'animate-spin' : ''" />刷新
        </button>
      </div>
    </header>

    <p v-if="message" class="break-all px-4 py-2 text-[11px]" :class="message.startsWith('已') ? 'text-emerald-700' : 'text-rose-600'">{{ message }}</p>

    <template v-if="!compact && docs.length">
      <div v-if="docs.length > 0" class="flex flex-wrap gap-2 border-b border-slate-100 px-4 py-2">
        <div v-for="doc in docs" :key="doc.id" class="inline-flex max-w-full items-center gap-1.5 rounded-lg border px-2 py-1 text-[11px]" :class="doc.id === selectedId ? 'border-emerald-400 bg-emerald-50 ring-2 ring-emerald-400/30' : 'border-slate-200'">
          <input type="checkbox" :aria-label="`选择 ${attachmentLabel(doc)}`" :checked="selectedDocIds.includes(doc.id)" @change="toggleDoc(doc.id)">
          <button type="button" class="inline-flex max-w-full items-center gap-1.5" :class="doc.id === selectedId ? 'text-emerald-800' : 'text-slate-600'" @click="selectDoc(doc)">
            <span v-if="!isImported(doc) || attachmentIssue(doc)" class="size-1.5 shrink-0 rounded-full bg-rose-500"></span>
            <span class="truncate" :title="doc.filename">{{ attachmentLabel(doc) }}</span>
          </button>
        </div>
      </div>

      <div v-if="selectedDoc" class="p-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2 text-[11px] font-semibold text-slate-700">
            <input v-if="docs.length === 1" type="checkbox" :aria-label="`选择 ${displayName(selectedDoc)}`" :checked="selectedDocIds.includes(selectedDoc.id)" @change="toggleDoc(selectedDoc.id)">
            <span v-if="!isImported(selectedDoc)" class="size-2 rounded-full bg-rose-500" aria-label="待确认柜货单"></span>
            <span class="truncate" :title="selectedDoc.filename">{{ attachmentLabel(selectedDoc) }}</span>
          </div>
          <span class="text-[10px] text-slate-400 tabular-nums">{{ selectedDoc.created_at.replace('T', ' ') }}</span>
        </div>

        <p v-if="lookupWarning" class="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] font-semibold text-rose-700" role="alert">
          {{ lookupWarning }}
        </p>

        <div class="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <label v-for="field in displayFields" :key="field.key" class="block">
            <span class="mb-0.5 flex items-center gap-1 text-[9px] font-medium text-slate-400">
              {{ field.label }}
              <span class="rounded bg-slate-100 px-1 py-0.5 text-[8px] text-slate-500">{{ field.hint }}</span>
            </span>
            <select
              v-if="field.type === 'select'"
              v-model="form[field.key]"
              class="h-8 w-full rounded-md border border-slate-200 bg-slate-50 px-2 text-[11px] text-slate-800 outline-none focus:border-emerald-400"
            >
              <option v-for="option in field.options ?? []" :key="option" :value="option">{{ option }}</option>
            </select>
            <input
              v-else
              v-model="form[field.key]"
              :type="field.type === 'date' ? 'date' : 'text'"
              :placeholder="field.hint === '手动' ? '装柜后补录' : ''"
              class="h-8 w-full rounded-md border border-slate-200 bg-slate-50 px-2 text-[11px] text-slate-800 outline-none placeholder:text-slate-300 focus:border-emerald-400"
              @change="onFieldChange(field.key)"
            >
          </label>
        </div>

        <div class="mt-2 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-2">
          <button
            v-if="isSo"
            type="button"
            class="inline-flex h-7 items-center gap-1 rounded-md px-2.5 text-[10px] font-semibold text-white disabled:opacity-50"
            :class="isImported(selectedDoc) ? 'bg-emerald-600' : 'bg-rose-600'"
            :disabled="busyId === selectedDoc.id || loadingDetail"
            @click="importCabinet"
          >
            {{ isImported(selectedDoc) ? '已导入柜表' : '导入柜表' }}
          </button>
          <button
            v-else
            type="button"
            class="inline-flex h-7 items-center gap-1 rounded-md bg-emerald-600 px-3 text-[10px] font-semibold text-white disabled:opacity-50"
            :disabled="loadingDetail"
            @click="importTruck('bulk')"
          >导入盐田散货W车</button>
          <a :href="downloadUrl(selectedDoc)" :download="downloadName(selectedDoc)" target="_blank" rel="noopener" class="inline-flex h-7 items-center gap-1 rounded-md border border-emerald-200 px-2.5 text-[10px] font-semibold text-emerald-700">
            <Download class="size-3" />下载
          </a>
          <button type="button" class="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 px-2.5 text-[10px] font-semibold text-slate-700" :disabled="!detail" @click="exportEmail">
            <Mail class="size-3" />导出邮件
          </button>
          <button type="button" class="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 px-2.5 text-[10px] font-semibold text-slate-600" @click="showDetail = !showDetail">
            <ChevronDown class="size-3" :class="showDetail ? 'rotate-180' : ''" />打开详情信息
          </button>
          <button
            v-if="pendingId === selectedDoc.id"
            type="button"
            class="inline-flex h-7 items-center gap-1 rounded-md border border-rose-300 px-2.5 text-[10px] font-semibold text-rose-700 disabled:opacity-50"
            :disabled="busyId === selectedDoc.id"
            @click="confirmDelete(selectedDoc)"
          >
            <Trash2 class="size-3" />确认删除
          </button>
          <button v-else type="button" class="inline-flex h-7 items-center gap-1 rounded-md border border-rose-200 px-2.5 text-[10px] font-semibold text-rose-600" @click="askDelete(selectedDoc)">
            <Trash2 class="size-3" />删除
          </button>
        </div>

        <dl v-if="showDetail" class="mt-3 grid gap-2 rounded-lg bg-slate-50 p-3 text-[11px] text-slate-600 sm:grid-cols-2">
          <div><dt class="text-slate-400">文件名</dt><dd class="break-all font-medium text-slate-700">{{ selectedDoc.filename }}</dd></div>
          <div><dt class="text-slate-400">模块</dt><dd class="font-medium text-slate-700">{{ selectedDoc.module }}</dd></div>
          <div><dt class="text-slate-400">任务 ID</dt><dd class="break-all font-medium text-slate-700">{{ selectedDoc.task_id || '—' }}</dd></div>
          <div><dt class="text-slate-400">生成时间</dt><dd class="font-medium text-slate-700">{{ selectedDoc.created_at.replace('T', ' ') }}</dd></div>
          <div><dt class="text-slate-400">明细行数</dt><dd class="font-medium text-slate-700">{{ detail?.lines.length ?? 0 }}</dd></div>
        </dl>
      </div>
    </template>

    <template v-else>
      <div v-if="docs.length" class="divide-y divide-slate-100">
        <div v-for="doc in docs" :key="doc.id" class="flex flex-wrap items-center justify-between gap-2 px-4 py-1.5 text-[11px]">
          <span class="flex min-w-0 items-center gap-2">
            <input type="checkbox" :aria-label="`选择 ${displayName(doc)}`" :checked="selectedDocIds.includes(doc.id)" @change="toggleDoc(doc.id)">
            <span class="truncate font-semibold text-slate-700" :title="doc.filename">{{ displayName(doc) }}</span>
          </span>
          <span class="text-slate-400 tabular-nums">{{ doc.created_at.replace('T', ' ') }}</span>
          <div class="flex items-center gap-3">
            <a :href="downloadUrl(doc)" :download="downloadName(doc)" target="_blank" rel="noopener" class="inline-flex items-center gap-1 font-semibold text-emerald-700">
              <Download class="size-3" />下载
            </a>
            <button v-if="module === 'truck'" type="button" class="inline-flex items-center gap-1 font-semibold text-emerald-700" @click="importTruckDoc(doc)">导入</button>
            <button v-if="module === 'truck'" type="button" class="inline-flex items-center gap-1 font-semibold text-slate-600" @click="exportEmailDoc(doc)">导出邮件</button>
            <button
              v-if="pendingId === doc.id"
              type="button"
              class="inline-flex items-center gap-1 font-semibold text-rose-700 disabled:opacity-50"
              :disabled="busyId === doc.id"
              @click="confirmDelete(doc)"
            >
              <Trash2 class="size-3" />确认删除
            </button>
            <button v-else type="button" class="inline-flex items-center gap-1 font-semibold text-rose-600" @click="askDelete(doc)">
              <Trash2 class="size-3" />删除
            </button>
          </div>
        </div>
      </div>
      <p v-else class="px-4 py-3 text-[11px] text-slate-400">暂无自动生成文件；确认邮件后会自动生成。</p>
    </template>
  </section>
</template>
