import type { UvPage, UvResponse, UvScope } from '../contracts'

/** Read every server page for calculations and selector options.  Page size is
 * capped at 200 by the API, so callers must never aggregate a first page only. */
export async function readAllPages<T>(
  reader: (scope: UvScope, signal?: AbortSignal) => Promise<UvResponse<UvPage<T>>>,
  scope: UvScope,
  signal?: AbortSignal,
): Promise<UvResponse<UvPage<T>>> {
  const pageSize = 200
  const first = await reader({ ...scope, page: 1, page_size: pageSize }, signal)
  const items = [...first.data.items]
  const pages = Math.ceil(first.data.total / pageSize)
  for (let page = 2; page <= pages; page += 1) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    const response = await reader({ ...scope, page, page_size: pageSize }, signal)
    items.push(...response.data.items)
  }
  return { ...first, data: { items, total: first.data.total, page: 1, page_size: pageSize } }
}
