<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { injectionApi as api } from '@/api/injectionScheduling';
import { getApiErrorMessage } from '@/lib/http';
import { useInjectionStore } from '@/stores/injectionScheduling';
import { factories, numberText } from './types';
import type { StartReview, StartReviewRow, StartSelection } from './bulkStart';
import { vInjDialog } from './composables/injDialog';
import InjButton from './components/ui/InjButton.vue';

const props = defineProps<{ items: StartSelection[]; canReport: boolean }>();
const emit = defineEmits<{
  close: [];
  remove: [string];
  started: [string[]];
}>();
const store = useInjectionStore();
const factory = store.factory!;
const preview = ref<StartReview | null>(null);
const results = ref<StartReviewRow[] | null>(null);
const loading = ref(false),
  error = ref('');
const rows = computed(() => results.value || preview.value?.items || []);
const eligible = computed(
  () => preview.value?.items.filter((row) => row.can_start) || [],
);
const successful = computed(
  () => results.value?.filter((row) => row.success).length || 0,
);
let generation = 0;
function close() {
  if (!store.busy) emit('close');
}
async function review() {
  if (store.busy || !props.canReport || store.factory !== factory) return;
  const expected = ++generation;
  loading.value = true;
  error.value = '';
  results.value = null;
  preview.value = null;
  if (!props.items.length) {
    loading.value = false;
    return;
  }
  try {
    const data = await api.post<StartReview>('/execution/start-preview', {
      factory_id: factory,
      items: props.items.map(({ machine_id, run_id }) => ({
        machine_id,
        run_id,
      })),
    });
    if (expected === generation && store.factory === factory)
      preview.value = data;
  } catch (e) {
    if (expected === generation)
      error.value = getApiErrorMessage(e) || '核对失败，请重试';
  } finally {
    if (expected === generation) loading.value = false;
  }
}
async function remove(machineId: string) {
  emit('remove', machineId);
  // Parent updates the frozen selection before the next review.
  await Promise.resolve();
  await review();
}
async function submit() {
  if (
    !props.canReport ||
    loading.value ||
    store.busy ||
    results.value ||
    !preview.value ||
    !eligible.value.length ||
    store.factory !== factory
  )
    return;
  error.value = '';
  const expected = generation;
  const reviewedRows = preview.value.items;
  const result = await store.mutate('/execution/bulk-start', {
    expected_revision: preview.value.revision,
    confirm_actual_start: true,
    items: eligible.value.map(({ machine_id, run_id, review_token }) => ({
      machine_id,
      run_id,
      review_token,
    })),
  });
  if (store.factory !== factory || expected !== generation) return;
  store.dirty = true;
  if (!result?.bulk_start) {
    error.value = store.error || '开工结果尚未确认，可重试同一操作或重新核对';
    return;
  }
  const receipt = new Map<string, StartReviewRow>(
    result.results.map((row: StartReviewRow) => [row.machine_id, row]),
  );
  results.value = reviewedRows.map(
    (row) => receipt.get(row.machine_id) || { ...row, success: false },
  );
  emit(
    'started',
    results.value.filter((row) => row.success).map((row) => row.machine_id),
  );
}
watch(() => store.factory, close);
watch(
  () => props.canReport,
  (allowed) => {
    if (!allowed) close();
  },
);
onMounted(() => {
  store.dirty = true;
  void review();
});
onBeforeUnmount(() => {
  generation++;
  if (store.factory === factory) store.dirty = false;
});
</script>
<template>
  <div class="inj-modal-backdrop">
    <section
      class="inj-modal inj-bulk-start-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="inj-bulk-start-title"
      v-inj-dialog="{ close, busy: store.busy }"
    >
      <header>
        <h2 id="inj-bulk-start-title">
          {{ results ? '批量开工结果' : '核对批量开工' }} ·
          {{ factories[factory] }}
        </h2>
        <button
          aria-label="关闭批量开工窗口"
          :disabled="store.busy"
          @click="close"
        >
          ×
        </button>
      </header>
      <p>
        每台机只开工已保存计划中的“下一批”，后续批次继续等待。请核对现场，确认这些批次现在实际开工。
      </p>
      <p v-if="loading" role="status">正在核对设备、实物模具及生产条件…</p>
      <p v-else-if="results" role="status" class="inj-bulk-summary">
        本次已开工 {{ successful }} 台，{{ results.length - successful }}
        台未开工。未开工机台仍保留勾选。
      </p>
      <p v-else-if="preview" role="status">
        已选 {{ rows.length }} 台 · 可开工 {{ eligible.length }} 台 · 待处理
        {{ rows.length - eligible.length }} 台
      </p>
      <p v-if="error" class="inj-error-text" role="alert">{{ error }}</p>
      <div class="inj-bulk-review-table">
        <table>
          <thead>
            <tr>
              <th>机号</th>
              <th>下一批模号 / 单号</th>
              <th>剩余啤数</th>
              <th>核对结果</th>
              <th v-if="!results">选择</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.machine_id">
              <td>{{ row.machine_code || '机台已不可用' }}</td>
              <td>
                <strong>{{ row.mold_code || '—' }}</strong
                ><small>{{ row.order_no || '—' }}</small>
              </td>
              <td>{{ numberText(row.remaining_shots) }}</td>
              <td
                :class="{
                  'inj-error-text': results ? !row.success : !row.can_start,
                }"
              >
                {{
                  results ? row.reason : row.can_start ? '可开工' : row.reason
                }}
              </td>
              <td v-if="!results">
                <button
                  :disabled="store.busy || loading"
                  :aria-label="`移除 ${row.machine_code}`"
                  @click="remove(row.machine_id)"
                >
                  移除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!rows.length && !loading">没有待核对机台，请返回看板勾选。</p>
      </div>
      <footer>
        <InjButton :disabled="store.busy" @click="close">{{
          results ? '完成' : '取消'
        }}</InjButton>
        <InjButton
          v-if="items.length"
          :disabled="store.busy || loading"
          @click="review"
          >{{ results ? '重新核对未开工机台' : '重新核对' }}</InjButton
        >
        <InjButton
          v-if="!results"
          primary
          :pending="store.busy"
          :disabled="!canReport || loading || !eligible.length"
          @click="submit"
          >确认现在开工（{{ eligible.length }} 台）</InjButton
        >
      </footer>
    </section>
  </div>
