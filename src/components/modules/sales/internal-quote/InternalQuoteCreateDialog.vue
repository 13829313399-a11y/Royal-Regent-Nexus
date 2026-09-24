<script setup lang="ts">
import { Building2, CheckCircle2, Copy, Eye, FileImage, FilePlus2, FileText, Plus, Snowflake, Trash2, X } from '@lucide/vue'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { internalQuoteSectionDefinitions } from '@/data/internalQuoteDeskConfig'
import InternalQuoteHistoryPicker from './InternalQuoteHistoryPicker.vue'
import type { ApiInternalQuoteHistoryProduct } from '@/api/internalQuote'
import type {
  InternalQuote,
  InternalQuoteBusinessOwner,
  InternalQuoteCreatePayload,
  InternalQuoteCreateProduct,
  InternalQuoteSectionCode,
} from '@/types/internalQuoteDesk'

const mandatorySectionCodes: InternalQuoteSectionCode[] = ['sales', 'engineering', 'assembly']
const mandatorySectionDefinitions = internalQuoteSectionDefinitions.filter((item) => mandatorySectionCodes.includes(item.code))
const optionalSectionDefinitions = internalQuoteSectionDefinitions.filter((item) => !mandatorySectionCodes.includes(item.code))

function normalizeParticipation(values: InternalQuoteSectionCode[]) {
  const selected = new Set([...mandatorySectionCodes, ...values])
  return internalQuoteSectionDefinitions.map((item) => item.code).filter((code) => selected.has(code))
}

const props = withDefaults(defineProps<{
  open: boolean
  mode: 'create' | 'clone'
  sourceQuote?: InternalQuote
  businessOwners: InternalQuoteBusinessOwner[]
  customers?: string[]
  busy?: boolean
  externalError?: string
  factoryId?: string
  factoryName?: string
  allowedInitiatorDepartments?: Array<'sales-business' | 'engineering'>
}>(), {
  factoryId: 'huaxing',
  factoryName: '华兴',
  customers: () => [],
  allowedInitiatorDepartments: () => ['sales-business', 'engineering'],
})

const emit = defineEmits<{
  close: []
  confirm: [payload: InternalQuoteCreatePayload]
}>()

const errorMessage = ref('')
const historyTarget = ref<{ kind: 'product' | 'component'; productIndex?: number; componentIndex?: number } | null>(null)
const documentPreview = ref<{ file: File; url: string; kind: 'image' | 'pdf' | 'file' } | null>(null)
type QuoteCreateForm = InternalQuoteCreatePayload & {
  quoteType: 'single' | 'series' | 'multi_region'
  products: InternalQuoteCreateProduct[]
}

const form = reactive<QuoteCreateForm>({
  quoteNo: '',
  productName: '',
  customer: '',
  versionLabel: 'V1.0',
  initiatorDepartment: 'sales-business',
  businessOwnerId: '',
  businessOwner: '',
  targetCustomerPrice: '无',
  quantity: 10000,
  targetDate: '2026-08-30',
  remark: '',
  participatingSections: [...mandatorySectionCodes],
  quoteType: 'single',
  products: [{ productName: '', quantity: 10000, regionCode: '', imageFile: null, documentFiles: [] }],
})
const selectedDepartmentDefinitions = computed(() => internalQuoteSectionDefinitions.filter((item) => (
  normalizeParticipation(form.participatingSections).includes(item.code)
)))

const title = computed(() => props.mode === 'clone' ? '复制内部报价' : '新建内部报价')
const customerOptions = computed(() => Array.from(new Set([
  ...(props.sourceQuote?.customer ? [props.sourceQuote.customer] : []),
  ...props.customers,
])))
const isJustPlay = computed(() => (
  props.mode === 'create'
  && String(props.factoryId).trim().toLowerCase().replace(/[\s_-]+/g, '') === 'huakangb'
  && String(form.customer).trim().toLowerCase().replace(/[\s_-]+/g, '') === 'justplay'
))

function initializeProductComponents() {
  for (const product of form.products) {
    if (!isJustPlay.value) product.componentImageFiles = undefined
    product.pricingComponents = isJustPlay.value
      ? [...(product.pricingComponents?.length ? product.pricingComponents : form.products[0]?.pricingComponents ?? ['主体', '配件1'])]
      : undefined
  }
}

watch(isJustPlay, initializeProductComponents, { immediate: true })
watch(() => form.customer, () => {
  historyTarget.value = null
  for (const product of form.products) {
    product.historySource = undefined
    product.componentSources = undefined
  }
})

watch(() => [props.open, props.mode, props.sourceQuote?.id, props.businessOwners[0]?.id, props.customers[0]] as const, ([open]) => {
  closeDocumentPreview()
  historyTarget.value = null
  if (!open) return
  errorMessage.value = ''
  if (props.mode === 'clone' && props.sourceQuote) {
    const selectedOwner = props.businessOwners.find((item) => item.id === props.sourceQuote?.businessOwnerId)
      ?? props.businessOwners[0]
    Object.assign(form, {
      quoteNo: `${props.sourceQuote.quoteNo}-COPY`,
      productName: props.sourceQuote.productName,
      customer: props.sourceQuote.customer,
      versionLabel: 'V1.0',
      initiatorDepartment: props.sourceQuote.initiatorDepartment,
      businessOwnerId: selectedOwner?.id ?? '',
      businessOwner: selectedOwner?.displayName ?? '',
      targetCustomerPrice: props.sourceQuote.targetCustomerPrice,
      quantity: props.sourceQuote.quantity,
      targetDate: props.sourceQuote.targetDate,
      remark: `复制自 ${props.sourceQuote.quoteNo} ${props.sourceQuote.versionLabel}`,
      participatingSections: normalizeParticipation(
        props.sourceQuote.sections.filter((section) => section.isRequired).map((section) => section.code),
      ),
      quoteType: 'single',
      products: [{
        productName: props.sourceQuote.productName,
        quantity: props.sourceQuote.quantity,
        regionCode: props.sourceQuote.regionCode,
        imageFile: null,
        documentFiles: [],
      }],
    })
    return
  }
  Object.assign(form, {
    quoteNo: '',
    productName: '',
    customer: props.customers[0] ?? '',
    versionLabel: 'V1.0',
    initiatorDepartment: props.allowedInitiatorDepartments[0] ?? 'sales-business',
    businessOwnerId: props.businessOwners[0]?.id ?? '',
    businessOwner: props.businessOwners[0]?.displayName ?? '',
    targetCustomerPrice: '无',
    quantity: 10000,
    targetDate: '2026-08-30',
    remark: '',
    participatingSections: [...mandatorySectionCodes],
    quoteType: 'single',
    products: [{ productName: '', quantity: 10000, regionCode: '', imageFile: null, documentFiles: [] }],
  })
  initializeProductComponents()
}, { immediate: true })

