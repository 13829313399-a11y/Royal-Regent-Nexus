<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useVirtualizer } from '@tanstack/vue-virtual'
import { Button } from '@/components/ui/button'
import {
  documentTools,
  type Anchor,
  type Job,
  type Result,
  type Table,
} from '@/api/documentTools'
import { getApiErrorMessage } from '@/lib/http'
const props = defineProps<{ job: Job; selectedTarget?: string; readonly?: boolean }>()
const emit = defineEmits<{
  locate: [anchor: Anchor, target: string]
  revised: [jobId: string]
}>()
const result = ref<Result>(),
  error = ref(''),
  loading = ref(false),
  tableId = ref(''),
  offset = ref(0),
  drafts = ref<Record<string, string>>({}),
  reason = ref('人工对照原文修正'),
  saving = ref(false)
const tableCatalog = ref<Table[]>([])
const scroller = ref<HTMLElement>()
const table = computed(
  () =>
    result.value?.tables.find((item) => item.id === tableId.value) ??
    result.value?.tables[0],
)
const corrections = computed(() =>
  Object.entries(drafts.value).map(([target_id, new_value]) => ({
    target_id,
    new_value,
    reason: reason.value,
  })),
)
const virtualEnabled = typeof ResizeObserver !== 'undefined'
const virtualizer = useVirtualizer(
  computed(() => ({
    count: table.value?.cells.length ?? 0,
    getScrollElement: () => scroller.value ?? null,
    estimateSize: () => 68,
    overscan: 8,
    enabled: virtualEnabled,
    initialRect: { width: 600, height: 400 },
  })),
)
const renderedCells = computed(() =>
  virtualEnabled
    ? virtualizer.value
        .getVirtualItems()
        .map((item) => ({
          cell: table.value!.cells[item.index]!,
          index: item.index,
        }))
    : (table.value?.cells ?? []).map((cell, index) => ({ cell, index })),
)
const paddingTop = computed(() =>
  virtualEnabled ? (virtualizer.value.getVirtualItems()[0]?.start ?? 0) : 0,
)
const paddingBottom = computed(() =>
  virtualEnabled
    ? Math.max(
        0,
        virtualizer.value.getTotalSize() -
          (virtualizer.value.getVirtualItems().at(-1)?.end ?? 0),
      )
    : 0,
)
function measureRow(element: Element | null) {
  if (element && virtualEnabled) virtualizer.value.measureElement(element)
}
async function scrollTarget() {
  await nextTick()
  const index =
    table.value?.cells.findIndex((cell) => cell.id === props.selectedTarget) ??
    -1
  if (index >= 0 && virtualEnabled) {
    virtualizer.value.scrollToIndex(index, { align: 'center' })
    await nextTick()
  }
  scroller.value
    ?.querySelector<HTMLElement>('.selected')
    ?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
}
let generation = 0
async function load(targetId?: string) {
  const ticket = ++generation
  loading.value = true
  error.value = ''
  try {
    let response = await documentTools.result(
      props.job.id,
      targetId ? undefined : tableId.value || undefined,
      offset.value,
      targetId,
    )
    if (targetId) {
      offset.value = response.offset
      tableId.value =
        response.tables.find((item) =>
          item.cells.some((cell) => cell.id === targetId),
        )?.id ?? tableId.value
    } else if (!tableId.value && response.tables.length) {
      tableCatalog.value = response.tables
      tableId.value = response.tables[0]!.id
      response = await documentTools.result(
        props.job.id,
        tableId.value,
        offset.value,
      )
    }
    if (ticket === generation) {
      result.value = response
      await scrollTarget()
    }
  } catch (problem) {
    if (ticket === generation) error.value = getApiErrorMessage(problem)
  } finally {
    if (ticket === generation) loading.value = false
  }
}
async function save() {
  saving.value = true
  error.value = ''
  try {
    const next = await documentTools.revise(props.job.id, {
      base_revision: props.job.revision,
      corrections: corrections.value,
    })
    drafts.value = {}
    emit('revised', next.job_id)
  } catch (problem) {
    error.value = getApiErrorMessage(problem)
  } finally {
    saving.value = false
  }
}
function chooseTable() {
  offset.value = 0
  void load()
}
function changePage(next: number) {
  offset.value = Math.max(0, next)
  void load()
}
watch(
  () => props.job.id,
  () => {
    tableId.value = ''
    offset.value = 0
    drafts.value = {}
    void load()
  },
  { immediate: true },
)
watch(
  () => props.selectedTarget,
  (target) => {
    if (!target) return
    if (
      table.value?.cells.some((cell) => cell.id === target) ||
      result.value?.blocks.some((block) => block.id === target)
    )
      void scrollTarget()
    else void load(target)
  },
)
onBeforeUnmount(() => {
  generation++
})
</script>

