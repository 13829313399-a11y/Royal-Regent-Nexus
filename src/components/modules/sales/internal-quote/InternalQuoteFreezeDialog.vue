<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Snowflake, X } from '@lucide/vue'
import { internalQuoteApi, type ApiInternalQuoteFreezeOptions } from '@/api/internalQuote'
import { useAuthStore } from '@/stores/auth'
import { useDialogFocus } from '@/composables/useDialogFocus'
import { readWorkingVersions } from '@/lib/internalQuoteWorkingVersions'
import { getApiErrorMessage } from '@/lib/http'
import type { InternalQuote } from '@/types/internalQuoteDesk'

const props = defineProps<{ quote: InternalQuote }>()
const emit = defineEmits<{ close: []; completed: [] }>()
const auth = useAuthStore()
const dialog = ref<HTMLElement | null>(null)
const rows = ref<Array<ApiInternalQuoteFreezeOptions['products'][number] & { selected: string }>>([])
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const reason = ref('')
const frozen = ref(true)
let generation = 0
onBeforeUnmount(() => { generation++ })
function close() { if (!busy.value) emit('close') }
useDialogFocus(() => true, dialog, { onEscape: close, inertBackground: true })
const selected = computed(() => rows.value.map(row => row.options.find(option => option.quote_id === row.selected)))
const canSubmit = computed(() => !loading.value && !busy.value && !!reason.value.trim() && rows.value.length > 0
  && selected.value.every(item => !!item?.header_revision)
  && selected.value.some(item => (item?.final_release_status === 'issued') !== frozen.value))
async function load() {
  const current = ++generation
  loading.value = true; rows.value = []; error.value = ''
  try {
    const data = await internalQuoteApi.getFreezeOptions(props.quote.id)
    if (generation !== current) return
    const remembered = readWorkingVersions(auth.currentUser?.id || '', props.quote.factoryId, props.quote.documentQuoteId || props.quote.id)
    rows.value = data.products.map(row => {
      const requested = remembered.products[row.product_root_id] || row.product_root_id
      return { ...row, selected: row.options.some(item => item.quote_id === requested) ? requested : '' }
    })
    frozen.value = !selected.value.every(item => item?.final_release_status === 'issued')
  } catch (cause) { if (generation === current) error.value = getApiErrorMessage(cause) }
  finally { if (generation === current) loading.value = false }
}
watch(() => [props.quote.id, props.quote.factoryId, auth.currentUser?.id], load, { immediate: true })
async function submit() {
  if (!canSubmit.value) return
  const current = generation
  busy.value = true; error.value = ''
  try {
    await internalQuoteApi.setDocumentFrozen(props.quote.id, {
      frozen: frozen.value, reason: reason.value.trim(),
      products: rows.value.map((row, index) => ({ quote_id: row.selected,
        revision: selected.value[index]!.header_revision!, family_revision: row.family_revision })),
    })
    if (generation === current) emit('completed')
  } catch (cause) {
    // Keep the selected scope/revisions until the user explicitly reloads and reviews.
    if (generation === current) error.value = getApiErrorMessage(cause)
  } finally { if (generation === current) busy.value = false }
}
</script>

