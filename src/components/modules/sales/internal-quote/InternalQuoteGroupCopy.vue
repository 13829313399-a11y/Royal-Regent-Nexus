<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { internalQuoteApi, type ApiInternalQuoteAlternative } from '@/api/internalQuote'
import { useAuthStore } from '@/stores/auth'
import { useQuoteOperationScope } from '@/features/internal-quote/operationScope'
import { getApiErrorMessage } from '@/lib/http'
import { chooseWorkingVersion, readWorkingVersions, rememberWorkingVersion } from '@/lib/internalQuoteWorkingVersions'
import type { InternalQuote } from '@/types/internalQuoteDesk'

const props = defineProps<{ quote: InternalQuote; kind: 'scenario' | 'version'; hasUnsavedChanges?: () => boolean }>()
const emit = defineEmits<{ close: []; open: [id: string] }>()
const auth = useAuthStore(), captureScope = useQuoteOperationScope(() => props.quote.id)
const rows = ref<Array<{ root: string; name: string; selected: string; revision: number; familyRevision: number; options: ApiInternalQuoteAlternative[]; loading: boolean; sequence: number }>>([])
const name = ref(''), note = ref(''), error = ref(''), loading = ref(true), busy = ref(false)
let generation = 0
onBeforeUnmount(() => { generation++ })
async function load() {
  const current = ++generation
  loading.value = true; error.value = ''; rows.value = []
  try {
    const [products, group] = await Promise.all([internalQuoteApi.listBatchProducts(props.quote.id), internalQuoteApi.getAlternativeGroup(props.quote.id)])
    const remembered = readWorkingVersions(auth.currentUser?.id || '', props.quote.factoryId, props.quote.documentQuoteId || props.quote.id)
    const result = await Promise.all(products.map(async product => {
      const family = await internalQuoteApi.listAlternatives(product.quote_id)
      const selected = chooseWorkingVersion(family.items, props.quote.id, group?.products.find(p => p.product_root_id === family.family_id)?.quote_id, remembered.products[family.family_id], product.quote_id)
      const quote = selected ? await internalQuoteApi.get(selected) : undefined
      return { root: family.family_id, name: product.product_name, selected, revision: quote?.header_revision ?? 0,
        familyRevision: family.revision, options: family.items.filter(item => !item.archived), loading: false, sequence: 0 }
    }))
    if (current === generation) rows.value = result
  } catch (cause) { if (current === generation) error.value = getApiErrorMessage(cause) }
  finally { if (current === generation) loading.value = false }
}
watch(() => props.quote.id, load, { immediate: true })
async function selectVersion(index: number) {
  const row = rows.value[index]!, id = row.selected, current = generation, sequence = ++row.sequence
  row.loading = true; row.revision = 0; error.value = ''
  try {
    const quote = await internalQuoteApi.get(id)
    if (current === generation && sequence === row.sequence) row.revision = quote.header_revision
  } catch (cause) { if (current === generation && sequence === row.sequence) error.value = getApiErrorMessage(cause) }
  finally { if (current === generation && sequence === row.sequence) row.loading = false }
}
async function copy() {
  if (busy.value || loading.value || rows.value.length < 2 || rows.value.some(r => r.loading || !r.selected || !r.revision)) return
  error.value = ''
  if (props.hasUnsavedChanges?.()) { error.value = '请先保存当前款，再复制整组方案。'; return }
  if (!note.value.trim() || (props.kind === 'scenario' && !name.value.trim())) { error.value = '请填写方案名称和修改说明。'; return }
  busy.value = true
  const check = captureScope(), current = generation, root = props.quote.productRootId || props.quote.id
  try {
    const result = await internalQuoteApi.copyAlternativeGroup(props.quote.id, {
      kind: props.kind, name: name.value.trim(), change_note: note.value.trim(),
      products: rows.value.map(r => ({ quote_id: r.selected, revision: r.revision, family_revision: r.familyRevision })),
    })
    check()
    if (current !== generation) return
    for (const quote of result.quotes) rememberWorkingVersion(auth.currentUser?.id || '', {
      id: quote.id, factoryId: quote.factory_id, documentQuoteId: quote.document_quote_id,
      productRootId: quote.product_root_id, status: quote.status,
    })
    const selected = result.group.products.find(p => p.product_root_id === root)?.quote_id || result.quotes[0]!.id
    emit('open', selected)
  } catch (cause) { if (current === generation) error.value = getApiErrorMessage(cause) }
  finally { if (current === generation) busy.value = false }
}
</script>

<template>
  <div class="group-copy-backdrop">
    <section role="dialog" aria-modal="true" aria-labelledby="group-copy-title" class="group-copy-dialog">
      <h2 id="group-copy-title">{{ kind === 'scenario' ? '整组复制为新方案' : '整组复制新版本' }}</h2>
      <p>在当前报价内一次复制全部产品。每款保留自己的资料、图片和参考价格，原版本不变。</p>
      <p v-if="loading" role="status">正在读取各款来源版本…</p>
      <label v-for="(row, index) in rows" :key="row.root">{{ index + 1 }}. {{ row.name }}
        <select v-model="row.selected" :aria-label="`${row.name} 来源版本`" :disabled="busy || row.loading" @change="selectVersion(index)">
          <option disabled value="">原工作版本不可用，请选择来源</option>
          <option v-for="option in row.options" :key="option.quote_id" :value="option.quote_id">{{ option.scenario_name }} · {{ option.version_label }}{{ option.status === 'exported' ? '（已输出）' : '' }}</option>
        </select>
      </label>
      <label v-if="kind === 'scenario'">整组方案名称<input v-model="name" maxlength="128" :disabled="busy" placeholder="例如：客户调价方案"></label>
      <label>修改说明<textarea v-model="note" maxlength="2000" :disabled="busy" /></label>
      <p>复制各款全部参与部门；目标产能、成品用量及其他业务输入沿用所选来源版本。</p>
      <p v-if="error" role="alert">{{ error }}</p>
      <footer><button :disabled="busy || loading" @click="load">重新读取来源</button><button :disabled="busy" @click="emit('close')">取消</button><button :disabled="busy || loading || rows.length < 2 || rows.some(r => r.loading || !r.selected || !r.revision)" @click="copy">{{ busy ? '整组复制中…' : `确认复制全部 ${rows.length} 款` }}</button></footer>
    </section>
  </div>
</template>

<style scoped>
.group-copy-backdrop{position:fixed;inset:0;z-index:80;display:grid;place-items:center;background:#0f172a66;padding:20px}.group-copy-dialog{width:min(640px,100%);max-height:85vh;overflow:auto;background:white;border:1px solid #99d5cc;border-radius:14px;padding:24px;color:#334155}.group-copy-dialog h2{font-size:18px;color:#134e4a}.group-copy-dialog p{font-size:13px;line-height:1.6}.group-copy-dialog label{display:grid;gap:6px;margin:14px 0;font-size:14px}.group-copy-dialog input,.group-copy-dialog textarea,.group-copy-dialog select{width:100%;border:1px solid #cbd5e1;border-radius:8px;padding:9px;background:white}.group-copy-dialog footer{display:flex;justify-content:flex-end;gap:10px;flex-wrap:wrap;margin-top:20px}.group-copy-dialog button{padding:9px 12px;border:1px solid #99d5cc;border-radius:8px;color:#0f766e;background:#f0fdfa}.group-copy-dialog button:disabled{opacity:.5}.group-copy-dialog [role=alert]{color:#b91c1c;white-space:pre-line}
</style>