function submit() {
  errorMessage.value = ''
  if (props.mode === 'create' && !props.allowedInitiatorDepartments.includes(form.initiatorDepartment)) {
    errorMessage.value = '当前账号不能以所选部门发起内部报价。'
    return
  }
  if (!form.quoteNo.trim() || !form.customer.trim()) {
    errorMessage.value = '请填写报价号、产品名称和客户。'
    return
  }
  if (!form.products.length || form.products.length > 20
    || form.products.some((product) => !product.productName.trim())) {
    errorMessage.value = '请填写 1 至 20 款产品的名称。'
    return
  }
  if (props.mode === 'create' && !props.customers.includes(form.customer)) {
    errorMessage.value = '请选择当前厂区客户资料中的客户。'
    return
  }
  if (!form.businessOwnerId || !form.businessOwner.trim()) {
    errorMessage.value = '业务部和工程部建单时都必须指定业务负责人。'
    return
  }
  if (!props.businessOwners.some((item) => item.id === form.businessOwnerId)) {
    errorMessage.value = '请选择当前厂区具备整单审核权限的业务部人员。'
    return
  }
  if (!form.targetCustomerPrice.trim()) {
    errorMessage.value = '请填写客人目标价；客人未提供时请填写“无”。'
    return
  }
  if (form.products.some((product) => !Number.isFinite(Number(product.quantity)) || Number(product.quantity) <= 0)) {
    errorMessage.value = '每款产品的出货数量都必须大于 0。'
    return
  }
  if (isJustPlay.value) {
    for (const [index, product] of form.products.entries()) {
      const componentNames = (product.pricingComponents ?? []).map((name) => name.trim())
      if (!componentNames.length || componentNames.length > 50 || componentNames.some((name) => !name || name.length > 64)) {
        errorMessage.value = `第 ${index + 1} 款必须填写主体及配件名称；最多 49 个配件，每个名称不超过 64 个字符。`
        return
      }
      if (componentNames.length !== new Set(componentNames.map((name) => name.toLocaleLowerCase())).size) {
        errorMessage.value = `第 ${index + 1} 款的 JustPlay 分项名称不能重复。`
        return
      }
      product.pricingComponents = componentNames
    }
  }
  const participating = new Set(normalizeParticipation(form.participatingSections))
  if (form.products.some((product) => (product.documentFiles ?? []).some((document) => !participating.has(document.department)))) {
    errorMessage.value = '产品资料必须分配给本次参与报价的部门。'
    return
  }
  const normalizedProducts = form.products.map((product) => ({
    ...product,
    productName: product.productName.trim(),
    quantity: Number(product.quantity),
    imageFile: isJustPlay.value ? null : product.imageFile,
    componentImageFiles: isJustPlay.value ? product.componentImageFiles : undefined,
    pricingComponents: isJustPlay.value ? [...(product.pricingComponents ?? [])] : undefined,
    componentSources: isJustPlay.value && product.componentSources
      ? (product.pricingComponents ?? []).map((_, index) => product.componentSources?.[index] ?? null) : undefined,
  }))
  emit('confirm', {
    ...form,
    productName: normalizedProducts[0]!.productName,
    quantity: normalizedProducts[0]!.quantity,
    products: normalizedProducts,
    pricingComponents: isJustPlay.value ? [...(normalizedProducts[0]?.pricingComponents ?? [])] : [],
    participatingSections: normalizeParticipation(form.participatingSections),
  })
}

function selectBusinessOwner() {
  const selected = props.businessOwners.find((item) => item.id === form.businessOwnerId)
  form.businessOwner = selected?.displayName ?? ''
}

function changeQuoteType() {
  const first = form.products[0] ?? { productName: '', quantity: 10000, regionCode: '' as const, imageFile: null, documentFiles: [] }
  if (form.quoteType === 'single') {
    form.products = [{ ...first, regionCode: '' }]
    return
  }
  if (form.quoteType === 'multi_region') {
    const baseName = first.productName.replace(/—(?:大陆价|印尼价)$/, '') || '产品名'
    form.products = [
      { ...first, productName: `${baseName}—大陆价`, regionCode: 'mainland' },
      { productName: `${baseName}—印尼价`, quantity: first.quantity, regionCode: 'indonesia', imageFile: null, documentFiles: [],
        pricingComponents: isJustPlay.value ? [...(first.pricingComponents ?? ['主体', '配件1'])] : undefined },
    ]
    return
  }
  form.products = form.products.map((product) => ({ ...product, regionCode: '' }))
}

function addProduct() {
  if (form.products.length >= 20 || form.quoteType !== 'series') return
  form.products.push({ productName: '', quantity: form.products[0]?.quantity ?? 10000, regionCode: '', imageFile: null, documentFiles: [],
    pricingComponents: isJustPlay.value ? [...(form.products[0]?.pricingComponents ?? ['主体', '配件1'])] : undefined })
}

function removeProduct(index: number) {
  if (form.products.length <= 1 || form.quoteType !== 'series') return
  form.products.splice(index, 1)
}

function addPricingComponent(productIndex: number) {
  const components = form.products[productIndex]?.pricingComponents
  if (!isJustPlay.value || !components || components.length >= 50) return
  let suffix = components.length
  while (components.some((name) => name.trim() === `配件${suffix}`)) suffix += 1
  components.push(`配件${suffix}`)
  form.products[productIndex]?.componentSources?.push(null)
}

function removePricingComponent(productIndex: number, componentIndex: number) {
  if (!isJustPlay.value || componentIndex === 0) return
  form.products[productIndex]?.pricingComponents?.splice(componentIndex, 1)
  form.products[productIndex]?.componentImageFiles?.splice(componentIndex, 1)
  form.products[productIndex]?.componentSources?.splice(componentIndex, 1)
}

function changeAccessoryCount(productIndex: number, event: Event) {
  const count = Number((event.target as HTMLSelectElement).value)
  const components = form.products[productIndex]?.pricingComponents
  if (!isJustPlay.value || !components || !Number.isInteger(count) || count < 0 || count > 49) return
  if (components.length > count + 1) components.splice(count + 1)
  form.products[productIndex]?.componentImageFiles?.splice(count + 1)
  form.products[productIndex]?.componentSources?.splice(count + 1)
  while (components.length < count + 1) addPricingComponent(productIndex)
}

function historySelection(product: ApiInternalQuoteHistoryProduct, componentId?: string) {
  const component = product.components.find(item => item.id === componentId)
  const region = product.region_code === 'mainland' ? '大陆价' : product.region_code === 'indonesia' ? '印尼价' : '未分地区'
  return { quote_id: product.quote_id, fingerprint: product.fingerprint, component_id: componentId,
    label: `${product.quote_no} / ${product.version_label} / ${region} / ${product.product_name}${component ? ` / ${component.name}` : ''}` }
}

