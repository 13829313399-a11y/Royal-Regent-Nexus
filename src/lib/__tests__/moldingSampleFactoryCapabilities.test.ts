import assert from 'node:assert/strict'
import {
  getAllowedMoldingSampleProductionFactoryIds,
  getMoldingSampleFactoryCapability,
  getMoldingSampleFactoryLabel,
  getSuggestedMoldingSampleProductionFactoryId,
  resolveMoldingSampleProductionFactoryId,
  validateMoldingSampleProductionAssignment,
} from '../moldingSampleFactoryCapabilities.js'

assert.deepEqual(getAllowedMoldingSampleProductionFactoryIds('huakang-c'), ['huakang-a', 'huakang-b'])
assert.deepEqual(getAllowedMoldingSampleProductionFactoryIds('huakang-d'), ['huakang-a', 'huakang-b'])
assert.equal(getSuggestedMoldingSampleProductionFactoryId('huakang-c'), 'huakang-a')
assert.equal(getSuggestedMoldingSampleProductionFactoryId('huakang-d'), 'huakang-b')

for (const factoryId of ['huakang-a', 'huakang-b', 'huadeng', 'huaxing'] as const) {
  assert.equal(getMoldingSampleFactoryCapability(factoryId)?.dispatchMode, 'self-only')
  assert.deepEqual(getAllowedMoldingSampleProductionFactoryIds(factoryId), [factoryId])
  assert.equal(getSuggestedMoldingSampleProductionFactoryId(factoryId), factoryId)
}

assert.equal(getMoldingSampleFactoryLabel('huakang-c'), '华康C')
assert.equal(getMoldingSampleFactoryLabel(null), '待派厂')
assert.equal(getMoldingSampleFactoryLabel('future-factory'), 'future-factory')

assert.deepEqual(validateMoldingSampleProductionAssignment('huakang-c', 'huakang-a'), {
  valid: true,
  productionFactoryId: 'huakang-a',
  error: '',
})
assert.deepEqual(validateMoldingSampleProductionAssignment('huakang-d', 'huakang-b'), {
  valid: true,
  productionFactoryId: 'huakang-b',
  error: '',
})
assert.match(
  validateMoldingSampleProductionAssignment('huakang-c', 'huadeng').error,
  /只能由华康A、华康B承接生产/,
)
assert.match(
  validateMoldingSampleProductionAssignment('huaxing', 'huakang-a').error,
  /只能由华兴承接生产/,
)
assert.match(
  validateMoldingSampleProductionAssignment('huakang-d', null).error,
  /必须选择华康A或华康B/,
)
assert.deepEqual(validateMoldingSampleProductionAssignment('huaxing', null), {
  valid: true,
  productionFactoryId: 'huaxing',
  error: '',
})

assert.equal(resolveMoldingSampleProductionFactoryId({
  factory_id: 'huaxing',
  production_factory_id: null,
}), 'huaxing')
assert.equal(resolveMoldingSampleProductionFactoryId({
  factory_id: 'huakang-c',
  production_factory_id: 'huakang-b',
}), 'huakang-b')
assert.equal(resolveMoldingSampleProductionFactoryId({
  factory_id: 'huakang-c',
  production_factory_id: null,
}), null)
assert.equal(resolveMoldingSampleProductionFactoryId({
  factory_id: 'huakang-c',
  production_factory_id: null,
  send_to: '发至湖南',
}), null)
assert.equal(resolveMoldingSampleProductionFactoryId({
  factory_id: 'huakang-d',
  production_factory_id: null,
  workshop: '模厂',
}), null)
