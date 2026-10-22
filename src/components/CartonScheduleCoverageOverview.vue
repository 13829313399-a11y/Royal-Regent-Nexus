<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import StatusPill from '@/components/common/StatusPill.vue'
import { cartonScheduleCoverageApi as api, type ScheduleCoverageCustomer } from '@/api/cartonScheduleCoverage'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDateTime } from '@/lib/dateTime'
import '@/features/carton-procurement/layout.css'

const props = defineProps<{ factoryId: string; viewerKey?: string; search?: string }>()
const emit = defineEmits<{ customer: [code: string]; missing: [code: string]; source: [batchId: string] }>()
const rows = ref<ScheduleCoverageCustomer[]>([]), loading = ref(false), error = ref(''), filter = ref('ALL')
const visible = computed(() => rows.value.filter(row => (!props.search?.trim() || `${row.customer_code} ${row.customer_name}`.toLocaleLowerCase().includes(props.search.trim().toLocaleLowerCase()))
  && (filter.value === 'ALL' || filter.value === 'NO_IMPORT' && !row.latest_import || filter.value === 'MISSING' && row.pending_count > 0 || filter.value === 'INACTIVE' && row.status === 'INACTIVE')))
const mode = (value: string) => value === 'FULL' ? '全量声明' : value === 'INCREMENTAL' ? '增量更新' : '范围未声明'
let generation = 0, controller = new AbortController()
watch(() => [props.factoryId, props.viewerKey], () => { generation++; controller.abort(); controller = new AbortController(); rows.value = []; error.value = ''; filter.value = 'ALL'; void load() }, { immediate: true, flush: 'sync' })
async function load() {
  const token = ++generation
  loading.value = true; error.value = ''
  try {
    const result = await api.workspace(props.factoryId, { status: 'PENDING', limit: 1, offset: 0 }, controller.signal)
    if (token === generation) rows.value = result.customers
  } catch (cause) { if (token === generation) { rows.value = []; error.value = getApiErrorMessage(cause) } }
  finally { if (token === generation) loading.value = false }
}
onBeforeUnmount(() => { generation++; controller.abort() })
</script>

<template>
  <section class="space-y-4" aria-label="客户排期覆盖总览">
    <header class="rounded-xl border border-teal-200 bg-card p-4"><div class="flex flex-wrap items-start justify-between gap-3"><div><h2 class="text-base font-semibold">客户排期覆盖总览</h2><p class="mt-2 text-xs leading-5 text-muted-foreground">按本厂每个客户查看最近导入、最近全量声明及缺行待核实。增量不代表完整覆盖；待核实数仅指缺行，不是全部未下单或全部异常。</p></div><Button type="button" variant="outline" size="sm" :disabled="loading" @click="load">刷新客户覆盖</Button></div><div class="mt-3 flex flex-wrap items-center gap-3 text-xs"><label>显示范围<select v-model="filter" aria-label="客户覆盖显示范围" class="ml-2 h-9 rounded-lg border border-input bg-card px-3"><option value="ALL">全部客户</option><option value="NO_IMPORT">尚无导入</option><option value="MISSING">有缺行待核实</option><option value="INACTIVE">已停用客户</option></select></label><span v-if="!loading && !error" class="text-muted-foreground">显示 {{ visible.length }} / {{ rows.length }} 个客户</span></div></header>
    <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">客户覆盖读取失败：{{ error }}。请刷新核对，不能据此认定没有缺行。</p><p v-if="loading && !rows.length" role="status" class="p-6 text-sm text-muted-foreground">正在读取全部客户的覆盖声明…</p>
    <div v-if="visible.length" class="overflow-hidden rounded-xl border bg-card"><div class="carton-table-wrap overflow-x-auto"><table class="carton-table-fit w-full text-left text-xs" aria-label="客户排期覆盖明细"><thead class="bg-muted/50 text-muted-foreground"><tr><th class="p-3">客户</th><th class="p-3">最近导入 / 版本</th><th class="p-3">最近全量声明</th><th class="p-3">缺行 / 排除依据</th><th class="p-3">查看</th></tr></thead><tbody class="divide-y"><tr v-for="row in visible" :key="row.customer_code"><td data-label="客户" class="break-words p-3"><b>{{ row.customer_name }}</b><p class="mt-1 text-muted-foreground">{{ row.customer_code === '__UNBOUND__' ? '历史来源保留原客户依据' : row.customer_code }}</p><StatusPill v-if="row.status === 'INACTIVE'" class="mt-2" label="已停用 · 只读" tone="slate" compact /></td><td data-label="最近导入 / 版本" class="break-words p-3"><template v-if="row.latest_import"><b>{{ mode(row.latest_import.scope_mode) }}</b><p class="mt-1">排期版本 {{ row.latest_import.as_of_date || '未声明' }}</p><p class="mt-1 text-muted-foreground">上传 {{ formatBusinessDateTime(row.latest_import.created_at) }}</p><p class="mt-1">{{ row.latest_import.filename }}</p></template><span v-else class="text-muted-foreground">尚无导入</span></td><td data-label="最近全量声明" class="p-3 tabular-nums"><template v-if="row.full_coverage"><b>客户交期 {{ row.full_coverage.coverage_start }} 至 {{ row.full_coverage.coverage_end }}</b><p class="mt-1">含首尾 · 排期版本 {{ row.full_coverage.as_of_date }}</p><p class="mt-2 text-muted-foreground">仅此声明段，不推定其他日期已覆盖</p><Button type="button" variant="link" size="sm" class="mt-1 h-auto px-0" :disabled="loading" @click="emit('source', row.full_coverage.batch_id)">查看最近全量原批次</Button></template><span v-else class="text-muted-foreground">{{ row.customer_code === '__UNBOUND__' ? '未绑定客户，不推断覆盖' : '尚无有效全量声明' }}</span></td><td data-label="缺行 / 排除依据" class="p-3"><b class="tabular-nums" :class="row.pending_count ? 'text-amber-800' : 'text-muted-foreground'">缺行待核实 {{ row.pending_count }} 项</b><p class="mt-2">比较排除 {{ row.excluded_count }} 行</p><Button v-if="row.excluded_count && row.latest_import" type="button" variant="link" size="sm" class="mt-1 h-auto px-0" :disabled="loading" @click="emit('source', row.latest_import.batch_id)">查看原批次排除明细</Button></td><td data-label="查看" class="space-y-2 p-3"><Button type="button" variant="outline" size="sm" :disabled="loading" @click="emit('customer', row.customer_code)">排期明细</Button><Button type="button" variant="outline" size="sm" :disabled="loading" @click="emit('missing', row.customer_code)">缺行核实</Button></td></tr></tbody></table></div></div>
    <p v-else-if="!loading && !error" class="rounded-xl border bg-card p-8 text-center text-sm text-muted-foreground">{{ rows.length ? '没有匹配的客户覆盖记录。' : '本厂尚无可查看的客户覆盖记录。' }}</p>
  </section>
</template>
