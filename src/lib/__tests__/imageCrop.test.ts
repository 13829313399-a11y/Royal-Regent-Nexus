import assert from 'node:assert/strict'

import {
  getContainedImageFrame,
  isUsableCropSelection,
  normalizeCropSelection,
  selectionToImagePixels,
} from '../imageCrop'

const selection = normalizeCropSelection({ x: 0.8, y: 0.7 }, { x: 0.2, y: 0.1 })

assert.deepEqual(selection, {
  x: 0.2,
  y: 0.1,
  width: 0.6000000000000001,
  height: 0.6,
})

assert.equal(isUsableCropSelection(selection), true)
assert.equal(isUsableCropSelection({ x: 0.2, y: 0.2, width: 0.05, height: 0.3 }), false)

assert.deepEqual(getContainedImageFrame(400, 200, 1000, 1000), {
  left: 100,
  top: 0,
  width: 200,
  height: 200,
})

assert.deepEqual(selectionToImagePixels({ x: 0.25, y: 0.1, width: 0.5, height: 0.4 }, 2000, 1000, 0), {
  x: 500,
  y: 100,
  width: 1000,
  height: 400,
})

assert.deepEqual(selectionToImagePixels({ x: 0, y: 0, width: 0.5, height: 0.5 }, 1000, 800, 0.02), {
  x: 0,
  y: 0,
  width: 520,
  height: 416,
})
