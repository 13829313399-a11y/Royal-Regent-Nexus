<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ClipboardPenLine, Printer, Save, X, ZoomIn, ZoomOut } from '@lucide/vue'
import MoldingSampleTrialReportSheet from '@/components/molding/MoldingSampleTrialReportSheet.vue'
import type {
  MoldingSampleItem,
  MoldingSampleOrder,
  MoldingSampleTrialReport,
  MoldingSampleTrialReportData,
} from '@/types/moldingSample'

const props = withDefaults(defineProps<{
  visible: boolean
  order: MoldingSampleOrder | null
  items: MoldingSampleItem[]
  reports: MoldingSampleTrialReport[]
  factoryShortName: string
  operatorName: string
  canSave: boolean
  saving: boolean
  readOnly?: boolean
  initialItemId?: string
}>(), {
  readOnly: false,
  initialItemId: '',
})

const emit = defineEmits<{
  close: []
  save: [payload: { itemId: string, data: MoldingSampleTrialReportData }]
}>()

const selectedItemId = ref('')
const draft = ref<MoldingSampleTrialReportData>(createEmptyTrialReportData())
const previewVisible = ref(false)
const reportZoom = ref(1)

const selectedItem = computed(() => props.items.find((item) => item.id === selectedItemId.value) ?? null)
const savedReport = computed(() => props.reports.find((report) => report.item_id === selectedItemId.value) ?? null)
const companyName = computed(() => `${props.factoryShortName || '华兴'}（河源）玩具制品有限公司`)
const savedStatusText = computed(() => {
  if (savedReport.value) {
    return props.readOnly
      ? `啤机部已保存并同步至工程部 · ${savedReport.value.updated_at}`
      : `已保存 · ${savedReport.value.updated_at}`
  }

  return '未保存，可直接填写或打印空表'
})
const reportCanvasStyle = computed(() => ({ width: `${210 * reportZoom.value}mm`, height: `${297 * reportZoom.value}mm` }))
const reportSheetStyle = computed(() => reportZoom.value === 1 ? undefined : ({ transform: `scale(${reportZoom.value})`, transformOrigin: 'top left' }))

function createEmptyTrialReportData(item?: MoldingSampleItem | null): MoldingSampleTrialReportData {
  return {
    mold_supplier: '', sample_category: '', material_name: item?.material ?? '', material_shots: item?.shoot_qty ? String(item.shoot_qty) : '', material_weight: '', color: item?.color ?? '', color_code: item?.pigment_no ?? '', color_shots: '', color_weight: '', virgin_material_shots: '', virgin_material_weight: '', runner_material_shots: '', runner_material_weight: '', water_ratio: '', water_shots: '', water_material_weight: '', water_weight: '', special_requirements: '', front_mold_water: '', rear_mold_water: '', other_trial_requirement: '', other_trial_requirement_note: '', baking_time_hours: '', mold_condition: item?.mold_presence_status === 'in_factory' ? '已在本厂' : item?.mold_presence_status === 'out_of_factory' ? '不在本厂' : '', expected_return_time: '', gross_weight: item?.gross_weight_g ? String(item.gross_weight_g) : '', net_weight: '', plastic_model: '', machine_model: '', machine_no: item?.production_machine ?? '', cooling_time: '', holding_time: '', cycle_time: '', injection_speed: '', ejector_count: '', cushion_pressure: '', clamping_force: '', high_pressure: '', low_pressure: '', pressure_stage_1: '', pressure_stage_2: '', pressure_stage_3: '', pressure_stage_4: '', barrel_temperature_head: '', barrel_temperature_middle: '', barrel_temperature_end: '', molding_mode: '', mold_issues: [], part_issues: [], issue_notes: '', trial_summary: '', trial_round: '', verdict: '', tester_name: props.operatorName, tester_date: '', molding_supervisor_name: '', molding_supervisor_date: '', engineer_name: '', engineer_date: '',
  }
}

function cloneReportData(data: MoldingSampleTrialReportData) {
  return {
    ...data,
    plastic_model: data.plastic_model === '待工程确认' ? '' : data.plastic_model,
    mold_issues: [...data.mold_issues],
    part_issues: [...data.part_issues],
  }
}

