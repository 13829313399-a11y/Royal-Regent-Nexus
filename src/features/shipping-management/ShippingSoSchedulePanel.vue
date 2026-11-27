<script setup lang="ts">
import { newId } from './ids'
import { ref } from 'vue'
import ShippingLoadingSheetPanel from './ShippingLoadingSheetPanel.vue'
import ShippingGeneratedDocs from './ShippingGeneratedDocs.vue'
import type { LoadingDraft, LoadingHeader, LoadingLine } from '@/api/shippingMail'

defineProps<{ factoryId: string }>()
const emit = defineEmits<{ notify: [message: string]; back: [] }>()

const cabinetSearch = ref('')
const cabinetDraft = ref<LoadingDraft | null>(null)

function text(value: unknown) {
  return value == null ? '' : String(value)
}

function toLine(line: Record<string, unknown>): LoadingLine {
  const productCode = text(line.filingCode) || text(line.declareCode)
  return {
    id: newId(),
    tradingCompany: text(line.tradingCompany) || 'DK',
    contract: text(line.contract),
    filingCode: productCode,
    declareCode: productCode,
    coefficient: line.coefficient == null ? null : Number(line.coefficient),
    quantity: line.quantity == null ? null : Number(line.quantity),
    cartons: line.cartons == null ? null : Number(line.cartons),
    grossWeight: line.grossWeight == null ? null : Number(line.grossWeight),
    netWeight: line.netWeight == null ? null : Number(line.netWeight),
    cbm: line.cbm == null ? null : Number(line.cbm),
    category: text(line.category) || '塑胶',
    grossPerCarton: line.grossPerCarton == null ? null : Number(line.grossPerCarton),
    netPerCarton: line.netPerCarton == null ? null : Number(line.netPerCarton),
    description: text(line.description),
    department: text(line.department) || 'W',
    cartonMark: text(line.cartonMark),
  }
}

async function importCabinet(payload: { taskId: string; filename: string; header: Record<string, unknown>; lines: Array<Record<string, unknown>> }) {  const source = payload.header
  const header: LoadingHeader = {
    shipper: text(source.shipper) || '华兴玩具制品（河源）有限公司',
    consignee: text(source.consignee),
    tradingCompany: 'DK',
    soNo: text(source.soNo),
    contractNo: text(source.contractNo),
    filingCode: text(source.filingCode),
    vessel: text(source.vessel),
    voyage: text(source.voyage),
    containerType: text(source.containerType),
    cutoff: text(source.cutoff),
    sheetDate: text(source.sheetDate) || new Date().toISOString().slice(0, 10),
    preparer: text(source.preparer) || '农建壮',
    brandNote: text(source.brandNote),
    poNo: text(source.poNo) || text(source.cartonMark),
    originPort: text(source.originPort) || '盐田',
    transportCompany: text(source.transportCompany) || '成隆达',
    tableName: text(source.tableName),
    number: text(source.number),
    plate: text(source.plate),
    containerNo: text(source.containerNo),
    sealNo: text(source.sealNo),
    tareWeight: text(source.tareWeight),
    destinationCountry: text(source.destinationCountry),
    bookingDate: text(source.bookingDate),
    bookingNo: text(source.bookingNo),
    tradeTerm: text(source.tradeTerm) || 'FOB',
    shippingClerk: text(source.shippingClerk),
    truckHead: text(source.truckHead),
    cartonMark: text(source.cartonMark) || text(source.poNo),
    photoNote: text(source.photoNote) || '注，要照相',
    department: 'W',
  }
  const contract = text(source.contractNo)
  const distinctContracts = new Set(payload.lines.map((line) => text(line.contract_no || line.contract)).filter(Boolean))
  const lines = payload.lines.map((line) => {
    const mapped = toLine(line)
    if (contract && distinctContracts.size <= 1) mapped.contract = contract
    return mapped
  })
  if (!header.contractNo && distinctContracts.size > 0) header.contractNo = [...distinctContracts][0]
  cabinetDraft.value = {
    number: text(source.number),
    taskId: payload.taskId,
    header,
    lines,
    totals: {},
  }
  emit('notify', `已把 ${payload.filename} 的表头与明细导入柜货单，请核对后导出。`)
}
</script>

<template>
  <section class="space-y-4" aria-label="SO出货表">
    <ShippingGeneratedDocs :factory-id="factoryId" module="so" label="SO 出货表" @import-cabinet="importCabinet" />
    <div class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 px-3 py-2.5">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex flex-wrap items-center gap-2">
          <h2 class="text-[14px] font-bold text-emerald-950">SO 出货表</h2>
          <p class="text-[10px] text-slate-500">柜货单模块 · 使用 DK 盐田 W11 柜模板，填色与公式与原表一致</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <input
            v-model="cabinetSearch"
            type="search"
            aria-label="搜索合同号或备案货号"
            placeholder="搜索合同号 / 备案货号"
            class="h-8 w-[200px] rounded-lg border border-emerald-200 bg-white px-2.5 text-[11px] text-slate-800 outline-none placeholder:text-slate-400 focus:border-emerald-500"
          >
          <button type="button" class="text-[12px] font-semibold text-emerald-800 hover:underline" @click="emit('back')">← 返回工厂排期单</button>
        </div>
      </div>
    </div>

    <ShippingLoadingSheetPanel :factory-id="factoryId" :initial-draft="cabinetDraft" :search-query="cabinetSearch" @notify="emit('notify', $event)" @back="emit('back')" />
  </section>
</template>