<template>
  <Teleport to="body">
    <div class="quote-freeze-backdrop" @click.self="close">
      <section ref="dialog" class="quote-freeze-dialog" role="dialog" aria-modal="true" aria-labelledby="quote-freeze-title" tabindex="-1">
        <header><div><Snowflake aria-hidden="true" /><h2 id="quote-freeze-title">整单冻结管理</h2></div><button type="button" :disabled="busy" aria-label="关闭冻结管理" @click="close"><X /></button></header>
        <form @submit.prevent="submit">
          <div class="quote-freeze-body">
            <p><strong>{{ quote.quoteNo }}</strong> · 全部当前产品一起操作。已优先读取本人上次工作版本，请核对每款的方案和版本。</p>
            <p>输出后仍可修改报价及汇总表。冻结后锁定系统资料；解除冻结可继续修改同一版本。历史导出文件始终保留。</p>
            <fieldset :disabled="busy || loading" class="quote-freeze-mode"><legend>本次操作</legend>
              <label><input v-model="frozen" type="radio" :value="true" name="freeze-mode">冻结整单</label>
              <label><input v-model="frozen" type="radio" :value="false" name="freeze-mode">解除整单冻结</label>
            </fieldset>
            <p v-if="loading" role="status">正在读取全部产品和版本…</p>
            <label v-for="row in rows" :key="row.product_root_id" class="quote-freeze-product">
              <strong>{{ row.product_name }}</strong>
              <select v-model="row.selected" :aria-label="`${row.product_name} 当前版本`" :disabled="busy">
                <option disabled value="">请选择本次操作的当前版本</option>
                <option v-for="option in row.options" :key="option.quote_id" :value="option.quote_id">
                  {{ option.scenario_name }} · {{ option.version_label }} · {{ option.final_release_status === 'issued' ? '已冻结' : option.final_release_status === 'output' ? '已输出，可修改' : '可修改' }}
                </option>
              </select>
            </label>
            <p class="quote-freeze-note">{{ frozen ? '冻结前会检查全部当前产品的资料和核价，保留对应输出文件；任一款未就绪，整单均不冻结。' : '已被客户采用的版本须先取消采用。解除后仍保留原资料及历史文件，修改后重新输出即可。' }}</p>
            <label class="quote-freeze-product">操作说明<textarea v-model="reason" :disabled="busy" maxlength="2000" rows="2" required placeholder="例如：本轮报价已确认 / 客户要求微调" /></label>
            <p v-if="error" role="alert" class="quote-freeze-error">{{ error }}</p>
          </div>
          <footer><button type="button" :disabled="busy || loading" @click="load">重新读取</button><button type="button" :disabled="busy" @click="close">取消</button>
            <button type="submit" class="primary" :disabled="!canSubmit">{{ busy ? '处理中…' : frozen ? `冻结全部 ${rows.length} 款` : `解除全部 ${rows.length} 款冻结` }}</button></footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.quote-freeze-backdrop{position:fixed;inset:0;z-index:90;display:grid;place-items:center;padding:20px;background:#0f172a66}
.quote-freeze-dialog{width:min(680px,100%);max-height:90dvh;display:flex;flex-direction:column;background:#fff;border:1px solid #cce4df;border-radius:18px;box-shadow:0 24px 64px #0f172a33;color:#183b36}
.quote-freeze-dialog header{display:flex;align-items:center;justify-content:space-between;padding:20px 24px;border-bottom:1px solid #e2eeeb;background:#f1faf7;border-radius:18px 18px 0 0}
.quote-freeze-dialog header div{display:flex;align-items:center;gap:10px}.quote-freeze-dialog h2{font-size:19px;margin:0}.quote-freeze-dialog header svg{width:21px;height:21px}
.quote-freeze-dialog form{display:flex;flex-direction:column;min-height:0}.quote-freeze-body{overflow:auto;padding:4px 24px 20px;min-height:0}
.quote-freeze-dialog p{font-size:13px;line-height:1.65;color:#5c7872}.quote-freeze-mode{display:flex;gap:20px;border:1px solid #d4e6e2;border-radius:10px;padding:12px}.quote-freeze-mode legend{font-size:13px}.quote-freeze-mode label{display:flex;gap:6px;align-items:center}
.quote-freeze-product{display:grid;gap:8px;font-size:14px;margin-top:16px}.quote-freeze-product select,.quote-freeze-product textarea{width:100%;box-sizing:border-box;border:1px solid #bcd7d1;border-radius:8px;padding:10px;background:#fff;color:inherit}
.quote-freeze-dialog .quote-freeze-note{background:#f1faf7;padding:12px;border-radius:8px}.quote-freeze-dialog .quote-freeze-error{color:#b91c1c;white-space:pre-wrap}
.quote-freeze-dialog footer{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:10px;padding:16px 24px;border-top:1px solid #e2eeeb}.quote-freeze-dialog button{border:1px solid #bdd8d2;border-radius:8px;background:#fff;padding:9px 14px;color:#17675c}.quote-freeze-dialog button.primary{background:#087f74;color:white;border-color:#087f74}.quote-freeze-dialog button:disabled{opacity:.5;cursor:not-allowed}
@media(max-width:600px){.quote-freeze-backdrop{padding:10px}.quote-freeze-dialog header,.quote-freeze-dialog footer{padding:14px}.quote-freeze-body{padding:0 14px 14px}.quote-freeze-dialog footer button.primary{flex:1}}
</style>
