// Keep the client filter aligned with ledger.import_preview and normalize_edu_item.
// This only selects candidates; the server still validates the final revision and identity.
function productKey(customerCode: string, value: string) {
  let product = value.trim()
  if (customerCode === 'edu') {
    product = product.replace(/\s+/g, ' ')
    const match = /^(F(?:11|12)-[A-Z]{2}\d{3}-(?:[A-Z]\d{3}|\d{4}))\d{4}$/i.exec(product)
    if (match) product = match[1]!
  }
  return product.toLowerCase()
}
export function sameReconciliationProduct(customerCode: string, existing: string, incoming: string) {
  const existingKey = productKey(customerCode, existing)
  return existingKey !== '' && existingKey === productKey(customerCode, incoming)
}