function acceptHistory(items: Array<{ product: ApiInternalQuoteHistoryProduct; componentId?: string }>) {
  const target = historyTarget.value
  if (!target) return
  errorMessage.value = ''
  if (target.kind === 'product') {
    const emptyFirst = form.products.length === 1 && !form.products[0]?.productName.trim()
      && !form.products[0]?.historySource && !form.products[0]?.componentSources?.some(Boolean)
      && !form.products[0]?.imageFile && !form.products[0]?.documentFiles?.length
      && !form.products[0]?.componentImageFiles?.some(Boolean)
    const newCount = target.productIndex !== undefined ? form.products.length : form.products.length - Number(emptyFirst) + items.length
    if (newCount > 20) { errorMessage.value = '一批报价最多 20 款，请减少选择。'; historyTarget.value = null; return }
    if (items.some(({ product }) => isJustPlay.value && !product.components.length)) {
      errorMessage.value = '所选历史 JustPlay 产品尚未建立分项，请先完善原产品分项。'; historyTarget.value = null; return
    }
    const added = items.map(({ product }): InternalQuoteCreateProduct => ({ productName: product.product_name, quantity: product.qty,
      regionCode: target.productIndex !== undefined && form.quoteType === 'multi_region' ? form.products[target.productIndex]!.regionCode : product.region_code,
      imageFile: null, documentFiles: [], historySource: historySelection(product),
      pricingComponents: isJustPlay.value ? product.components.map(c => c.name) : undefined,
      componentSources: isJustPlay.value ? product.components.map(c => historySelection(product, c.id)) : undefined,
    }))
    if (target.productIndex !== undefined) form.products.splice(target.productIndex, 1, added[0]!)
    else { if (emptyFirst) form.products.splice(0, 1); form.products.push(...added) }
    if (form.quoteType === 'single' && form.products.length > 1) form.quoteType = 'series'
  } else {
    const product = form.products[target.productIndex!]
    if (!product?.pricingComponents) return
    const names = product.pricingComponents
    if (target.componentIndex === undefined && names.length + items.length > 50) {
      errorMessage.value = '每款最多 1 个主体和 49 个配件。'; historyTarget.value = null; return
    }
    product.componentSources ??= names.map(() => null)
    product.componentImageFiles ??= names.map(() => null)
    for (const item of items) {
      const name = item.product.components.find(c => c.id === item.componentId)?.name ?? '配件'
      const index = target.componentIndex ?? names.length
      let unique = name
      let suffix = 2
      while (names.some((current, i) => i !== index && current.trim().toLowerCase() === unique.toLowerCase())) unique = `${name.slice(0, 57)} (${suffix++})`
      names[index] = unique
      product.componentSources[index] = historySelection(item.product, item.componentId)
      product.componentImageFiles[index] = null
    }
  }
  form.participatingSections = normalizeParticipation([...form.participatingSections, ...items.flatMap(item => (
    item.componentId ? item.product.component_sections?.[item.componentId] ?? item.product.participating_sections
      : item.product.participating_sections
  ))])
  historyTarget.value = null
}

function clearHistory(product: InternalQuoteCreateProduct) {
  product.historySource = undefined
  product.componentSources = undefined
}

function selectProductImage(index: number, event: Event) {
  const input = event.target as HTMLInputElement
  const product = form.products[index]
  if (product) product.imageFile = input.files?.[0] ?? null
}

function selectComponentImage(productIndex: number, componentIndex: number, event: Event) {
  const input = event.target as HTMLInputElement
  const product = form.products[productIndex]
  if (!product) return
  const images = product.componentImageFiles ?? (product.componentImageFiles = [])
  images[componentIndex] = input.files?.[0] ?? null
}

function selectProductDocuments(index: number, event: Event) {
  const input = event.target as HTMLInputElement
  const product = form.products[index]
  if (!product) return
  const existing = product.documentFiles ?? (product.documentFiles = [])
  for (const file of Array.from(input.files ?? [])) {
    if (existing.some((item) => item.file.name === file.name && item.file.size === file.size)) continue
    existing.push({ file, department: 'engineering' })
  }
  input.value = ''
}

function removeProductDocument(productIndex: number, documentIndex: number) {
  form.products[productIndex]?.documentFiles?.splice(documentIndex, 1)
}

function closeDocumentPreview() {
  if (documentPreview.value?.url) URL.revokeObjectURL(documentPreview.value.url)
  documentPreview.value = null
}

function openDocumentPreview(file: File) {
  closeDocumentPreview()
  const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
  const kind = ['jpg', 'jpeg', 'png', 'webp'].includes(extension)
    ? 'image'
    : extension === 'pdf' ? 'pdf' : 'file'
  documentPreview.value = {
    file,
    url: kind === 'file' ? '' : URL.createObjectURL(file),
    kind,
  }
}

onBeforeUnmount(closeDocumentPreview)
</script>

