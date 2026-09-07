<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useDialogFocus } from "@/composables/useDialogFocus";
import { http, getApiErrorMessage } from "@/lib/http";
const props = defineProps<{ id: string }>();
const emit = defineEmits<{ close: [] }>();
const root = ref<HTMLElement | null>(null);
useDialogFocus(() => true, root, { onEscape: () => emit("close") });
const data = ref<{
  events: { id: string; state: string; observed_at: string }[];
  commands: {
    id: string;
    action: string;
    status: string;
    requested_at: string;
    result_message: string;
  }[];
}>();
const error = ref("");
onMounted(async () => {
  try {
    data.value = (
      await http.get(`/three-d-printing/printers/${props.id}/timeline`, {
        params: { factory_id: "huakang-a" },
      })
    ).data;
  } catch (e) {
    error.value = getApiErrorMessage(e);
  }
});
</script>
<template>
  <div
    class="fixed inset-0 z-50 flex justify-end bg-black/30"
    @click.self="$emit('close')"
  >
    <aside
      ref="root"
      role="dialog"
      aria-modal="true"
      aria-label="打印机状态与命令时间线"
      class="h-full w-full max-w-xl overflow-auto bg-white p-6"
      tabindex="-1"
      @keydown.esc="$emit('close')"
    >
      <button
        class="float-right rounded border px-3 py-2"
        autofocus
        @click="$emit('close')"
      >
        关闭
      </button>
      <h2 class="text-xl font-bold">机台详情与时间线</h2>
      <p role="alert">{{ error }}</p>
      <h3 class="mt-8 font-bold">命令结果</h3>
      <ol>
        <li v-for="item in data?.commands" :key="item.id" class="border-b py-3">
          {{ item.requested_at }} · {{ item.action }} · {{ item.status }}
          <p>{{ item.result_message }}</p>
        </li>
      </ol>
      <h3 class="mt-8 font-bold">状态历史</h3>
      <ol>
        <li v-for="item in data?.events" :key="item.id" class="border-b py-2">
          {{ item.observed_at }} · {{ item.state }}
        </li>
      </ol>
    </aside>
  </div>
</template>
