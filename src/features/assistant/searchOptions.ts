import type { Capabilities } from './types'
import type { SearchMode, ThinkingMode } from './v2'
export function searchUnavailable(caps: Capabilities | null, mode: SearchMode, thinking: ThinkingMode, images: boolean) {
  if (mode === 'off') return ''
  const search = caps?.search
  if (!search?.supported_modes.includes(mode)) return search?.status_label || '当前联网模式不可用，可关闭联网后普通提问。'
  if (!search.verified_combinations.some(c => c.input === (images ? 'text_image' : 'text') && c.thinking === thinking)) return '此图片与思考组合尚未验证联网。请保留资料，选择已支持的组合或关闭联网。'
  return ''
}