<template>
  <Teleport to="body">
    <Transition name="quote-dialog">
      <div v-if="open" class="quote-dialog-backdrop" role="presentation" @mousedown.self="emit('close')">
        <section class="quote-dialog" role="dialog" aria-modal="true" :aria-label="title">
          <header class="quote-dialog-head">
            <div class="quote-dialog-heading">
              <span class="quote-dialog-icon">
                <Copy v-if="mode === 'clone'" aria-hidden="true" />
                <FilePlus2 v-else aria-hidden="true" />
              </span>
              <div>
                <h2>{{ title }}</h2>
                <p>业务部与工程部均可发起；固定部门自动参与，其余部门按本次报价范围选择。</p>
              </div>
            </div>
            <button type="button" class="quote-icon-button" aria-label="关闭" @click="emit('close')">
              <X aria-hidden="true" />
            </button>
          </header>

          <div class="quote-dialog-body">
            <div v-if="mode === 'clone' && sourceQuote" class="quote-copy-note">
              <Copy aria-hidden="true" />
              <span>整单复制 {{ sourceQuote.quoteNo }} {{ sourceQuote.versionLabel }} 的报价头、全部部门明细和参考快照；审核及导出状态会清零。</span>
            </div>

            <fieldset class="quote-department-choice">
              <legend>发起部门</legend>
              <label :class="{ active: form.initiatorDepartment === 'sales-business', disabled: !allowedInitiatorDepartments.includes('sales-business') }">
                <input v-model="form.initiatorDepartment" type="radio" value="sales-business" :disabled="!allowedInitiatorDepartments.includes('sales-business')">
                <span class="quote-choice-check"><CheckCircle2 aria-hidden="true" /></span>
                <strong>业务部建单</strong>
                <small>维护报价头及业务部内容，保存完整后直接输出</small>
              </label>
              <label :class="{ active: form.initiatorDepartment === 'engineering', disabled: !allowedInitiatorDepartments.includes('engineering') }">
                <input v-model="form.initiatorDepartment" type="radio" value="engineering" :disabled="!allowedInitiatorDepartments.includes('engineering')">
                <span class="quote-choice-check"><CheckCircle2 aria-hidden="true" /></span>
                <strong>工程部建单</strong>
                <small>发起工程核价，并指定业务负责人</small>
              </label>
            </fieldset>

            <fieldset v-if="mode === 'create'" class="quote-type-choice">
              <legend>报价类型</legend>
              <label :class="{ active: form.quoteType === 'single' }">
                <input v-model="form.quoteType" type="radio" value="single" @change="changeQuoteType">
                <strong>单款报价</strong><small>仅建立一款产品</small>
              </label>
              <label :class="{ active: form.quoteType === 'series' }">
                <input v-model="form.quoteType" type="radio" value="series" @change="changeQuoteType">
                <strong>系列多款</strong><small>同批最多 20 款</small>
              </label>
              <label :class="{ active: form.quoteType === 'multi_region' }">
                <input v-model="form.quoteType" type="radio" value="multi_region" @change="changeQuoteType">
                <strong>多地区报价</strong><small>默认大陆价与印尼价</small>
              </label>
            </fieldset>

            <div class="quote-form-grid">
              <label>
                <span>报价号 / 货号 <b>*</b></span>
                <input v-model="form.quoteNo" type="text" placeholder="例如 IQ-HX-2026-0716-06">
              </label>
              <label>
                <span>版本标签 <b>*</b></span>
                <input v-model="form.versionLabel" type="text" placeholder="V1.0">
              </label>
              <label>
                <span>客户 <b>*</b></span>
                <select v-model="form.customer">
                  <option value="" disabled>{{ customerOptions.length ? '选择客户' : '当前厂区暂无客户' }}</option>
                  <option v-for="customer in customerOptions" :key="customer" :value="customer">{{ customer }}</option>
                </select>
                <small v-if="!customerOptions.length" class="quote-owner-hint">请联系本厂业务主管或工程主管先维护客户资料。</small>
              </label>
              <label>
                <span>业务负责人（仅业务部） <b>*</b></span>
                <select v-model="form.businessOwnerId" :disabled="!businessOwners.length" @change="selectBusinessOwner">
                  <option value="" disabled>{{ businessOwners.length ? '选择业务负责人' : '当前厂区暂无具备审核权限的业务部人员' }}</option>
                  <option v-for="owner in businessOwners" :key="owner.id" :value="owner.id">{{ owner.displayName }}（{{ owner.username }}）</option>
                </select>
                <small class="quote-owner-hint">新报价无需人工审核；资料保存完整后可直接输出，并保留版本。</small>
              </label>
              <label>
                <span>客人目标价 <b>*</b></span>
                <input v-model="form.targetCustomerPrice" type="text" maxlength="128" placeholder="例如 USD 3.50；没有请填无">
              </label>
              <label>
                <span>预计完成日期</span>
                <input v-model="form.targetDate" type="date">
              </label>
              <label class="wide">
                <span>备注</span>
                <textarea v-model="form.remark" rows="2" placeholder="记录客户要求、报价范围或版本说明" />
              </label>
            </div>

            <section class="quote-product-list">
              <div class="quote-product-list-head">
                <div><strong>产品清单</strong><span>{{ isJustPlay ? '每款独立设置配件；新增产品默认复制当前第 1 款的配件个数和名称，之后互不影响。' : '第 1 款为基准款；创建后可把整份部门报价复制到其他款。' }}</span></div>
                <div class="quote-component-actions">
                  <button v-if="mode === 'create' && form.quoteType !== 'multi_region'" type="button" :disabled="busy" @click="historyTarget = { kind: 'product' }"><Copy />引用历史产品</button>
                  <button v-if="form.quoteType === 'series'" type="button" :disabled="form.products.length >= 20" @click="addProduct"><Plus />新增产品</button>
                </div>
              </div>
              <div class="quote-product-rows">
                <article v-for="(product, index) in form.products" :key="index" class="quote-product-row">
                  <span class="quote-product-number">{{ String(index + 1).padStart(2, '0') }}</span>
                  <label class="quote-product-name"><span>产品名称 <b>*</b></span><input v-model="product.productName" type="text" :placeholder="index === 0 ? '填写基准款名称' : `填写第 ${index + 1} 款名称`"></label>
                  <label><span>出货数量 <b>*</b></span><input v-model.number="product.quantity" type="number" min="1" step="1"></label>
                  <div class="quote-product-assets">
                    <div class="quote-product-asset-pickers">
                      <label v-if="!isJustPlay" class="quote-product-image"><span>产品主图</span><input type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" @change="selectProductImage(index, $event)"><small><FileImage />{{ product.imageFile?.name || '选择图片' }}</small></label>
                      <button v-if="!isJustPlay && product.imageFile" type="button" class="quote-asset-preview" @click="openDocumentPreview(product.imageFile)"><Eye />预览主图</button>
                      <label v-if="mode === 'create'" class="quote-product-documents"><span>产品资料</span><input type="file" multiple accept=".xls,.xlsx,.doc,.docx,.pdf,.jpg,.jpeg" @change="selectProductDocuments(index, $event)"><small><FileText />添加资料</small></label>
                    </div>
                    <div v-if="product.documentFiles?.length" class="quote-product-document-list">
                      <div v-for="(document, documentIndex) in product.documentFiles" :key="`${document.file.name}-${document.file.size}`">
                        <button type="button" class="quote-document-name" :title="`预览 ${document.file.name}`" @click="openDocumentPreview(document.file)"><Eye />{{ document.file.name }}</button>
                        <select v-model="document.department" :aria-label="`${document.file.name} 分配部门`">
                          <option v-for="section in selectedDepartmentDefinitions" :key="section.code" :value="section.code">{{ section.label }}</option>
                        </select>
                        <button type="button" class="quote-document-remove" :aria-label="`移除 ${document.file.name}`" @click="removeProductDocument(index, documentIndex)"><Trash2 /></button>
                      </div>
                    </div>
                  </div>
                  <span v-if="product.regionCode" class="quote-region-badge">{{ product.regionCode === 'mainland' ? '大陆价' : '印尼价' }}</span>
                  <button v-if="form.quoteType === 'series' && form.products.length > 1" type="button" class="quote-remove-product" aria-label="移除产品" @click="removeProduct(index)"><Trash2 /></button>
                  <b v-if="index === 0" class="quote-baseline-badge">基准款</b>
                  <div v-if="mode === 'create'" class="quote-history-source">
                    <button type="button" @click="historyTarget = { kind: 'product', productIndex: index }">{{ product.historySource ? '更换整款来源' : '引用整款到本产品' }}</button>
                    <template v-if="product.historySource"><span>整款来源：{{ product.historySource.label }}（含图片及包装资料）</span><button type="button" @click="clearHistory(product)">取消本款引用</button></template>
                    <label v-if="product.historySource || product.componentSources?.some(Boolean)">材料 / 机型参考价<select :value="product.historyReferenceMode ?? 'source'" @change="product.historyReferenceMode = ($event.target as HTMLSelectElement).value as 'source' | 'current'"><option value="source">沿用历史参考价（冲突时提示）</option><option value="current">使用当前参考表重新核价</option></select></label>
                  </div>
                  <section v-if="isJustPlay" class="quote-product-list quote-pricing-component-list quote-product-components">
                    <div class="quote-product-list-head">
                      <div><strong>本款 JustPlay 报价分项</strong><span>1 个主体 + {{ Math.max(0, (product.pricingComponents?.length ?? 1) - 1) }} 个配件；名称可分别修改。</span></div>
                      <div class="quote-component-actions">
                        <label class="quote-accessory-count"><span>配件个数</span><select :value="(product.pricingComponents?.length ?? 1) - 1" :aria-label="`第 ${index + 1} 款配件个数`" @change="changeAccessoryCount(index, $event)"><option v-for="count in 50" :key="count - 1" :value="count - 1">{{ count - 1 }} 个</option></select></label>
                        <button type="button" :disabled="(product.pricingComponents?.length ?? 0) >= 50" @click="addPricingComponent(index)"><Plus />新增配件</button>
                        <button type="button" :disabled="(product.pricingComponents?.length ?? 0) >= 50" @click="historyTarget = { kind: 'component', productIndex: index }"><Copy />引用历史配件</button>
                      </div>
                    </div>
                    <div class="quote-pricing-component-rows">
                      <div v-for="(_component, componentIndex) in product.pricingComponents" :key="componentIndex" class="quote-component-card">
                        <span>{{ componentIndex === 0 ? '主体' : `配件 ${componentIndex}` }}</span>
                        <input v-model="product.pricingComponents![componentIndex]" type="text" maxlength="64" :aria-label="`第 ${index + 1} 款${componentIndex === 0 ? '主体' : `配件 ${componentIndex}`}名称`" :placeholder="componentIndex === 0 ? '例如：主体' : `例如：配件${componentIndex}`">
                        <button v-if="componentIndex > 0" type="button" :aria-label="`移除第 ${index + 1} 款配件 ${componentIndex}`" @click="removePricingComponent(index, componentIndex)"><Trash2 /></button>
                        <div class="quote-component-asset">
                          <button type="button" @click="historyTarget = { kind: 'component', productIndex: index, componentIndex }">{{ product.componentSources?.[componentIndex] ? '替换历史配件' : '选择历史分项' }}</button>
                          <small v-if="product.componentSources?.[componentIndex]" class="quote-component-source">来源：{{ product.componentSources[componentIndex]!.label }} · 含原分项图片</small>
                          <button v-if="product.componentSources?.[componentIndex]" type="button" @click="product.componentSources![componentIndex] = null">取消分项引用</button>
                          <label class="quote-component-image-picker"><FileImage /><span>{{ product.componentImageFiles?.[componentIndex]?.name || '选择本分项图片' }}</span><input type="file" accept=".jpg,.jpeg,.png,.webp" :aria-label="`第 ${index + 1} 款${_component}图片`" @change="selectComponentImage(index, componentIndex, $event)"></label>
                          <template v-if="product.componentImageFiles?.[componentIndex]">
                            <button type="button" @click="openDocumentPreview(product.componentImageFiles[componentIndex]!)">预览</button>
                            <button type="button" @click="product.componentImageFiles![componentIndex] = null">移除图片</button>
                          </template>
                        </div>
                      </div>
                    </div>
                    <p>图片仅用于当前分项，导出放在对应明细右侧；新增产品只复制分项名称和个数，不复制图片。模具及喷油映射后统一选择明细归属。</p>
                  </section>
                </article>
              </div>
              <p>{{ isJustPlay ? '图片在各分项内提供；' : '产品主图与资料在同一区域维护；' }}资料必须分配给参与部门，支持 Excel、Word、PDF 和 JPG/JPEG，创建后继续在对应部门资料栏预览。</p>
            </section>

            <section class="quote-create-baseline">
              <p v-if="form.products.some(p => p.historySource || p.componentSources?.some(Boolean))" class="quote-history-notice">历史明细独立复制，不影响原单。材料/机型参考价按每款的选择冻结，汇率、倍率及地区运费按新单重新核价；配件重组不复制共享包装。请建单后核对包装、人工及电子公共费用，再直接输出。</p>
              <div class="quote-baseline-title">
                <Building2 aria-hidden="true" />
                <div><strong>当前厂区：{{ factoryName }}</strong><span>统一车间 {{ factoryId }}-workshop，不在页面内重复切换厂区</span></div>
              </div>
              <div class="quote-participation-heading">
                <strong>参与部门</strong>
                <span>业务部、工程部、装配部固定参与</span>
              </div>
              <div class="quote-segment-pills mandatory">
                <span v-for="segment in mandatorySectionDefinitions" :key="segment.code">
                  <CheckCircle2 aria-hidden="true" />{{ segment.label }} · 固定
                </span>
              </div>
              <div class="quote-optional-segments" aria-label="可选参与部门">
                <label
                  v-for="segment in optionalSectionDefinitions"
                  :key="segment.code"
                  :class="{ active: form.participatingSections.includes(segment.code) }"
                >
                  <input v-model="form.participatingSections" type="checkbox" :value="segment.code">
                  <CheckCircle2 aria-hidden="true" />
                  <span>
                    <strong>{{ segment.label }}</strong>
                    <small>{{ form.participatingSections.includes(segment.code) ? '已选择参与' : '本次不参与' }}</small>
                  </span>
                </label>
              </div>
              <p class="quote-participation-note">未选择的部门不会收到填写任务，也不计入协作进度和最终放行；创建后仍可在协作页添加回来。</p>
              <p><Snowflake aria-hidden="true" />创建后冻结汇率、材料价与机型价参考快照；同步新参考表会产生新 revision。</p>
            </section>

            <p v-if="errorMessage || externalError" class="quote-form-error" role="alert">{{ errorMessage || externalError }}</p>
          </div>

          <footer class="quote-dialog-actions">
            <button type="button" class="quote-secondary-button" :disabled="busy" @click="emit('close')">取消</button>
            <button type="button" class="quote-primary-button" :disabled="busy || !businessOwners.length || !customerOptions.length" @click="submit">
              <Copy v-if="mode === 'clone'" aria-hidden="true" />
              <FilePlus2 v-else aria-hidden="true" />
              {{ busy ? '正在提交…' : mode === 'clone' ? '确认复制并进入协作' : '创建并进入协作' }}
            </button>
          </footer>
        </section>
        <div v-if="documentPreview" class="quote-create-preview-backdrop" role="presentation" @mousedown.self="closeDocumentPreview">
          <section class="quote-create-preview" role="dialog" aria-modal="true" :aria-label="`预览 ${documentPreview.file.name}`">
            <header><div><strong>{{ documentPreview.file.name }}</strong><span>{{ (documentPreview.file.size / 1024).toFixed(1) }} KB</span></div><button type="button" aria-label="关闭资料预览" @click="closeDocumentPreview"><X /></button></header>
            <img v-if="documentPreview.kind === 'image'" :src="documentPreview.url" :alt="documentPreview.file.name">
            <iframe v-else-if="documentPreview.kind === 'pdf'" :src="documentPreview.url" :title="documentPreview.file.name" />
            <div v-else class="quote-create-file-preview"><FileText /><strong>文件已加入本款产品资料</strong><span>Excel 和 Word 内容将在报价创建完成后，通过对应部门的资料预览窗口打开。</span></div>
          </section>
        </div>
      </div>
    </Transition>
  </Teleport>
  <InternalQuoteHistoryPicker :open="!!historyTarget && open" :factory-id="factoryId" :customer="form.customer" :is-just-play="isJustPlay" :kind="historyTarget?.kind ?? 'product'" :multiple="historyTarget?.kind === 'product' ? historyTarget.productIndex === undefined : historyTarget?.componentIndex === undefined" @close="historyTarget = null" @confirm="acceptHistory" />
