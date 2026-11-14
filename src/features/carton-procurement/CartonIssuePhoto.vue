<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { Camera, ImagePlus, Search, X } from '@lucide/vue'
import { DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogRoot, DialogTitle } from 'reka-ui'
import { getApiErrorMessage } from '@/lib/http'
import { issuePhotoMatches, readIssuePhoto, type IssuePhotoDraft, type IssuePhotoRow, type IssuePhotoStock } from './issuePhoto'

interface Position extends IssuePhotoStock {
  customer: string
  packagingType: string
  specification: string
  paperQuality: string
  location: string
  unit: string
}

const props = defineProps<{ factory: string; positions: Position[]; disabled: boolean; existingDocument: string }>()
const emit = defineEmits<{ apply: [draft: IssuePhotoDraft]; open: [boolean] }>()
const empty = (): IssuePhotoRow => ({ contract_no: '', reference_kind: 'po', item_no: '', requested_quantity: '', evidence: '', top: 0, bottom: 0 })
const open = ref(false)
const busy = ref(false)
const failure = ref('')
const missingHeader = ref(false)
const documentNo = ref('')
const rows = ref<IssuePhotoRow[]>([])
const picks = ref<Record<number, string[]>>({})
const edited = ref(new Set<number>())
const preview = ref('')
const crop = ref('')
const rotation = ref(0)
let previewImage: Promise<HTMLImageElement> | undefined
let request: AbortController | undefined
let cropGeneration = 0
const format = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 4 })
const referenceLabel = (row: IssuePhotoRow) => {
  if (!row.top && row.reference_kind === 'po') return '合同或 PO'
  if (row.reference_kind === 'po') return 'PO'
  return row.reference_kind === 'customer_po' ? '客户 PO' : '合同'
}

const results = computed(() => rows.value.map((row, index) => {
  const previous = rows.value.slice(0, index).reverse()
  const baseIndex = previous.findIndex(value => value.contract_no && !/^\s*-/.test(value.contract_no))
  const base = previous[baseIndex]
  const chosen = props.positions.find(position => picks.value[index - 1 - baseIndex]?.includes(position.id))
  const lastItem = previous.find(value => value.item_no)?.item_no
  const manual = edited.value.has(index)
  return issuePhotoMatches(manual ? { ...row, evidence: '' } : row,
    props.positions, chosen?.poNumber || (base && (!base.reference_kind || base.reference_kind === 'contract') ? base.contract_no : ''),
    chosen?.itemNo || lastItem, manual)
}))
const documentConflict = computed(() => !!props.existingDocument.trim() && documentNo.value.trim() !== props.existingDocument.trim())
const draft = computed<IssuePhotoDraft>(() => {
  const positions = new Set<string>()
  const references: Record<string, string> = {}
  const repeated = new Set<string>()
  for (const [index, ids] of Object.entries(picks.value)) {
    const row = rows.value[Number(index)]
    if (!row) continue
    for (const id of ids) {
      if (!results.value[Number(index)]?.some(candidate => candidate.position.id === id)) continue
      if (positions.has(id)) repeated.add(id)
      positions.add(id)
      if (ids.length === 1 && row.requested_quantity) references[id] = row.requested_quantity
    }
  }
  for (const id of repeated) delete references[id]
  return { documentNo: documentNo.value.trim(), positions: [...positions], requested: references }
})

function setOpen(value: boolean) {
  open.value = value
  emit('open', value)
  if (!value) reset()
}

function reset() {
  request?.abort()
  request = undefined
  busy.value = false
  failure.value = ''
  missingHeader.value = false
  rows.value = []
  documentNo.value = ''
  picks.value = {}
  edited.value.clear()
  clearCrop()
  if (preview.value) URL.revokeObjectURL(preview.value)
  preview.value = ''
  previewImage = undefined
}
onBeforeUnmount(reset)

function startManual() {
  reset()
  documentNo.value = props.existingDocument
  rows.value = [empty()]
  setOpen(true)
}

async function choose(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  reset()
  setOpen(true)
  const controller = new AbortController()
  request = controller
  busy.value = true
  try {
    const url = URL.createObjectURL(file)
    preview.value = url
    const image = new Image()
    image.src = url
    previewImage = image.decode().then(() => image)
    const decoded = await previewImage
    const longest = Math.max(decoded.naturalWidth, decoded.naturalHeight)
    const scale = Math.min(1, 2000 / longest)
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(decoded.naturalWidth * scale))
    canvas.height = Math.max(1, Math.round(decoded.naturalHeight * scale))
    const context = canvas.getContext('2d')
    if (!context) throw new Error('浏览器无法处理这张照片。')
    context.fillStyle = '#fff'
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.drawImage(decoded, 0, 0, canvas.width, canvas.height)
    const jpeg = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', .94))
    if (!jpeg) throw new Error('浏览器无法转换这张照片。')
    const result = await readIssuePhoto(props.factory, new File([jpeg], 'issue-note.jpg', { type: 'image/jpeg' }), controller.signal)
    if (request !== controller) return
    rotation.value = result.rotation
    documentNo.value = result.document_no
    rows.value = result.rows.length ? result.rows : [empty()]
    missingHeader.value = result.has_header === false
    if (!result.rows.length) failure.value = '没有读到明细。可对照原图，输入合同或货号中清楚的一段。'
  } catch (error) {
    if (request !== controller) return
    failure.value = getApiErrorMessage(error) || '无法读取照片，请重拍或手动查找。'
    rows.value = [empty()]
  } finally {
    if (request === controller) busy.value = false
  }
}