<template>
  <section class="dt-review" aria-label="结构化结果核对">
    <div class="dt-review-toolbar">
      <strong>结果核对 · 版本 {{ job.revision }}</strong
      ><label v-if="tableCatalog.length"
        >表格<select v-model="tableId" @change="chooseTable">
          <option v-for="item in tableCatalog" :key="item.id" :value="item.id">
            {{ item.title || item.id }} · {{ item.row_count }} 行 ×
            {{ item.column_count }} 列
          </option>
        </select></label
      >
    </div>
    <p v-if="error" role="alert">
      {{ error }}
      <Button variant="outline" size="sm" @click="load()">重试</Button>
    </p>
    <p v-if="loading" role="status">正在读取结果…</p>
    <div
      v-if="result"
      ref="scroller"
      class="dt-review-content"
      :aria-busy="loading"
    >
      <p class="dt-review-help">
        点击来源定位原文。此网格按单元格核对，合并关系单独标注；版式请查看 PDF
        校样。
      </p>
      <table v-if="table?.cells.length">
        <thead>
          <tr>
            <th>位置 / 来源</th>
            <th>原始识别</th>
            <th>结果（可编辑）</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="paddingTop" aria-hidden="true">
            <td
              colspan="3"
              :style="{ height: `${paddingTop}px`, padding: 0 }"
            />
          </tr>
          <tr
            v-for="{ cell, index } in renderedCells"
            :key="cell.id"
            :ref="(element) => measureRow(element as Element | null)"
            :data-index="index"
            :class="{
              selected: selectedTarget === cell.id,
              ambiguous: !['resolved', 'manually_confirmed'].includes(cell.resolution),
            }"
          >
            <td>
              <button
                type="button"
                @click="emit('locate', cell.source, cell.id)"
              >
                行 {{ cell.row + 1 }} · 列 {{ cell.column + 1
                }}<small v-if="cell.rowspan > 1 || cell.colspan > 1"
                  >合并 {{ cell.rowspan }} × {{ cell.colspan }}</small
                ><small
                  >{{ cell.source.sheet }} {{ cell.source.cell
                  }}{{
                    cell.source.page_index != null
                      ? `第 ${cell.source.page_index + 1} 页`
                      : ''
                  }}</small
                >
              </button>
            </td>
            <td class="dt-original">{{ cell.raw_text || '（空白）' }}</td>
            <td>
              <input
                :readonly="readonly"
                :aria-label="`行 ${cell.row + 1} 列 ${cell.column + 1} 结果`"
                :value="drafts[cell.id] ?? cell.display_text"
                @focus="emit('locate', cell.source, cell.id)"
                @input="
                  drafts[cell.id] = ($event.target as HTMLInputElement).value
                "
              /><small v-if="cell.resolution === 'manually_confirmed'">已人工确认</small><small v-else-if="cell.resolution !== 'resolved'"
                >需要核对原文</small
              >
            </td>
          </tr>
          <tr v-if="paddingBottom" aria-hidden="true">
            <td
              colspan="3"
              :style="{ height: `${paddingBottom}px`, padding: 0 }"
            />
          </tr>
        </tbody>
      </table>
      <div v-if="table" class="dt-review-pagination">
        <Button
          variant="outline"
          size="sm"
          :disabled="offset === 0 || loading"
          @click="changePage(offset - 200)"
          >上一段</Button
        ><span
          >{{ offset + 1 }}–{{ offset + (table.cells.length || 0) }} /
          {{ result.total_cells }} 单元格</span
        ><Button
          variant="outline"
          size="sm"
          :disabled="offset + 200 >= result.total_cells || loading"
          @click="changePage(offset + 200)"
          >下一段</Button
        >
      </div>
      <div
        v-if="!table && (result.total_blocks ?? 0) > 200"
        class="dt-review-pagination"
      >
        <Button
          variant="outline"
          size="sm"
          :disabled="offset === 0 || loading"
          @click="changePage(offset - 200)"
          >上一段</Button
        ><span
          >区块 {{ offset + 1 }}–{{ offset + result.blocks.length }} /
          {{ result.total_blocks }}</span
        ><Button
          variant="outline"
          size="sm"
          :disabled="offset + 200 >= (result.total_blocks ?? 0) || loading"
          @click="changePage(offset + 200)"
          >下一段</Button
        >
      </div>
      <div
        v-for="block in result.blocks.filter(
          (item) => item.kind !== 'table' && item.text,
        )"
        :key="block.id"
        class="dt-block"
        :class="{ selected: selectedTarget === block.id }"
      >
        <button type="button" @click="emit('locate', block.source, block.id)">
          {{
            block.source.page_index != null
              ? `第 ${block.source.page_index + 1} 页`
              : '原文区块'
          }}
          · 查看来源</button
        ><p v-if="block.original_text" class="dt-original">原文：{{ block.original_text }}</p><textarea
          :readonly="readonly"
          :aria-label="`区块 ${block.id} 结果`"
          :value="drafts[block.id] ?? block.text"
          rows="3"
          @focus="emit('locate', block.source, block.id)"
          @input="
            drafts[block.id] = ($event.target as HTMLTextAreaElement).value
          "
        />
      </div>
      <p v-if="!table?.cells.length && !result.blocks.length">
        没有可编辑的结构化结果。请查看输出文件与处理报告。
      </p>
    </div>
    <div v-if="corrections.length" class="dt-review-save">
      <label>修正说明<input v-model="reason" aria-label="修正说明" /></label
      ><Button :disabled="saving || !reason.trim()" size="sm" @click="save">{{
        saving ? '正在保存…' : `保存 ${corrections.length} 项修正并生成新版`
      }}</Button
      ><small>原文件和上一个版本继续保留。</small>
    </div>
  </section>
