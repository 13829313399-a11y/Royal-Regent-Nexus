import { onBeforeUnmount, watch, type Ref } from 'vue'

/** Latest response per operation, fenced by page lifetime and authorization context. */
export function useUvRequestScope(context: Ref<number>) {
  let alive = true, generation = 0
  const channels = new Map<string, number>()
  function invalidate() { generation++; channels.clear() }
  function start(channel: string) {
    const version = (channels.get(channel) ?? 0) + 1, epoch = generation
    channels.set(channel, version)
    return () => alive && epoch === generation && channels.get(channel) === version
  }
  watch(context, invalidate, { flush: 'sync' })
  onBeforeUnmount(() => { alive = false; invalidate() })
  return { start, invalidate, alive: () => alive }
}