function clearCrop() {
  cropGeneration++
  if (crop.value) URL.revokeObjectURL(crop.value)
  crop.value = ''
}

async function showRow(row: IssuePhotoRow) {
  if (!previewImage || row.bottom <= row.top) return
  clearCrop()
  const generation = cropGeneration
  try {
    const image = await previewImage
    const canvas = document.createElement('canvas')
    const rightAngle = rotation.value % 180 !== 0
    const width = rightAngle ? image.naturalHeight : image.naturalWidth
    const height = rightAngle ? image.naturalWidth : image.naturalHeight
    canvas.width = Math.min(1400, width)
    const scale = canvas.width / width
    canvas.height = Math.max(1, Math.ceil((row.bottom - row.top) * height * scale))
    const context = canvas.getContext('2d')
    if (!context) return
    context.scale(scale, scale)
    context.translate(width / 2, height * (.5 - row.top))
    context.rotate(-rotation.value * Math.PI / 180)
    context.drawImage(image, -image.naturalWidth / 2, -image.naturalHeight / 2)
    const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', .9))
    if (blob && generation === cropGeneration) crop.value = URL.createObjectURL(blob)
  } catch { /* The full photo remains available. */ }
}

function changeRow(index: number) {
  edited.value.add(index)
  delete picks.value[index]
  for (const [key, ids] of Object.entries(picks.value)) {
    const candidates = results.value[Number(key)] || []
    picks.value[Number(key)] = ids.filter(id => candidates.some(value => value.position.id === id))
  }
}
function select(index: number, id: string, checked: boolean) {
  const current = picks.value[index] || []
  picks.value[index] = checked ? [...current, id] : current.filter(value => value !== id)
}
function apply() {
  const result = draft.value
  if (!result.positions.length || props.disabled || documentConflict.value) return
  setOpen(false)
  emit('apply', result)
}
</script>

