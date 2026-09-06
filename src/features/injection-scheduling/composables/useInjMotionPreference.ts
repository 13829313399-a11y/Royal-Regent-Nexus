import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

export function useInjMotionPreference() {
  const reduced = ref(true),
    hidden = ref(false);
  let media: MediaQueryList | undefined;
  const update = () => {
    reduced.value = media?.matches ?? true;
    hidden.value = document.hidden;
  };
  onMounted(() => {
    media = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    update();
    media?.addEventListener('change', update);
    document.addEventListener('visibilitychange', update);
  });
  onBeforeUnmount(() => {
    media?.removeEventListener('change', update);
    document.removeEventListener('visibilitychange', update);
  });
  return {
    reduced,
    hidden,
    motionAllowed: computed(() => !reduced.value && !hidden.value),
  };
}