</template>

<style scoped>
.dt-review {
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--card);
  height: 100%;
  font-size: 13px;
}
.dt-review-toolbar {
  padding: 12px;
  display: grid;
  gap: 10px;
  border-bottom: 1px solid var(--border);
}
.dt-review-toolbar label {
  display: flex;
  gap: 8px;
  align-items: center;
}
.dt-review-toolbar select {
  min-width: 0;
  flex: 1;
  padding: 5px;
}
.dt-review-content {
  overflow: auto;
  flex: 1;
  min-height: 250px;
}
.dt-review-help {
  padding: 10px 12px;
  color: var(--muted-foreground);
  font-size: 12px;
  line-height: 1.6;
}
.dt-review table {
  border-collapse: collapse;
  width: 100%;
  min-width: 460px;
}
.dt-review th {
  position: sticky;
  top: 0;
  background: var(--muted);
  text-align: left;
  font-size: 12px;
  padding: 9px;
}
.dt-review td {
  border-bottom: 1px solid var(--border);
  padding: 7px;
  max-width: 220px;
  vertical-align: top;
}
.dt-review td button {
  text-align: left;
  color: var(--primary);
  min-width: 90px;
  line-height: 1.6;
}
.dt-review small {
  display: block;
  font-size: 11px;
  color: var(--muted-foreground);
}
.dt-review input,
.dt-review textarea {
  width: 100%;
  border: 1px solid var(--input);
  border-radius: 6px;
  padding: 7px;
  background: var(--card);
  font-size: 13px;
}
.dt-review input {
  min-width: 140px;
}
.dt-review .selected {
  background: var(--accent);
}
.dt-review .ambiguous td:first-child {
  border-left: 3px solid #b45309;
}
.dt-review .dt-original {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.dt-review-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 5px;
  padding: 10px;
  font-size: 11px;
}
.dt-block {
  padding: 12px;
  border-top: 1px solid var(--border);
}
.dt-block button {
  margin-bottom: 6px;
  color: var(--primary);
  font-size: 12px;
}
.dt-review-save {
  display: grid;
  gap: 7px;
  padding: 12px;
  border-top: 1px solid var(--border);
  background: var(--accent);
}
.dt-review [role='alert'] {
  color: var(--destructive);
  padding: 12px;
}
input:focus-visible,
textarea:focus-visible,
button:focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 1px;
}
</style>
