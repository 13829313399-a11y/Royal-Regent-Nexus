<script setup lang="ts">
import { computed, ref } from 'vue'
import { DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle, DialogTrigger } from 'reka-ui'
import { buzzBeePurchaseUnitHkd, type BuzzBeePurchaseFormula } from '@/lib/internalQuoteSectionPayload'
import type { MoldingMaterialReference } from '@/lib/internalQuoteMoldingReferences'

const props = defineProps<{
  formula?: BuzzBeePurchaseFormula
  materials: MoldingMaterialReference[]
  rate?: number
  quantity: number
  lossRate?: number
  disabled?: boolean
}>()
const emit = defineEmits<{ apply: [value: BuzzBeePurchaseFormula | undefined] }>()
const open = ref(false)
const key = ref('')
const weight = ref<number | ''>('')
const labor = ref<number | ''>('')
const selectionKey = (item: { material: string; grade: string }) => JSON.stringify([item.material, item.grade])
const materials = computed(() => props.materials.filter(item => item.priceHkdLb > 0))
const draft = computed<BuzzBeePurchaseFormula | undefined>(() => {
  const selected = materials.value.find(item => selectionKey(item) === key.value)
  if (!selected || !props.rate || props.rate <= 0 || !Number.isFinite(props.rate)
    || weight.value === '' || !Number.isFinite(weight.value) || weight.value <= 0
    || labor.value === '' || !Number.isFinite(labor.value) || labor.value < 0) return
  return { material: selected.material, grade: selected.grade, price_hkd_lb: selected.priceHkdLb, weight_g: weight.value, labor_rmb: labor.value }
})
const unit = computed(() => draft.value ? buzzBeePurchaseUnitHkd(draft.value, Number(props.rate)) : 0)

function toggle(next: boolean) {
  if (next) {
    key.value = props.formula ? selectionKey(props.formula) : ''
    weight.value = props.formula?.weight_g ?? ''
    labor.value = props.formula?.labor_rmb ?? ''
  }
  open.value = next
}
function apply(value?: BuzzBeePurchaseFormula) {
  if (props.disabled) return
  emit('apply', value)
  open.value = false
}
</script>

<template>
  <DialogRoot :open="open" @update:open="toggle">
    <DialogTrigger type="button" class="fx-trigger" :class="{ active: formula }" :aria-pressed="!!formula" aria-label="胶料加啤工计价公式" title="胶料加啤工计价公式">ƒx</DialogTrigger>
    <DialogPortal>
      <DialogOverlay class="fx-overlay" />
      <DialogContent class="fx-dialog">
        <DialogTitle>其他外购 · 胶料加啤工</DialogTitle>
        <DialogDescription>每条港币单价 = 胶料每磅港币价 ÷ 454 × 单条克重 + 单条啤工人民币 ÷ 汇率。</DialogDescription>
        <label>胶料及料型
          <select v-model="key" :disabled="disabled">
            <option value="">选择本报价采用的胶料</option>
            <option v-for="item in materials" :key="selectionKey(item)" :value="selectionKey(item)">{{ item.material }} · {{ item.grade }}（{{ item.priceHkdLb }} HKD/lb）</option>
          </select>
        </label>
        <label>单条重量（g）<input v-model.number="weight" type="number" min="0" step="any" :disabled="disabled"></label>
        <label>单条啤工（RMB）<input v-model.number="labor" type="number" min="0" step="any" :disabled="disabled"></label>
        <div v-if="draft" class="fx-result" aria-live="polite">
          <div>单价　{{ draft.price_hkd_lb }} ÷ 454 × {{ draft.weight_g }} + {{ draft.labor_rmb }} ÷ {{ rate }} ≈ <strong>{{ unit.toFixed(4) }} HKD/条</strong></div>
          <div>金额　单价 × 用量 {{ quantity }} × 损耗率 {{ lossRate ?? 1 }} ≈ <strong>{{ (unit * quantity * (lossRate ?? 1)).toFixed(4) }} HKD</strong></div>
        </div>
        <p v-else-if="!materials.length">本报价尚无可用胶料价格，请先维护采用价目表。</p>
        <p v-else-if="key && !materials.some(item => selectionKey(item) === key)">当前价目表中找不到已选料型，请重新选择胶料。</p>
        <p v-else-if="!rate || rate <= 0">请先设置本报价的 RMB/HKD 汇率。</p>
        <footer>
          <button v-if="formula && !disabled" type="button" @click="apply()">转为手填单价</button>
          <DialogClose type="button">{{ disabled ? '关闭' : '取消' }}</DialogClose>
          <button v-if="!disabled" type="button" class="confirm" :disabled="!draft" @click="draft && apply(draft)">采用公式</button>
        </footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.fx-trigger { cursor: pointer; color: #0f766e; font-weight: 700; }
.fx-trigger.active { background: #ccfbf1; }
.fx-overlay { position: fixed; inset: 0; z-index: 120; background: rgb(15 23 42 / 48%); }
.fx-dialog { position: fixed; z-index: 121; top: 50%; left: 50%; transform: translate(-50%, -50%); width: min(29rem, 94vw); max-height: 90dvh; overflow: auto; display: grid; gap: .85rem; padding: 1.25rem; border-radius: .85rem; background: white; color: #334155; box-shadow: 0 20px 60px #0f172a40; font-size: .875rem; }
.fx-dialog h2 { margin: 0; font-size: 1.15rem; color: #115e59; }
.fx-dialog p { margin: 0; }
.fx-dialog label { display: grid; gap: .3rem; font-weight: 600; }
.fx-dialog input, .fx-dialog select, .fx-dialog button { border: 1px solid #cbd5e1; border-radius: .4rem; padding: .45rem .6rem; }
.fx-result { padding: .75rem; border-radius: .4rem; background: #f0fdfa; line-height: 1.7; font-variant-numeric: tabular-nums; }
.fx-dialog footer { display: flex; justify-content: flex-end; gap: .5rem; flex-wrap: wrap; }
.fx-dialog .confirm { color: white; background: #0f766e; }
.fx-dialog button:disabled { opacity: .5; }
</style>