<template>
  <div>
    <div class="flex gap-2">
      <label class="relative flex min-h-12 flex-1 items-center justify-center gap-2 rounded-xl bg-teal-800 px-3 font-semibold text-white has-[:focus-visible]:ring-2 has-[:disabled]:opacity-60">
        <Camera class="size-5" aria-hidden="true" />拍领料单
        <input type="file" class="absolute inset-0 size-full cursor-pointer opacity-0" accept="image/*" capture="environment" aria-label="拍领料单" :disabled="disabled" @change="choose">
      </label>
      <label class="relative flex min-h-12 items-center gap-1.5 rounded-xl border bg-white px-3 font-semibold text-teal-800 has-[:focus-visible]:ring-2 has-[:disabled]:opacity-60">
        <ImagePlus class="size-4" aria-hidden="true" />选照片
        <input type="file" class="absolute inset-0 size-full cursor-pointer opacity-0" accept="image/*" aria-label="选择领料单照片" :disabled="disabled" @change="choose">
      </label>
    </div>
    <button type="button" :disabled="disabled" class="mt-2 flex min-h-11 items-center gap-2 rounded-xl border bg-white px-3 font-semibold text-teal-800 disabled:opacity-60" @click="startManual">
      <Search class="size-4" aria-hidden="true" />按编号找订单
    </button>
    <DialogRoot :open="open" @update:open="setOpen">
      <DialogOverlay class="fixed inset-0 z-[70] bg-slate-950/40" />
      <DialogContent class="carton-phone-dialog fixed inset-0 z-[71] mx-auto flex w-full max-w-xl flex-col bg-white">
        <div class="flex shrink-0 items-start justify-between gap-3 border-b p-4">
          <div><DialogTitle class="text-lg font-bold">核对领料单</DialogTitle><DialogDescription class="text-sm text-slate-600">按纸单逐行选订单和仓位，实发数量在发料表单确认。</DialogDescription></div>
          <DialogClose aria-label="关闭领料单核对" class="grid size-11 shrink-0 place-items-center rounded-lg border"><X class="size-5" aria-hidden="true" /></DialogClose>
        </div>
        <div class="carton-phone-receipt-body flex-1 space-y-3 p-4">
          <p v-if="busy" role="status" class="rounded-xl bg-teal-50 p-4 text-sm text-teal-900">正在读取领料单…</p>
          <p v-if="failure" role="alert" class="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">{{ failure }}</p>
          <p v-else-if="missingHeader" role="status" class="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">表头未读全，已用读到的编号找候选。请对照原图核对合同和货号。</p>
          <details v-if="preview" class="rounded-xl border p-3">
            <summary class="min-h-9 cursor-pointer font-semibold text-teal-800">查看原照片</summary>
            <img :src="preview" alt="领料单原照片" class="w-full rounded-lg">
          </details>
          <div v-if="crop" class="sticky top-0 z-10 rounded-xl border bg-white p-2 shadow">
            <div class="flex items-center justify-between"><strong>原单行</strong><button type="button" class="min-h-10 px-2 text-teal-800" @click="clearCrop">收起</button></div>
            <img :src="crop" alt="领料单对应行" class="w-full">
          </div>
          <template v-if="!busy">
            <label class="block font-semibold">来源单据号<input v-model="documentNo" maxlength="64" class="mt-1 block min-h-11 w-full rounded-lg border px-3 text-base" placeholder="核对右上角印刷单号"></label>
            <p v-if="documentConflict" role="alert" class="rounded-lg bg-amber-50 p-2 text-sm text-amber-900">已有单号 {{ existingDocument }} 的发料草稿。若是另一张单，请先回到库存清空已选，再识别新单。</p>
            <section v-for="(row, index) in rows" :key="index" class="min-w-0 space-y-2 rounded-xl border p-3">
              <div class="flex items-center justify-between gap-2"><h3 class="font-bold">第 {{ index + 1 }} 行</h3><button v-if="row.bottom > row.top && preview" type="button" class="min-h-10 px-2 font-semibold text-teal-800" @click="showRow(row)">看原单行</button></div>
              <div class="grid grid-cols-2 gap-2">
                <label class="min-w-0 font-semibold">{{ referenceLabel(row) }}<input v-model="row.contract_no" :aria-label="`第 ${index + 1} 行${referenceLabel(row)}`" maxlength="64" class="mt-1 min-h-11 w-full rounded-lg border px-2 text-base" @input="changeRow(index)"></label>
                <label class="min-w-0 font-semibold">货号<input v-model="row.item_no" :aria-label="`第 ${index + 1} 行货号`" maxlength="64" class="mt-1 min-h-11 w-full rounded-lg border px-2 text-base" @input="changeRow(index)"></label>
              </div>
              <label v-if="row.customer_po !== undefined"
                class="block min-w-0 font-semibold">客户 PO<input v-model="row.customer_po" :aria-label="`第 ${index + 1} 行客户 PO`" maxlength="64" class="mt-1 min-h-11 w-full rounded-lg border px-2 text-base" @input="changeRow(index)"></label>
              <p v-if="row.evidence" class="break-all text-xs text-slate-600">识别原文 {{ row.evidence }}</p>
              <p v-if="row.requested_quantity" class="text-xs text-slate-700">领料数参考 {{ row.requested_quantity }}，请核对单位</p>
              <p v-if="!results[index]?.length" class="text-sm text-slate-600">可输入合同、PO 或货号中连续的至少 4 个字符，按本厂可发库存查找。</p>
              <label v-for="{ position, label } in results[index]" :key="position.id" class="flex min-h-12 items-start gap-2 rounded-lg border bg-slate-50 p-2">
                <input :checked="picks[index]?.includes(position.id)" type="checkbox" class="mt-1 size-5 shrink-0 accent-teal-700" @change="select(index, position.id, ($event.target as HTMLInputElement).checked)">
                <span class="min-w-0 [overflow-wrap:anywhere]">
                  <strong>{{ position.poNumber }} · {{ position.itemNo }}</strong>
                  <span class="block text-xs text-slate-600">{{ position.customer }}<template v-if="position.customerPo"> · 客户 PO {{ position.customerPo }}</template></span>
                  <span class="block">{{ position.packagingType }} · {{ position.paperQuality }} · {{ position.specification }} · {{ position.location || '待核仓位' }}</span>
                  <span class="block text-xs text-teal-800">可发 {{ format.format(position.balance) }} {{ position.unit }} · {{ label }}</span>
                </span>
              </label>
            </section>
            <button type="button" class="min-h-11 w-full rounded-lg border font-semibold text-teal-800" @click="rows.push(empty())">＋ 手动补一行</button>
          </template>
        </div>
        <footer class="carton-phone-footer shrink-0 border-t bg-white px-4 pt-3">
          <button type="button" :disabled="busy || disabled || documentConflict || !draft.positions.length" class="min-h-12 w-full rounded-xl bg-teal-800 px-3 font-bold text-white disabled:opacity-50" @click="apply">带入发料（{{ draft.positions.length }} 项）</button>
        </footer>
      </DialogContent>
    </DialogRoot>
  </div>
</template>
