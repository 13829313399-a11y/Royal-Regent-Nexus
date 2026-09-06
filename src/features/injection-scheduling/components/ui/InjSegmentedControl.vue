<script setup lang="ts">
import {
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
  type Component,
} from 'vue';
import { useInjMotionPreference } from '../../composables/useInjMotionPreference';
const props = defineProps<{
  modelValue: string;
  options: { value: string; label: string; icon?: Component }[];
  label: string;
  disabled?: boolean;
}>();
const emit = defineEmits<{ 'update:modelValue': [string] }>();
const root = ref<HTMLElement>();
const indicator = ref({
  transform: 'translateX(0px)',
  width: '0px',
  opacity: 0,
});
const { motionAllowed } = useInjMotionPreference();
let observer: ResizeObserver | undefined,
  frame = 0,
  disposed = false;
function measure() {
  const container = root.value,
    selected = container?.querySelector<HTMLElement>('[aria-pressed="true"]');
  if (!container || !selected) return;
  const outer = container.getBoundingClientRect(),
    rect = selected.getBoundingClientRect();
  indicator.value = {
    transform: `translateX(${rect.left - outer.left + container.scrollLeft - container.clientLeft}px)`,
    width: `${rect.width}px`,
    opacity: 1,
  };
}
function queue() {
  if (disposed) return;
  if (frame) cancelAnimationFrame(frame);
  if (!motionAllowed.value) {
    measure();
    return;
  }
  frame = requestAnimationFrame(measure);
}
function keys(event: KeyboardEvent, index: number) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const buttons = root.value?.querySelectorAll<HTMLButtonElement>('button');
  const count = props.options.length;
  const next =
    event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? count - 1
        : (index + (event.key === 'ArrowRight' ? 1 : -1) + count) % count;
  buttons?.[next]?.focus();
}
watch(
  () => [props.modelValue, props.options, motionAllowed.value],
  () => nextTick(queue),
  { deep: true },
);
onMounted(() => {
  if (typeof ResizeObserver !== 'undefined')
    observer = new ResizeObserver(queue);
  if (root.value) {
    observer?.observe(root.value);
    root.value
      .querySelectorAll('button')
      .forEach((el) => observer?.observe(el));
  }
  window.addEventListener('resize', queue);
  document.fonts?.ready.then(queue);
  measure();
});
onBeforeUnmount(() => {
  disposed = true;
  observer?.disconnect();
  if (frame) cancelAnimationFrame(frame);
  window.removeEventListener('resize', queue);
});
</script>
<template>
  <div
    ref="root"
    class="inj-pill-control"
    :class="{ 'inj-no-motion': !motionAllowed }"
    role="group"
    :aria-label="label"
    @scroll="queue"
  >
    <span class="inj-pill-indicator" :style="indicator" aria-hidden="true" />
    <button
      v-for="(option, index) in options"
      :key="option.value"
      type="button"
      :disabled="disabled"
      :aria-pressed="modelValue === option.value"
      @click="emit('update:modelValue', option.value)"
      @keydown="keys($event, index)"
    >
      <component
        :is="option.icon"
        v-if="option.icon"
        aria-hidden="true"
      /><span>{{ option.label }}</span>
    </button>
  </div>
</template>