</template>

<style scoped>
.quote-history-source{grid-column:2/-1;display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:12px;color:#475569}.quote-history-source button{border:1px solid #99f6e4;border-radius:7px;background:#f0fdfa;padding:7px;color:#0f766e}.quote-component-source{width:100%;font-size:11px;color:#64748b;overflow-wrap:anywhere}.quote-history-notice{background:#fffbeb;border:1px solid #fde68a;padding:10px!important;color:#92400e!important;border-radius:8px}
.quote-dialog-backdrop{position:fixed;inset:0;z-index:100;display:grid;place-items:center;padding:24px;background:rgb(15 23 42/.5);backdrop-filter:blur(5px)}
.quote-dialog{width:min(980px,100%);max-height:min(920px,calc(100vh - 48px));overflow:auto;border:1px solid #d8e2e7;border-radius:18px;background:#fff;box-shadow:0 30px 80px rgb(15 23 42/.24)}
.quote-dialog-head,.quote-dialog-actions{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:18px 22px;border-color:#e2e8f0;background:#f8fafc}
.quote-dialog-head{border-bottom:1px solid #e2e8f0}.quote-dialog-actions{justify-content:flex-end;border-top:1px solid #e2e8f0}
.quote-dialog-heading{display:flex;min-width:0;align-items:center;gap:13px}.quote-dialog-heading h2{margin:0;color:#0f172a;font-size:20px;font-weight:900}.quote-dialog-heading p{margin:5px 0 0;color:#64748b;font-size:12px;line-height:1.5}
.quote-dialog-icon{display:grid;width:42px;height:42px;flex:0 0 auto;place-items:center;border-radius:12px;background:#ccfbf1;color:#0f766e}.quote-dialog-icon svg,.quote-icon-button svg{width:20px;height:20px}
.quote-icon-button{display:grid;width:36px;height:36px;flex:0 0 auto;place-items:center;border:0;border-radius:9px;background:transparent;color:#64748b}.quote-icon-button:hover{background:#e2e8f0;color:#0f172a}
.quote-dialog-body{display:grid;gap:18px;padding:22px}.quote-copy-note{display:flex;gap:9px;border:1px solid #bfdbfe;border-radius:10px;background:#eff6ff;padding:11px 13px;color:#1e40af;font-size:12px;line-height:1.55}.quote-copy-note svg{width:17px;height:17px;flex:0 0 auto;margin-top:1px}
.quote-department-choice{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:0;padding:0;border:0}.quote-department-choice legend{grid-column:1/-1;margin-bottom:1px;color:#475569;font-size:12px;font-weight:800}.quote-department-choice label{position:relative;display:grid;grid-template-columns:auto 1fr;gap:2px 9px;border:1px solid #dbe5ea;border-radius:11px;padding:13px 14px;cursor:pointer}.quote-department-choice label.active{border-color:#14b8a6;background:#f0fdfa;box-shadow:0 0 0 3px rgb(20 184 166/.09)}.quote-department-choice input{position:absolute;opacity:0}.quote-choice-check{grid-row:1/3;color:#94a3b8}.active .quote-choice-check{color:#0f766e}.quote-choice-check svg{width:18px;height:18px}.quote-department-choice strong{color:#0f172a;font-size:13px}.quote-department-choice small{color:#64748b;font-size:11px;line-height:1.45}
.quote-department-choice label.disabled{cursor:not-allowed;opacity:.48}.quote-department-choice label.disabled:hover{border-color:#dbe5ea;box-shadow:none}
.quote-type-choice{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin:0;padding:0;border:0}.quote-type-choice legend{grid-column:1/-1;color:#475569;font-size:12px;font-weight:800}.quote-type-choice label{position:relative;display:grid;gap:3px;border:1px solid #dbe5ea;border-radius:10px;padding:11px 12px;cursor:pointer}.quote-type-choice label.active{border-color:#14b8a6;background:#f0fdfa;box-shadow:0 0 0 3px rgb(20 184 166/.08)}.quote-type-choice input{position:absolute;opacity:0}.quote-type-choice strong{color:#0f172a;font-size:13px}.quote-type-choice small{color:#64748b;font-size:11px}
.quote-form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.quote-form-grid label{display:grid;gap:6px}.quote-form-grid label.wide{grid-column:1/-1}.quote-form-grid label>span{color:#475569;font-size:11px;font-weight:800}.quote-form-grid b{color:#dc2626}.quote-form-grid input,.quote-form-grid select,.quote-form-grid textarea{width:100%;border:1px solid #dbe5ea;border-radius:9px;background:#fff;padding:9px 11px;color:#0f172a;font-size:13px;outline:none}.quote-form-grid textarea{resize:vertical}
.quote-owner-hint{color:#64748b;font-size:11px;line-height:1.5}
.quote-product-list{display:grid;gap:10px;border:1px solid #dbe5ea;border-radius:12px;background:#f8fafc;padding:14px}.quote-product-list-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.quote-product-list-head>div{display:grid;gap:3px}.quote-product-list-head strong{color:#0f172a;font-size:14px}.quote-product-list-head span,.quote-product-list>p{margin:0;color:#64748b;font-size:11px;line-height:1.5}.quote-product-list-head button{display:inline-flex;align-items:center;gap:5px;border:1px solid #99f6e4;border-radius:8px;background:#fff;padding:7px 10px;color:#0f766e;font-size:11px;font-weight:900}.quote-product-list-head button svg{width:14px}.quote-product-rows{display:grid;gap:8px}.quote-product-row{position:relative;display:grid;grid-template-columns:34px minmax(170px,1.35fr) minmax(95px,.55fr) minmax(330px,2fr) auto;align-items:start;gap:9px;border:1px solid #e2e8f0;border-radius:10px;background:#fff;padding:10px}.quote-product-number{align-self:center;color:#0f766e;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;font-weight:900}.quote-product-row label{display:grid;gap:5px}.quote-product-row label>span{color:#475569;font-size:10px;font-weight:800}.quote-product-row label b{color:#dc2626}.quote-product-row input[type=text],.quote-product-row input[type=number]{min-width:0;width:100%;border:1px solid #dbe5ea;border-radius:8px;padding:8px 9px;color:#0f172a;font-size:12px}.quote-product-image input,.quote-product-documents input{position:absolute;width:1px;height:1px;opacity:0}.quote-product-image small,.quote-product-documents small{display:flex;min-width:0;align-items:center;justify-content:center;gap:5px;overflow:hidden;border:1px dashed #99f6e4;border-radius:8px;padding:8px 9px;color:#0f766e;font-size:11px;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}.quote-product-image small svg,.quote-product-documents small svg{width:14px;flex:0 0 auto}.quote-product-assets{display:grid;gap:7px}.quote-product-asset-pickers{display:grid;grid-template-columns:minmax(120px,1fr) auto minmax(105px,.7fr);align-items:end;gap:6px}.quote-asset-preview{display:inline-flex;height:34px;align-items:center;gap:4px;border:1px solid #99f6e4;border-radius:8px;background:#f0fdfa;padding:0 8px;color:#0f766e;font-size:10px;font-weight:900}.quote-asset-preview svg{width:13px}.quote-product-document-list{display:grid;gap:5px}.quote-product-document-list>div{display:grid;grid-template-columns:minmax(0,1fr) 86px 28px;gap:5px}.quote-document-name{display:flex;min-width:0;align-items:center;gap:5px;overflow:hidden;border:1px solid #dbe5ea;border-radius:7px;background:#fff;padding:6px 7px;color:#475569;font-size:10px;text-align:left;text-overflow:ellipsis;white-space:nowrap}.quote-document-name svg{width:12px;flex:0 0 auto}.quote-product-document-list select{min-width:0;border:1px solid #dbe5ea;border-radius:7px;background:#fff;padding:5px;color:#0f766e;font-size:10px;font-weight:800}.quote-document-remove{display:grid;place-items:center;border:1px solid #fecaca;border-radius:7px;background:#fff;color:#dc2626}.quote-document-remove svg{width:12px}.quote-baseline-badge,.quote-region-badge{position:absolute;top:6px;right:8px;border-radius:999px;padding:3px 6px;font-size:9px}.quote-baseline-badge{background:#ccfbf1;color:#0f766e}.quote-region-badge{right:62px;background:#eff6ff;color:#1d4ed8}.quote-remove-product{display:grid;width:30px;height:30px;place-items:center;border:1px solid #fecaca;border-radius:8px;background:#fff;color:#dc2626}.quote-remove-product svg{width:14px}
.quote-pricing-component-list{border-color:#99f6e4;background:#f0fdfa}.quote-pricing-component-rows{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.quote-pricing-component-rows .quote-component-card{display:grid;grid-template-columns:auto minmax(0,1fr) 30px;align-items:center;gap:8px;border:1px solid #ccfbf1;border-radius:9px;background:#fff;padding:8px}.quote-pricing-component-rows .quote-component-card>span{color:#0f766e;font-size:11px;font-weight:900}.quote-pricing-component-rows input{min-width:0;border:1px solid #dbe5ea;border-radius:7px;padding:7px 8px;color:#0f172a;font-size:12px}.quote-pricing-component-rows .quote-component-card>button{display:grid;width:30px;height:30px;place-items:center;border:1px solid #fecaca;border-radius:7px;background:#fff;color:#dc2626}.quote-pricing-component-rows .quote-component-card>button svg{width:13px}
.quote-create-preview-backdrop{position:fixed;inset:0;z-index:120;display:grid;place-items:center;padding:28px;background:rgb(15 23 42/.66)}.quote-create-preview{display:grid;width:min(900px,100%);max-height:calc(100vh - 56px);overflow:hidden;border:1px solid #cbd5e1;border-radius:16px;background:#fff;box-shadow:0 28px 80px rgb(15 23 42/.35)}.quote-create-preview header{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid #e2e8f0;background:#f8fafc;padding:12px 14px}.quote-create-preview header>div{display:grid;min-width:0}.quote-create-preview header strong{overflow:hidden;color:#0f172a;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.quote-create-preview header span{margin-top:2px;color:#64748b;font-size:10px}.quote-create-preview header button{display:grid;width:32px;height:32px;place-items:center;border:0;border-radius:8px;background:#fff;color:#64748b}.quote-create-preview header svg{width:16px}.quote-create-preview>img{display:block;max-width:100%;max-height:calc(100vh - 150px);margin:auto;object-fit:contain}.quote-create-preview>iframe{width:min(900px,90vw);height:calc(100vh - 150px);border:0}.quote-create-file-preview{display:grid;min-height:280px;place-items:center;align-content:center;gap:9px;padding:30px;color:#64748b;text-align:center}.quote-create-file-preview>svg{width:44px;color:#0d9488}.quote-create-file-preview strong{color:#0f172a;font-size:15px}.quote-create-file-preview span{max-width:480px;font-size:12px;line-height:1.6}
.quote-create-baseline{display:grid;gap:12px;border:1px solid #dbe5ea;border-radius:12px;background:#f8fafc;padding:15px}.quote-baseline-title{display:flex;align-items:center;gap:9px}.quote-baseline-title>svg{width:20px;color:#0f766e}.quote-baseline-title div{display:grid}.quote-baseline-title strong{color:#0f172a;font-size:13px}.quote-baseline-title span{margin-top:2px;color:#64748b;font-size:11px}.quote-segment-pills{display:flex;flex-wrap:wrap;gap:7px}.quote-segment-pills span{display:inline-flex;align-items:center;gap:4px;border:1px solid #ccfbf1;border-radius:999px;background:#fff;padding:5px 8px;color:#0f766e;font-size:10px;font-weight:800}.quote-segment-pills svg{width:12px;height:12px}.quote-create-baseline p{display:flex;align-items:flex-start;gap:6px;margin:0;color:#64748b;font-size:11px;line-height:1.5}.quote-create-baseline p svg{width:15px;height:15px;flex:0 0 auto;color:#0d9488}.quote-form-error{margin:0;border-radius:8px;background:#fef2f2;padding:9px 11px;color:#b91c1c;font-size:12px}
.quote-primary-button,.quote-secondary-button{display:inline-flex;min-height:38px;align-items:center;justify-content:center;gap:7px;border-radius:9px;padding:0 16px;font-size:12px;font-weight:900}.quote-primary-button{border:1px solid #0f766e;background:#0f766e;color:#fff}.quote-primary-button:hover{background:#115e59}.quote-secondary-button{border:1px solid #cbd5e1;background:#fff;color:#475569}.quote-primary-button svg{width:16px;height:16px}.quote-dialog-enter-active,.quote-dialog-leave-active{transition:opacity .16s ease}.quote-dialog-enter-active .quote-dialog,.quote-dialog-leave-active .quote-dialog{transition:transform .18s ease}.quote-dialog-enter-from,.quote-dialog-leave-to{opacity:0}.quote-dialog-enter-from .quote-dialog,.quote-dialog-leave-to .quote-dialog{transform:translateY(8px) scale(.985)}
.quote-department-choice small,.quote-form-grid label>span,.quote-baseline-title span,.quote-create-baseline p{font-size:12px}.quote-segment-pills span{font-size:11px}.quote-primary-button,.quote-secondary-button{font-size:13px}.quote-icon-button,.quote-primary-button,.quote-secondary-button,.quote-department-choice label{transition:color .18s ease,background-color .18s ease,border-color .18s ease,box-shadow .18s ease,transform .18s ease}.quote-icon-button:hover,.quote-primary-button:hover,.quote-secondary-button:hover{transform:translateY(-1px)}.quote-icon-button:active,.quote-primary-button:active,.quote-secondary-button:active{transform:translateY(0) scale(.98)}.quote-secondary-button:hover{border-color:#99f6e4;background:#f0fdfa;color:#0f766e}.quote-department-choice label:hover{border-color:#99f6e4;box-shadow:0 8px 18px rgb(15 118 110/.08)}.quote-form-grid input,.quote-form-grid select,.quote-form-grid textarea{transition:border-color .18s ease,box-shadow .18s ease,background-color .18s ease}.quote-form-grid input:hover,.quote-form-grid select:hover,.quote-form-grid textarea:hover{border-color:#94a3b8}.quote-form-grid input:focus,.quote-form-grid select:focus,.quote-form-grid textarea:focus{border-color:#14b8a6;box-shadow:0 0 0 3px rgb(20 184 166/.1)}
.quote-participation-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.quote-participation-heading strong{color:#0f172a;font-size:13px}.quote-participation-heading span{color:#64748b;font-size:12px}.quote-segment-pills.mandatory span{border-color:#99f6e4;background:#f0fdfa;padding:6px 9px;font-size:11px}.quote-optional-segments{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:7px}.quote-optional-segments label{position:relative;display:flex;align-items:center;gap:7px;min-width:0;border:1px solid #dbe5ea;border-radius:10px;background:#fff;padding:9px;cursor:pointer;transition:border-color .18s ease,background-color .18s ease,box-shadow .18s ease,transform .18s ease}.quote-optional-segments label:hover{border-color:#5eead4;box-shadow:0 7px 16px rgb(15 118 110/.08);transform:translateY(-1px)}.quote-optional-segments label.active{border-color:#14b8a6;background:#f0fdfa;box-shadow:0 0 0 2px rgb(20 184 166/.08)}.quote-optional-segments input{position:absolute;opacity:0}.quote-optional-segments>label>svg{width:16px;height:16px;flex:0 0 auto;color:#cbd5e1}.quote-optional-segments label.active>svg{color:#0f766e}.quote-optional-segments label span{display:grid;min-width:0}.quote-optional-segments strong{overflow:hidden;color:#0f172a;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.quote-optional-segments small{margin-top:2px;color:#64748b;font-size:10px;white-space:nowrap}.quote-create-baseline .quote-participation-note{border-radius:8px;background:#fff7ed;padding:8px 10px;color:#9a3412;font-size:12px}
@media(max-width:760px){.quote-optional-segments{grid-template-columns:repeat(2,minmax(0,1fr))}.quote-type-choice{grid-template-columns:1fr}.quote-product-row{grid-template-columns:30px 1fr}.quote-product-row label,.quote-product-assets{grid-column:2}.quote-product-asset-pickers{grid-template-columns:1fr auto}.quote-product-documents{grid-column:1/-1}.quote-remove-product{grid-column:2}.quote-region-badge{right:8px;top:32px}}
@media(max-width:650px){.quote-dialog-backdrop{padding:0}.quote-dialog{max-height:100vh;border-radius:0}.quote-department-choice,.quote-form-grid,.quote-pricing-component-rows{grid-template-columns:1fr}.quote-form-grid label.wide{grid-column:auto}.quote-dialog-actions{position:sticky;bottom:0}.quote-participation-heading{align-items:flex-start;flex-direction:column;gap:3px}}
@media(prefers-reduced-motion:reduce){.quote-icon-button,.quote-primary-button,.quote-secondary-button,.quote-department-choice label,.quote-optional-segments label,.quote-form-grid input,.quote-form-grid select,.quote-form-grid textarea{transition:none}}
.quote-product-components{grid-column:2/-1;min-width:0;margin-top:4px}
.quote-product-list-head>.quote-component-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.quote-product-row .quote-accessory-count{display:flex;align-items:center;gap:6px}
.quote-accessory-count select{border:1px solid #99f6e4;border-radius:7px;background:#fff;padding:6px;color:#0f766e;font-size:12px}
.quote-product-components .quote-pricing-component-rows label{grid-column:auto}
@media(max-width:760px){.quote-product-components{grid-column:1/-1}.quote-product-components .quote-product-list-head{align-items:flex-start;flex-direction:column}.quote-product-components .quote-pricing-component-rows{grid-template-columns:1fr}}
.quote-component-asset{grid-column:1/-1;display:flex;align-items:center;gap:8px;flex-wrap:wrap}.quote-component-asset label{display:flex;max-width:100%;color:#0f766e;cursor:pointer;font-size:12px}.quote-component-asset label span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.quote-component-asset input{position:absolute;width:1px;height:1px;opacity:0}.quote-component-asset button{font-size:12px;color:#0f766e;border:1px solid #99f6e4;border-radius:6px;padding:4px 8px}
.quote-component-asset .quote-component-image-picker{display:flex;align-items:center;gap:6px;border:1px dashed #99f6e4;border-radius:7px;background:#f0fdfa;padding:7px 9px;min-height:32px}.quote-component-image-picker svg{width:15px;height:15px;flex-shrink:0}
</style>
