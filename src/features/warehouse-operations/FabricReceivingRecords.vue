<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { fabricReceivingApi as api, materialCategoryLabels, type FabricReceipt, type FabricStockBatch } from '@/api/fabricReceiving'

const props = defineProps<{ mode: 'receipts' | 'stock' | 'movements' }>()
const search = ref(''), offset = ref(0), total = ref<number>(), busy = ref(false), error = ref('')
const receipts = ref<FabricReceipt[]>([]), stock = ref<FabricStockBatch[]>([])
let sequence = 0
async function load() {
  const ticket = ++sequence
  busy.value = true; error.value = ''; total.value = undefined; receipts.value = []; stock.value = []
  try {
    if (props.mode === 'receipts') {
      const result = await api.receipts(search.value.trim(), offset.value)
      if (ticket === sequence) { total.value = result.total; receipts.value = result.items }
    } else {
      const result = await api.stock(search.value.trim(), offset.value)
      if (ticket === sequence) { total.value = result.total; stock.value = result.items }
    }
  } catch (e) { if (ticket === sequence) error.value = getApiErrorMessage(e) }
  finally { if (ticket === sequence) busy.value = false }
}
function query() { offset.value = 0; void load() }
watch(() => props.mode, () => { search.value = ''; offset.value = 0; void load() }, { immediate: true })
onBeforeUnmount(() => { sequence++ })
</script>

<template>
  <div class="fabric-receiving-records">
    <div class="warehouse-table-heading"><div><h2>{{ mode === 'receipts' ? '实际入库记录' : mode === 'stock' ? '本系统批次库存' : '实际入库流水' }}</h2><p>数量来自仓库已确认的本次实收。这里只包含本系统登记的入库，不含历史库存期初；新批次为待检，质检放行与发料尚未开放。</p></div></div>
    <form class="fabric-list-controls" @submit.prevent="query"><label>查找记录<input v-model="search" aria-label="查找实际入库记录" type="search" maxlength="128" placeholder="采购单 / 送货依据 / 物料 / 供应商 / 仓位" :disabled="busy" /></label><Button type="submit" variant="outline" :disabled="busy">查询 / 刷新</Button><RouterLink :to="{ path: '/modules/pmc-warehouse/fabric-warehouse/receipts', query: { factory: 'huakang-c', view: 'pending' } }" class="fabric-import-link">待收料登记入库</RouterLink></form>
    <p v-if="busy" class="fabric-message" role="status">正在查询实际入库记录…</p><p v-if="error" class="fabric-error" role="alert">{{ error }}</p>
    <div class="warehouse-table-scroll" tabindex="0" role="region" :aria-label="mode === 'receipts' ? '实际入库记录' : '实际库存明细'">
      <table v-if="mode === 'receipts'"><thead><tr><th>入库单 / 日期</th><th>采购来源 / 供应商</th><th>物料 / 分类</th><th>本次实收</th><th>送货依据</th><th>登记人</th><th>实物明细</th></tr></thead><tbody><tr v-for="record in receipts" :key="record.id">
        <td>{{ record.id }}<small>{{ record.receipt_date }}</small></td><td>{{ record.facts.order_no }}<small>{{ record.facts.supplier }}</small><small>{{ record.facts.source_category === 'SUPPLEMENT' ? '补数追货' : '正常采购' }}</small></td><td>{{ record.facts.material_code }}<small>{{ record.facts.material_name }}</small><small>{{ materialCategoryLabels[record.material_category] }}</small></td><td>{{ record.quantity }} {{ record.unit }}</td><td>{{ record.delivery_reference }}</td><td>{{ record.actor_name }}</td><td><details><summary>查看 {{ record.batches.length }} 项实物</summary><p v-for="batch in record.batches" :key="batch.id">{{ batch.quantity }} {{ record.unit }} · {{ batch.location }}<template v-if="record.material_category === 'FABRIC'"> · 缸号 {{ batch.dye_lot || '未填' }}<template v-if="batch.roll_no"> · 卷号 {{ batch.roll_no }}</template></template> · 待检</p><p v-if="record.difference_reason">超收说明：{{ record.difference_reason }}</p><p v-if="record.note">备注：{{ record.note }}</p><p>来源版本 {{ record.source_revision }} · 登记时间 {{ record.occurred_at }}</p></details></td>
      </tr></tbody></table>
      <table v-else><thead><tr><th>{{ mode === 'movements' ? '流水 / 入库单' : '批次 / 入库单' }}</th><th>物料 / 分类</th><th>采购来源 / 供应商</th><th>仓位</th><th>缸号 / 卷号</th><th>{{ mode === 'movements' ? '本次入库数量' : '实物库存数量' }}</th><th>质量</th><th>收货日期</th><th>送货依据 / 登记人</th></tr></thead><tbody><tr v-for="batch in stock" :key="batch.id">
        <td>{{ mode === 'movements' ? batch.movement_id : batch.id }}<small>{{ batch.receipt_id }}</small></td><td>{{ batch.facts.material_code }}<small>{{ batch.facts.material_name }}</small><small>{{ materialCategoryLabels[batch.material_category] }}</small></td><td>{{ batch.facts.order_no }}<small>{{ batch.facts.supplier }}</small></td><td>{{ batch.location }}</td><td><template v-if="batch.material_category === 'FABRIC'">{{ batch.dye_lot || '未填' }}<small v-if="batch.roll_no">{{ batch.roll_no }}</small></template><template v-else>—</template></td><td>{{ batch.quantity }} {{ batch.unit }}</td><td>待检</td><td>{{ batch.receipt_date }}</td><td>{{ batch.delivery_reference }}<small>{{ batch.actor_name }}</small></td>
      </tr></tbody></table>
    </div>
    <p v-if="total === 0 && !busy" class="fabric-message" role="status">{{ search ? '没有匹配的入库记录。' : '尚未登记本系统实际入库，采购历史没有计入库存。' }}</p>
    <footer v-if="total !== undefined" class="warehouse-list-footer"><span>共 {{ total }} 条 · {{ total ? offset + 1 : 0 }}–{{ Math.min(offset + 50, total) }}</span><div><Button variant="outline" :disabled="busy || offset === 0" @click="offset -= 50; load()">上一页</Button><Button variant="outline" :disabled="busy || offset + 50 >= total" @click="offset += 50; load()">下一页</Button></div></footer>
  </div>
</template>