function syncSelectedItem(itemId?: string) {
  const nextId = itemId || selectedItemId.value || props.items[0]?.id || ''
  selectedItemId.value = props.items.some((item) => item.id === nextId) ? nextId : (props.items[0]?.id || '')
  const item = props.items.find((entry) => entry.id === selectedItemId.value) ?? null
  const existing = props.reports.find((report) => report.item_id === selectedItemId.value)
  draft.value = existing ? cloneReportData(existing.data) : createEmptyTrialReportData(item)
}

watch(
  () => [props.visible, props.items, props.reports, props.initialItemId] as const,
  ([visible]) => { if (visible) syncSelectedItem(props.initialItemId) },
  { immediate: true, deep: true },
)

function closeDialog() { previewVisible.value = false; reportZoom.value = 1; emit('close') }
function toggleReportZoom() { reportZoom.value = reportZoom.value === 1 ? 1.3 : 1 }
function saveTrialReport() {
  if (selectedItem.value && props.canSave && !props.readOnly) {
    emit('save', { itemId: selectedItem.value.id, data: cloneReportData(draft.value) })
  }
}
function confirmPrint() {
  document.body.classList.add('molding-sample-trial-report-printing')
  document.getElementById('molding-sample-active-print-page')?.remove()
  const pageStyle = document.createElement('style')
  pageStyle.id = 'molding-sample-active-print-page'
  pageStyle.textContent = '@media print { @page { size: A4 portrait; margin: 0; } }'
  document.head.append(pageStyle)
  const cleanUp = () => { document.body.classList.remove('molding-sample-trial-report-printing'); pageStyle.remove() }
  window.addEventListener('afterprint', cleanUp, { once: true })
  window.print()
}
</script>

