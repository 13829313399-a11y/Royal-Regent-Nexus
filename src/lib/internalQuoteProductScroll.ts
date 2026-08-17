let pendingProductScrollTop: number | null = null

export function rememberInternalQuoteProductScroll(scrollTop: number) {
  pendingProductScrollTop = Number.isFinite(scrollTop) && scrollTop > 0 ? scrollTop : 0
}

export function consumeInternalQuoteProductScroll() {
  const scrollTop = pendingProductScrollTop
  pendingProductScrollTop = null
  return scrollTop
}
