<script setup lang="ts">
import { CircleDollarSign, Plus, Save, Trash2, X } from '@lucide/vue'
import { ref, watch } from 'vue'

interface MaterialRow {
  material: string
  grade: string
  price_hkd_lb: string
}

const props = withDefaults(defineProps<{
  open: boolean
  productName: string
  snapshot: Record<string, unknown>
  busy?: boolean
}>(), { busy: false })

const emit = defineEmits<{
  close: []
  save: [rows: MaterialRow[]]
}>()

const rows = ref<MaterialRow[]>([])
const errorMessage = ref('')

function snapshotRows(snapshot: Record<string, unknown>) {
  const source = snapshot.material_prices
  if (!source || typeof source !== 'object' || Array.isArray(source)) return []
  return Object.entries(source as Record<string, unknown>).map(([key, value]) => {
    const separator = key.indexOf('|')
    return {
      material: separator >= 0 ? key.slice(0, separator) : key,
      grade: separator >= 0 ? key.slice(separator + 1) : '',
      price_hkd_lb: String(value ?? ''),
    }
  }).sort((left, right) => `${left.material}|${left.grade}`.localeCompare(`${right.material}|${right.grade}`, 'zh-CN'))
}

watch(() => [props.open, props.snapshot] as const, ([open]) => {
  if (!open) return
  rows.value = snapshotRows(props.snapshot)
  errorMessage.value = ''
}, { immediate: true })

function addRow() {
  rows.value.push({ material: '', grade: '', price_hkd_lb: '' })
}

function save() {
  errorMessage.value = ''
  const normalized = rows.value.map((row) => ({
    material: row.material.trim(),
    grade: row.grade.trim(),
    price_hkd_lb: String(row.price_hkd_lb).trim(),
  }))
  if (normalized.some((row) => !row.material || !row.grade || !(Number(row.price_hkd_lb) > 0))) {
    errorMessage.value = '每一项都必须填写材质、料型和大于 0 的 HKD/Lb 单价。'
    return
  }
  const keys = normalized.map((row) => `${row.material.toLowerCase()}|${row.grade.toLowerCase()}`)
  if (new Set(keys).size !== keys.length) {
    errorMessage.value = '材质和料型组合不能重复。'
    return
  }
  emit('save', normalized)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="quote-material-backdrop" role="presentation" @mousedown.self="emit('close')">
      <section class="quote-material-dialog" role="dialog" aria-modal="true" aria-label="本报价专用料价">
        <header>
          <div class="quote-material-title"><span><CircleDollarSign /></span><div><h2>本报价专用料价</h2><p>{{ productName }} · 只影响当前款，不修改厂区基础料价</p></div></div>
          <button type="button" aria-label="关闭本报价专用料价" @click="emit('close')"><X /></button>
        </header>
        <div class="quote-material-body">
          <div class="quote-material-notice">保存后服务器会建立新的报价快照，并重新计算所有依赖这些料价的部门内容。</div>
          <div class="quote-material-table-wrap">
            <table>
              <thead><tr><th>#</th><th>材质</th><th>料型</th><th>单价 HKD/Lb</th><th /></tr></thead>
              <tbody>
                <tr v-for="(row, index) in rows" :key="index">
                  <td>{{ index + 1 }}</td>
                  <td><input v-model="row.material" :disabled="busy" aria-label="专用料价材质"></td>
                  <td><input v-model="row.grade" :disabled="busy" aria-label="专用料价料型"></td>
                  <td><input v-model="row.price_hkd_lb" :disabled="busy" type="number" min="0.0001" step="0.0001" aria-label="专用料价 HKD/Lb"></td>
                  <td><button type="button" class="delete" :disabled="busy" aria-label="删除专用料价" @click="rows.splice(index, 1)"><Trash2 /></button></td>
                </tr>
                <tr v-if="!rows.length"><td colspan="5" class="empty">当前没有专用料价。可以新增；保存空清单后，依赖材料价的项目将显示缺价校验。</td></tr>
              </tbody>
            </table>
          </div>
          <button type="button" class="add" :disabled="busy || rows.length >= 200" @click="addRow"><Plus />新增料价</button>
          <p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
        </div>
        <footer><button type="button" class="secondary" :disabled="busy" @click="emit('close')">取消</button><button type="button" class="primary" :disabled="busy" @click="save"><Save />{{ busy ? '保存并重算中…' : '保存专用料价' }}</button></footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.quote-material-backdrop{position:fixed;inset:0;z-index:110;display:grid;place-items:center;padding:24px;background:rgb(15 23 42/.58);backdrop-filter:blur(4px)}.quote-material-dialog{display:grid;width:min(820px,100%);max-height:calc(100vh - 48px);overflow:hidden;border:1px solid #cbd5e1;border-radius:17px;background:#fff;box-shadow:0 28px 80px rgb(15 23 42/.3)}header,footer{display:flex;align-items:center;justify-content:space-between;gap:12px;background:#f8fafc;padding:15px 18px}header{border-bottom:1px solid #e2e8f0}footer{justify-content:flex-end;border-top:1px solid #e2e8f0}.quote-material-title{display:flex;align-items:center;gap:11px}.quote-material-title>span{display:grid;width:38px;height:38px;place-items:center;border-radius:10px;background:#ccfbf1;color:#0f766e}.quote-material-title svg{width:20px}.quote-material-title h2{margin:0;color:#0f172a;font-size:18px}.quote-material-title p{margin:3px 0 0;color:#64748b;font-size:11px}header>button{display:grid;width:34px;height:34px;place-items:center;border:0;border-radius:8px;background:#fff;color:#64748b}header>button svg{width:17px}.quote-material-body{display:grid;min-height:0;gap:10px;overflow:auto;padding:16px 18px}.quote-material-notice{border:1px solid #99f6e4;border-radius:9px;background:#f0fdfa;padding:9px 11px;color:#0f766e;font-size:11px}.quote-material-table-wrap{overflow:auto;border:1px solid #e2e8f0;border-radius:10px}table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid #e2e8f0;padding:7px;text-align:left}th{background:#f8fafc;color:#64748b;font-size:10px}td{color:#475569;font-size:11px}th:first-child,td:first-child{width:42px;text-align:center}th:last-child,td:last-child{width:42px}input{width:100%;border:1px solid #dbe5ea;border-radius:7px;padding:7px 8px;color:#0f172a;font-size:12px}.delete{display:grid;width:28px;height:28px;place-items:center;border:1px solid #fecaca;border-radius:7px;background:#fff;color:#dc2626}.delete svg{width:13px}.empty{padding:28px 14px;color:#94a3b8;text-align:center}.add{display:inline-flex;width:max-content;align-items:center;gap:5px;border:1px solid #99f6e4;border-radius:8px;background:#f0fdfa;padding:7px 10px;color:#0f766e;font-size:11px;font-weight:900}.add svg,footer svg{width:14px}.error{margin:0;border-radius:8px;background:#fef2f2;padding:8px 10px;color:#b91c1c;font-size:11px}.secondary,.primary{display:inline-flex;min-height:36px;align-items:center;gap:6px;border-radius:8px;padding:0 13px;font-size:12px;font-weight:900}.secondary{border:1px solid #cbd5e1;background:#fff;color:#475569}.primary{border:1px solid #0f766e;background:#0f766e;color:#fff}button:disabled{cursor:not-allowed;opacity:.5}
</style>
