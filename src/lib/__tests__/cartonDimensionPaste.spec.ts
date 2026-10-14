import { expect, it } from 'vitest'
import { normalizeCartonDimensionPaste } from '../cartonDimensionPaste'

it.each([
  ['30\t20\t15\r\n', '30*20*15'],
  ['30\n20\n15', '30*20*15'],
  ['30.5 20.25 15', '30.5*20.25*15'],
  ['30 20', '30*20'],
  ['30 20 0', '30*20*0'],
  [' ３０　２０　１５ ', '30*20*15'],
])('normalizes only a pasted dimension pair/triple: %s', (value, expected) => {
  expect(normalizeCartonDimensionPaste(value)).toBe(expected)
})

it.each(['', '302015', '30*20*15', '30×20×15', '30 x 20 x 15', '30 20 15 cm', '长30 宽20 高15', '30 20 15\n40 30 20', '30 -20 15', 'A33 30 20', '30,5 20 15'])('leaves existing separators, descriptions and ambiguous pastes untouched: %s', value => {
  expect(normalizeCartonDimensionPaste(value)).toBeNull()
})
