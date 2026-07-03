import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/data/moldingSampleWorkflowMock.ts'), 'utf8')
const huakangAStart = source.indexOf('const huakangAItems')
const huakangAEnd = source.indexOf('const huakangBOrder')

assert.notEqual(huakangAStart, -1)
assert.notEqual(huakangAEnd, -1)

const huakangAItemsSource = source.slice(huakangAStart, huakangAEnd)

assert.equal((huakangAItemsSource.match(/createItem\(\{/g) ?? []).length, 14)

for (const requiredOrderCopy of [
  "id: 'BP-62437'",
  "client_name: 'BuzzBee'",
  "order_number: '62437'",
  "doc_number: 'W-G026-00'",
  "product_name: '链条枪'",
  "date: '2026-04-09'",
  '见客样办，枪身不可刮花，颜色要对办，工程订色粉。',
]) {
  assert.match(source, new RegExp(requiredOrderCopy.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
}

for (const requiredItemCopy of [
  "mold_id: 'BBT62450-A-02-2'",
  "mold_name: '手柄饰件'",
  "mold_id: 'BBT62450-B-01'",
  "mold_name: '左右枪身B款'",
  "mold_id: 'BBT62659-04'",
  "mold_name: '左右枪身长装饰件'",
  "color: '深绿色 / PMS 2272C'",
  "color: '暗蓝色 / PMS 2935C'",
  "color: '深蓝色 / PMS 7694C'",
  "pigment_no: '70039'",
  "pigment_no: '70040'",
  "completion_time: '2026-04-13'",
]) {
  assert.match(huakangAItemsSource, new RegExp(requiredItemCopy.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
}

assert.equal((huakangAItemsSource.match(/shoot_qty: 30/g) ?? []).length, 14)
assert.equal((huakangAItemsSource.match(/quantity: '1\/1'/g) ?? []).length, 14)
assert.equal((huakangAItemsSource.match(/machine_type: '待工程确认'/g) ?? []).length, 14)