<template>
  <Transition enter-active-class="transition duration-150 ease-out" enter-from-class="opacity-0" enter-to-class="opacity-100" leave-active-class="transition duration-150 ease-in" leave-from-class="opacity-100" leave-to-class="opacity-0">
    <section v-if="visible && order" class="fixed inset-0 z-[70] bg-slate-950/45 px-3 py-4 backdrop-blur-sm sm:px-5" role="dialog" aria-modal="true" aria-label="试模报告填写与打印" data-testid="molding-sample-trial-report-dialog">
      <div class="mx-auto flex h-full max-w-7xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl shadow-slate-950/30">
        <header class="flex shrink-0 items-center gap-3 border-b border-slate-200 px-4 py-3"><span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-teal-50 text-teal-700"><ClipboardPenLine class="size-4" aria-hidden="true" /></span><div class="min-w-0"><h2 class="text-[15px] font-bold text-slate-950">{{ readOnly ? '试模报告历史 / 打印' : '试模报告填写 / 打印' }}</h2><p class="mt-0.5 text-[11px] text-slate-500">原纸质《工模试模（交模）验收回执》版式 · {{ readOnly ? '已保存记录，只读查看' : '格内填写' }}</p></div><button type="button" class="ml-auto flex h-8 w-8 items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-700" aria-label="关闭试模报告" @click="closeDialog"><X class="size-4" aria-hidden="true" /></button></header>
        <div class="flex shrink-0 flex-wrap items-end gap-3 border-b border-slate-200 bg-slate-50 px-4 py-2.5"><p class="mr-auto text-[11px] text-slate-600">{{ savedStatusText }}；工程资料会自动带入，啤机部直接在原表格对应位置填写。</p><label class="block text-[11px] font-semibold text-slate-600">选择模具明细<select :value="selectedItemId" class="ml-2 h-8 min-w-56 rounded border border-slate-300 bg-white px-2 text-[12px] font-normal text-slate-800 outline-none focus:border-teal-600" @change="syncSelectedItem(($event.target as HTMLSelectElement).value)"><option v-for="item in items" :key="item.id" :value="item.id">{{ item.sort_order }} · {{ item.mold_id || '未填模具编号' }} · {{ item.mold_name || '未填模具名称' }}</option></select></label></div>
        <div class="molding-sample-trial-report-editor min-h-0 flex-1 overflow-auto bg-slate-200 p-4"><div class="molding-sample-trial-report-zoom-canvas" :style="reportCanvasStyle"><MoldingSampleTrialReportSheet v-if="selectedItem" :order="order" :item="selectedItem" :data="draft" :company-name="companyName" :style="reportSheetStyle" :editable="!readOnly" @update:data="draft = $event" /></div></div>
        <footer class="flex shrink-0 flex-wrap justify-end gap-2 border-t border-slate-200 px-4 py-3"><button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-200 px-3 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300" @click="toggleReportZoom"><ZoomIn v-if="reportZoom === 1" class="size-3.5" aria-hidden="true" /><ZoomOut v-else class="size-3.5" aria-hidden="true" />{{ reportZoom === 1 ? '放大报告' : '恢复原尺寸' }}</button><button type="button" class="h-8 rounded-md border border-slate-200 px-3 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300" @click="closeDialog">{{ readOnly ? '返回历史' : '关闭' }}</button><button type="button" :disabled="!selectedItem" class="inline-flex h-8 items-center gap-1.5 rounded-md border border-teal-200 bg-teal-50 px-3 text-[12px] font-semibold text-teal-800 transition hover:bg-teal-100 disabled:cursor-not-allowed disabled:opacity-50" @click="previewVisible = true"><Printer class="size-3.5" aria-hidden="true" />预览 / 打印</button><button v-if="!readOnly" type="button" :disabled="saving || !canSave" class="inline-flex h-8 items-center gap-1.5 rounded-md bg-slate-900 px-3 text-[12px] font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400" @click="saveTrialReport"><Save class="size-3.5" aria-hidden="true" />{{ saving ? '保存中...' : '保存试模报告' }}</button></footer>
      </div>
    </section>
  </Transition>

  <Teleport to="body">
    <section v-if="previewVisible && order && selectedItem" class="fixed inset-0 z-[80] bg-slate-950/50 px-4 py-5 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="试模报告打印预览" data-testid="molding-sample-trial-report-print-preview"><div class="mx-auto flex h-full max-w-7xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl"><header class="flex shrink-0 items-center gap-3 border-b border-slate-200 px-4 py-3"><span class="flex h-9 w-9 items-center justify-center rounded-lg bg-teal-50 text-teal-700"><Printer class="size-4" aria-hidden="true" /></span><div><h2 class="text-[15px] font-bold text-slate-950">试模报告 · 打印预览</h2><p class="mt-0.5 text-[11px] text-slate-500">{{ companyName }} · {{ selectedItem.mold_id || '未填模具编号' }}</p></div><button type="button" class="ml-auto flex h-8 w-8 items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-700" aria-label="关闭试模报告打印预览" @click="previewVisible = false"><X class="size-4" aria-hidden="true" /></button></header><div class="molding-sample-trial-report-editor min-h-0 flex-1 overflow-auto bg-slate-200 p-4"><div class="molding-sample-trial-report-zoom-canvas" :style="reportCanvasStyle"><MoldingSampleTrialReportSheet :order="order" :item="selectedItem" :data="draft" :company-name="companyName" :style="reportSheetStyle" /></div></div><footer class="flex shrink-0 justify-end gap-2 border-t border-slate-200 px-4 py-3"><button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-200 px-3 text-[12px] font-semibold text-slate-600" @click="toggleReportZoom"><ZoomIn v-if="reportZoom === 1" class="size-3.5" aria-hidden="true" /><ZoomOut v-else class="size-3.5" aria-hidden="true" />{{ reportZoom === 1 ? '放大报告' : '恢复原尺寸' }}</button><button type="button" class="h-8 rounded-md border border-slate-200 px-3 text-[12px] font-semibold text-slate-600" @click="previewVisible = false">返回填写</button><button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-md bg-slate-900 px-3 text-[12px] font-semibold text-white" @click="confirmPrint"><Printer class="size-3.5" aria-hidden="true" />确认打印</button></footer></div></section>
    <section class="molding-sample-trial-report-print-root" data-testid="molding-sample-trial-report-print-area" aria-label="试模报告打印内容"><MoldingSampleTrialReportSheet v-if="order && selectedItem" :order="order" :item="selectedItem" :data="draft" :company-name="companyName" /></section>
  </Teleport>
</template>

<style>
.molding-sample-trial-report-zoom-canvas > .molding-trial-report-sheet { box-shadow: 0 1px 8px rgb(15 23 42 / 20%); }
</style>
