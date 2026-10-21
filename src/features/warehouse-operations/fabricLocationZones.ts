export const locationCategoryLabels: Record<string, string> = { FABRIC: '布料', ACCESSORY: '辅料', THREAD: '线' }
export function matchesLocationCategory(location: { category?: string }, category?: string) {
  return category === undefined || (!!category && location.category === category)
}