</template>
<style scoped>
.inj-bulk-start-dialog {
  width: min(940px, calc(100vw - 32px));
  max-height: calc(100dvh - 40px);
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
}
.inj-bulk-start-dialog header,
.inj-bulk-start-dialog footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.inj-bulk-start-dialog h2,
.inj-bulk-start-dialog p {
  margin: 0;
}
.inj-bulk-start-dialog header button {
  font-size: 22px;
}
.inj-bulk-start-dialog footer {
  justify-content: flex-end;
}
.inj-bulk-review-table {
  overflow: auto;
  min-height: 0;
}
.inj-bulk-review-table table {
  width: 100%;
  min-width: 580px;
  border-collapse: collapse;
}
.inj-bulk-review-table th,
.inj-bulk-review-table td {
  padding: 10px;
  text-align: left;
  border-bottom: 1px solid var(--inj-line);
}
.inj-bulk-review-table th {
  position: sticky;
  top: 0;
  background: var(--inj-bg, #f2f7f6);
  z-index: 1;
}
.inj-bulk-review-table small {
  display: block;
  max-width: 300px;
  overflow-wrap: anywhere;
  margin-top: 4px;
}
.inj-bulk-summary {
  color: var(--inj-accent);
  font-weight: 600;
}
@media (max-width: 600px) {
  .inj-bulk-review-table table {
    min-width: 0;
  }
  .inj-bulk-review-table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }
  .inj-bulk-review-table tbody,
  .inj-bulk-review-table tr,
  .inj-bulk-review-table td {
    display: block;
  }
  .inj-bulk-review-table tr {
    padding: 8px 0;
    border-bottom: 1px solid var(--inj-line);
  }
  .inj-bulk-review-table td {
    padding: 4px 0;
    border: 0;
    overflow-wrap: anywhere;
  }
  .inj-bulk-review-table td:first-child {
    font-weight: 700;
  }
  .inj-bulk-review-table td:first-child::before {
    content: '机号：';
  }
  .inj-bulk-review-table td:nth-child(3)::before {
    content: '剩余啤数：';
  }
  .inj-bulk-review-table td:nth-child(4)::before {
    content: '核对结果：';
  }
}
</style>
