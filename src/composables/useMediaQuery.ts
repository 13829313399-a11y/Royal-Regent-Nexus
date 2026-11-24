import { onScopeDispose, ref } from 'vue'

export function useMediaQuery(query: string) {
  const media = window.matchMedia?.(query)
  const matches = ref(media?.matches ?? false)
  if (media) {
    const update = (event: MediaQueryListEvent) => { matches.value = event.matches }
    media.addEventListener('change', update)
    onScopeDispose(() => media.removeEventListener('change', update))
  }
  return matches
}
