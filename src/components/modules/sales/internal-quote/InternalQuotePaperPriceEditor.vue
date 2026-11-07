<script setup lang="ts">
import { Plus, Trash2 } from '@lucide/vue'
import type { QuotePaperPrice } from '@/lib/internalQuotePaper'
const rows = defineModel<QuotePaperPrice[]>({ required: true })
defineProps<{ disabled?: boolean }>()
function add() { rows.value.push({ key: `paper_${crypto.randomUUID().replaceAll('-', '')}`, name: '', price_factor_hkd: '', remark: '' }) }
</script>
<template>
  <div class="paper-editor">
    <p>填写经确认的纸材系数；用于现有英寸展开面积 ÷ 1000 的 HKD 箱价计算。税项仍按本单原规则处理。</p>
    <div class="paper-scroll"><table><thead><tr><th>纸材名称</th><th>系数 HKD</th><th>来源／适用说明</th><th>操作</th></tr></thead><tbody>
      <tr v-for="(row, i) in rows" :key="row.key"><td><input v-model="row.name" :disabled="disabled" maxlength="128" placeholder="例如 A=B" aria-label="纸材名称"></td><td><input :value="row.price_factor_hkd" @input="row.price_factor_hkd = ($event.target as HTMLInputElement).value" :disabled="disabled" type="number" min="0.0001" step="0.0001" aria-label="纸材系数 HKD"></td><td><input v-model="row.remark" :disabled="disabled" maxlength="500" placeholder="供应商、日期或适用产品" aria-label="纸材来源说明"></td><td><button type="button" :disabled="disabled" aria-label="删除纸材" @click="rows.splice(i, 1)"><Trash2 :size="16" /></button></td></tr>
      <tr v-if="!rows.length"><td colspan="4">尚未配置纸材目录，现有报价继续沿用原系数。</td></tr>
    </tbody></table></div>
    <button type="button" :disabled="disabled || rows.length >= 100" @click="add"><Plus :size="16" />新增纸材</button>
    <small>删除已选纸材会要求相关纸箱或平卡重新选择。未确认的价格不会自动填入。</small>
  </div>
</template>
<style scoped>
.paper-editor { display:grid; gap:12px; } .paper-editor p,.paper-editor small { color:var(--muted-foreground); }
.paper-scroll { overflow-x:auto; } table { width:100%; border-collapse:collapse; } th,td { padding:8px; border-bottom:1px solid var(--border); text-align:left; }
input { min-width:100px; width:100%; padding:8px; border:1px solid var(--input); border-radius:6px; background:var(--background); } button { display:inline-flex; align-items:center; gap:6px; justify-self:start; padding:8px; border:1px solid var(--border); border-radius:6px; } button:disabled { opacity:.5; }
</style>
