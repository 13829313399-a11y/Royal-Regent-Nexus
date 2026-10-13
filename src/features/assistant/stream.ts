/** Streaming UTF-8 decoder; network packets are not SSE events. */
export async function* parseSSE(body: ReadableStream<Uint8Array>) {
  const reader = body.getReader(), decoder = new TextDecoder()
  let buffer = '', event = 'message', data: string[] = []
  try {
    while (true) {
      const chunk = await reader.read()
      buffer += decoder.decode(chunk.value, { stream: !chunk.done })
      let at: number
      while ((at = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, at).replace(/\r$/, '')
        buffer = buffer.slice(at + 1)
        if (!line) {
          if (data.length) yield { event, data: data.join('\n') }
          event = 'message'; data = []
        } else if (line.startsWith('event:')) event = line.slice(6).trimStart()
        else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
      }
      if (buffer.length > 2_000_000) throw new Error('模型响应格式异常。')
      if (chunk.done) {
        if (buffer.trim() || data.length) throw new Error('连接在事件结束前中断。')
        break
      }
    }
  } finally { await reader.cancel().catch(() => undefined); reader.releaseLock() }
}
