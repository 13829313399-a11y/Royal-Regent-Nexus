import { existsSync, readFileSync } from 'node:fs'
import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import { describe, expect, it } from 'vitest'
import {
  buildDickyCustomerQuoteFileName,
  convertDickyInternalQuote,
  createDickyCustomerQuoteWorkbook,
} from '@/lib/customerPriceConverters/dicky'
import {
  createXlsxWorkbook,
  parseXlsxWorkbook,
  type XlsxCellInput,
} from '@/lib/customerPriceConverters/xlsxLite'

const dickyTemplatePath = 'public/templates/dicky-customer-quote-template.bin'

function asArrayBuffer(bytes: Uint8Array) {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

function createMinimalDickyWorkbook() {
  const rows: XlsxCellInput[][] = Array.from({ length: 88 }, () => [])

  rows[0][0] = '华登制品 (香港) 有限公司'
  rows[1][0] = 'ROYAL REGENT PRODUCTS (H.K.) LIMITED'
  rows[5][0] = 'ESTIMATAE QUOTATION (估價)'
  rows[6][0] = 'Client(客  戶): '
  rows[6][2] = 'Simba Dickie toys'
  rows[6][9] = 'Date(日期)： '
  rows[6][10] = 46157
  rows[7][0] = 'Attn:'
  rows[7][2] = 'Sam'
  rows[8][0] = 'From:'
  rows[8][2] = 'Ben/ Dicky'
  rows[10][0] = 'NO.'
  rows[10][1] = 'ITEM'
  rows[10][7] = "40'HK /YT FCL"
  rows[11][0] = 1
  rows[11][1] = '20 307 3001\n史迪仔\n（包含2xAALR6电池）'
  rows[11][2] = '0/12'
  rows[11][3] = 0.047
  rows[11][4] = '24*11*12cm'
  rows[11][5] = '49.8*35.2*27cm'
  rows[11][6] = '5K-10K'
  rows[11][7] = { value: 12.34, formula: "'Stitch史迪仔'!D52" }
  rows[11][8] = { value: 11.22, formula: "'Stitch史迪仔'!E52" }
  rows[11][9] = { value: 10.11, formula: "'Stitch史迪仔'!F52" }
  rows[12][0] = 2
  rows[12][1] = '20 307 3000\n米妮\n（不包含2xAA-LR6电池）'
  rows[12][7] = 9.88
  rows[20][0] = 'Remark（备注）：'
  rows[21][0] = 1
  rows[21][1] = '看图估价，如有更改，则需更新报价。'
  rows[24][0] = 4
  rows[24][1] = '产品可通过RoHS,Non Phthalates(6P标准),Cadmium,ASTM,EN71,EN62115,FCC，EMC等测试。'
  rows[27][1] = '料型'
  rows[27][2] = '料价'
  rows[28][1] = 'PP'
  rows[28][2] = 5.8
  rows[30][1] = '注*若人民币的汇率升幅超过2%，工人工资加幅和原材料升幅超过5%，本公司將會保留加价的权利.'
  rows[40][0] = 'Quotation (报价) '
  rows[41][0] = 'Client(客  戶): '
  rows[36][0] = { value: 'summary style sentinel', style: 13 }
  rows[41][2] = 'Dickie'
  rows[41][9] = 'Date(日期)︰ '
  rows[41][10] = 46108
  rows[42][0] = 'Attn:'
  rows[42][2] = 'Sam'
  rows[43][0] = 'From:'
  rows[43][2] = 'Ben/ Dicky'
  rows[45][0] = 'Project Name ( 產品名稱)︰ '
  rows[46][1] = 'Mold # \r\n模具編號 '
  rows[46][2] = 'Parts (膠件) '
  rows[47][0] = '20 307 3001\n史迪仔'
  rows[47][1] = 'M01'
  rows[47][2] = '车灯'
  rows[47][4] = 'ABS'
  rows[47][9] = { value: 1000, formula: '出客模费!J4' }
  rows[85][1] = 'TOTAL:HK$'
  rows[85][9] = { value: 1000, formula: 'SUM(J48:J85)' }
  rows[86][1] = 'First shot time ( 试模期 )：'
  rows[86][9] = '45 Working Days'
  rows[87][1] = 'Finish time(交模期)：'
  rows[87][9] = '75 Working Days'

  return asArrayBuffer(createXlsxWorkbook([{ name: '总表', rows }]))
}

function createMinimalDickyTemplateWorkbook() {
  const rows: XlsxCellInput[][] = Array.from({ length: 88 }, () => [])

  rows[0][0] = { value: 'template visual sentinel', style: 13 }
  rows[40][0] = 'Quotation template'
  rows[46][1] = 'Mold #'
  rows[47][1] = 'M01'
  rows[85][1] = 'TOTAL:HK$'
  rows[86][1] = 'First shot time'
  rows[87][1] = 'Finish time'

  return createXlsxWorkbook([{ name: 'Quotation', rows }])
}

function createBabySitterDickyWorkbook(
  firstRemark = '按客人提供的图片估价，预计胶件重量218g,搪胶重量预计是69g,如有更改，则需更新报价。',
) {
  const rows: XlsxCellInput[][] = Array.from({ length: 27 }, () => [])

  rows[0][0] = '华登制品 (亞洲) 有限公司'
  rows[5][0] = 'ESTIMATAE QUOTATION (估價)'
  rows[6][0] = 'Client(客  戶): '
  rows[6][2] = 'Dickie'
  rows[6][10] = 46203
  rows[10][0] = 'NO.'
  rows[10][1] = 'ITEM'
  rows[11][0] = 1
  rows[11][1] = 'Stuffed Body'
  rows[11][7] = 69.5
  rows[15][0] = 'Remark（备注）：'
  rows[16][0] = 1
  rows[16][1] = { value: firstRemark, style: 4 }
  rows[17][0] = 2
  rows[17][1] = { value: '公仔头，手脚是搪胶，其他配件及公仔大身是塑胶件.', style: 4 }
  rows[18][0] = 3
  rows[18][1] = { value: '产品可通过RoHS,Non Phthalates(6P标准),Cadmium,ASTM,EN71,EN62115,FCC，EMC等测试。', style: 4 }
  rows[19][0] = 4
  rows[19][1] = { value: '报价未含吊柜费，入仓费。', style: 3 }
  rows[20][0] = 5
  rows[20][1] = '按现如下料价报价(HK$/LB)：'
  rows[21][1] = '料型'
  rows[21][2] = '料价'
  rows[21][4] = '料型'
  rows[21][5] = '料价'
  rows[22][1] = 'PP'
  rows[22][2] = 4.8
  rows[22][4] = 'C-ABS'
  rows[22][5] = 8.5
  rows[23][1] = 'ABS'
  rows[23][2] = 5.8
  rows[23][4] = 'HIPS'
  rows[23][5] = 5.1
  rows[24][1] = '注*若人民币的汇率升幅超过2%，工人工资加幅和原材料升幅超过5%，本公司將會保留加价的权利.'
  rows[25][0] = 6
  rows[25][1] = '客戶负责来板的法律责任，包括知识产权。'
  rows[26][0] = 7
  rows[26][1] = '除非产品价格全数清还，本公司仍拥有产品拥有权。'

  return asArrayBuffer(createXlsxWorkbook([{ name: '总表', rows }]))
}

const disneyCableMoldParts: Array<[string, string, string, string]> = [
  ['M01', '后车胎*2/前小轮', 'Rear Tires * 2 / Front Small Wheels', '米妮/史迪仔/胡迪/雪人\n(共用模具）'],
  ['M02', '前车胎*2', 'Front Tires * 2', '米妮/史迪仔/胡迪/雪人\n(共用模具）'],
  ['M03', '车铃', 'Car Bell', '米妮/史迪仔/胡迪/雪人\n(共用模具）'],
  ['M04', '齿轮', 'Gear', '米妮/史迪仔/胡迪/雪人\n(共用模具）'],
  ['M05', '遥控器面壳/底壳/电池盖/包装扣*2/螺母压件', 'Remote Control Front Shell / Bottom Shell / Battery Cover / Packing Buckle * 2 / Nut Retainer', '米妮/史迪仔/胡迪/雪人\n(共用模具）'],
  ['M06', '前进按制，后退按制', 'Forward Button, Reverse Button', '米妮/史迪仔/胡迪/雪人\n(共用模具）'],
  ['M07', '牙箱盖、前小轮压盖', 'Gearbox Cover / Front Small Wheel Cap', '米妮/史迪仔/胡迪\n(共用模具）'],
  ['M08', '车面', 'Car Body', '4边行位'],
  ['M09', '车底/座椅', 'Car Bottom / Seat', ''],
  ['M10', '3000米妮车灯/3001史迪仔车灯', '3000 Minnie Car Light / 3001 Stitch Car Light', '转水口'],
  ['M11', '3000米妮前玻璃/3005胡迪玻璃', '3000 Minnie Front Windshield / 3005 Woody Windshield', '转水口'],
  ['M12', '米妮公仔头/史迪仔公仔头', 'Minnie Doll Head / Stitch Doll Head', '转水口'],
  ['M13', '米妮公仔身/蝴蝶结/左右手/遥控器蝴蝶结', 'Minnie Doll Body / Bow / Left Hand / Right Hand / Remote Control Bow', '米妮'],
  ['M14', '车面', 'Car Body', '史迪仔'],
  ['M15', '车底/座椅', 'Car Bottom / Seat', '行位*1'],
  ['M16', '史迪仔耳朵/手/遥控器耳朵', 'Stitch Ears / Hands / Remote Control Ears', '史迪仔'],
  ['M17', '左右车身/车底', 'Left and Right Car Bodies / Car Bottom', ''],
  ['M18', '车面', 'Car Body', ''],
  ['M19', '座椅', 'Seat', ''],
  ['M20', '3002雪宝车灯/3005胡迪车灯', '3002 Olaf Car Light / 3005 Woody Car Light', '转水口'],
  ['M21', '雪宝公仔前身后身/胡迪公仔身体前壳，身体前壳后壳', 'Olaf Doll Front and Rear Body / Woody Doll Body Front Shell / Rear Shell', '转水口'],
  ['M22', '雪宝头发/手/鼻子/遥控器配件', 'Olaf Hair / Hands / Nose / Remote Control Accessories', ''],
  ['M23', '车身', 'Car Body', '胡迪'],
  ['M24', '尾翼', 'Rear Wing', ''],
  ['M25', '车底/座椅', 'Car Bottom / Seat', ''],
  ['M26', '帽子/手/天线', 'Hat / Hands / Antenna', '转水口/喷油'],
]

function createDisneyCableMoldPartsWorkbook() {
  const rows: XlsxCellInput[][] = Array.from({ length: 76 }, () => [])

  rows[40][0] = 'Quotation (报价) '
  rows[46][1] = 'Mold #'
  rows[46][2] = 'Parts'

  disneyCableMoldParts.forEach(([moldNo, part, _translation, remark], index) => {
    const row = rows[47 + index]
    row[0] = '20 307 3001\n史迪仔'
    row[1] = moldNo
    row[2] = part
    row[10] = remark
  })

  rows[73][1] = 'Finish time(交模期)：'
  rows[73][9] = '75 Working Days'

  return asArrayBuffer(createXlsxWorkbook([{ name: '总表', rows }]))
}

function createFormulaLinkedDickyWorkbook() {
  const summaryRows: XlsxCellInput[][] = Array.from({ length: 88 }, () => [])
  const moldFeeRows: XlsxCellInput[][] = Array.from({ length: 8 }, () => [])
  const factoryRows: XlsxCellInput[][] = Array.from({ length: 12 }, () => [])

  summaryRows[6][2] = 'Simba Dickie toys'
  summaryRows[6][10] = 46157
  summaryRows[11][1] = '20 307 3001\n史迪仔\n（包含2xAALR6电池）'
  summaryRows[11][7] = 25.3
  summaryRows[20][0] = 'Remark（备注）：'
  summaryRows[24][0] = 4
  summaryRows[24][1] = '产品可通过RoHS,Non Phthalates(6P标准),Cadmium,ASTM,EN71,EN62115,FCC，EMC等测试。'
  summaryRows[40][0] = 'Quotation (报价) '
  summaryRows[46][1] = 'Mold #'
  summaryRows[46][2] = 'Parts'
  summaryRows[47][0] = '20 307 3001\n史迪仔'
  summaryRows[47][1] = 'M01'
  summaryRows[47][2] = { value: '#NAME?', formula: "'出客模费'!C4" }
  summaryRows[47][10] = { formula: "'出客模费'!L7" }
  summaryRows[48][0] = '20 307 3001\n史迪仔'
  summaryRows[48][1] = 'M02'
  summaryRows[48][2] = { value: '#NAME?', formula: "'出客模费'!C5" }
  summaryRows[85][1] = 'TOTAL:HK$'
  summaryRows[85][9] = { value: 1000, formula: 'SUM(J48:J85)' }
  summaryRows[86][1] = 'First shot time ( 试模期 )：'
  summaryRows[87][1] = 'Finish time(交模期)：'

  moldFeeRows[3][2] = { formula: "'模厂'!C11" }
  moldFeeRows[4][2] = { formula: "'模厂'!C12" }
  moldFeeRows[6][11] = '米妮/史迪仔/胡迪/雪宝\n(共用模具）'
  factoryRows[10][2] = '车灯'
  factoryRows[11][2] = '牙箱盖、齿轮盖，前小轮压盖，配件'

  return asArrayBuffer(createXlsxWorkbook([
    { name: '总表', rows: summaryRows },
    { name: '出客模费', rows: moldFeeRows },
    { name: '模厂', rows: factoryRows },
  ]))
}

function readXmlAttr(attrs: string, name: string) {
  return attrs.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1] ?? ''
}

function normalizeWorksheetTarget(target: string) {
  const normalized = target.replace(/\\/g, '/').replace(/^\/+/, '')
  return normalized.startsWith('xl/') ? normalized : `xl/${normalized}`
}

function findSheetPath(zip: Record<string, Uint8Array>, sheetName: string) {
  const workbookXml = strFromU8(zip['xl/workbook.xml'])
  const relationsXml = strFromU8(zip['xl/_rels/workbook.xml.rels'])
  const relationMap = new Map<string, string>()

  for (const match of relationsXml.matchAll(/<Relationship\b([^>]*)\/>/g)) {
    relationMap.set(readXmlAttr(match[1], 'Id'), readXmlAttr(match[1], 'Target'))
  }

  for (const match of workbookXml.matchAll(/<sheet\b([^>]*)\/>/g)) {
    const attrs = match[1]
    if (readXmlAttr(attrs, 'name') === sheetName) {
      return normalizeWorksheetTarget(relationMap.get(readXmlAttr(attrs, 'r:id')) ?? '')
    }
  }

  return ''
}

function readCellStyle(zip: Record<string, Uint8Array>, sheetPath: string, ref: string) {
  const sheetXml = strFromU8(zip[sheetPath])
  const match = sheetXml.match(new RegExp(`<c\\b[^>]*\\br="${ref}"[^>]*`))
  return match?.[0].match(/\bs="([^"]+)"/)?.[1] ?? ''
}

function readCellFormula(zip: Record<string, Uint8Array>, sheetPath: string, ref: string) {
  const sheetXml = strFromU8(zip[sheetPath])
  const match = sheetXml.match(new RegExp(`<c\\b[^>]*\\br="${ref}"[^>]*>([\\s\\S]*?)<\\/c>`))
  return match?.[1].match(/<f(?:\s[^>]*)?>([\s\S]*?)<\/f>/)?.[1] ?? ''
}

function readCellXf(zip: Record<string, Uint8Array>, styleId: string | number) {
  const stylesXml = zip['xl/styles.xml'] ? strFromU8(zip['xl/styles.xml']) : ''
  const cellXfsBody = stylesXml.match(/<cellXfs\b[^>]*>([\s\S]*?)<\/cellXfs>/)?.[1] ?? ''
  const xfs = Array.from(cellXfsBody.matchAll(/<xf\b[^>]*(?:\/>|>[\s\S]*?<\/xf>)/g)).map((match) => match[0])
  return xfs[Number(styleId)] ?? ''
}

function replaceCellXf(stylesXml: string, styleId: string | number, replacer: (xf: string) => string) {
  return stylesXml.replace(/(<cellXfs\b[^>]*>)([\s\S]*?)(<\/cellXfs>)/, (_full, start: string, body: string, end: string) => {
    let index = -1
    const updatedBody = body.replace(/<xf\b[^>]*(?:\/>|>[\s\S]*?<\/xf>)/g, (xf) => {
      index += 1
      return index === Number(styleId) ? replacer(xf) : xf
    })

    return `${start}${updatedBody}${end}`
  })
}

function findSelfReferencingFormulaRefs(zip: Record<string, Uint8Array>, sheetPath: string) {
  const sheetXml = strFromU8(zip[sheetPath])
  const refs: string[] = []

  for (const match of sheetXml.matchAll(/<c\b([^>]*)>([\s\S]*?)<\/c>/g)) {
    const ref = readXmlAttr(match[1], 'r')
    const formula = match[2].match(/<f(?:\s[^>]*)?>([\s\S]*?)<\/f>/)?.[1] ?? ''
    if (!ref || !formula || formula.includes('!')) {
      continue
    }

    const parsedRef = ref.match(/^([A-Z]+)(\d+)$/)
    if (!parsedRef) {
      continue
    }

    const [, columnName, rowNumber] = parsedRef
    const tokenPattern = /(?:^|[^A-Z])\$?([A-Z]{1,3})\$?(\d+)(?![A-Z0-9])/g
    for (const tokenMatch of formula.matchAll(tokenPattern)) {
      if (tokenMatch[1] === columnName && tokenMatch[2] === rowNumber) {
        refs.push(ref)
      }
    }
  }

  return refs
}

describe('Dickie customer price converter', () => {
  it('translates every remark in a sample-based quotation', () => {
    const result = convertDickyInternalQuote(
      createBabySitterDickyWorkbook('按客人提供的样办报价，如有更改，则需重新报价。'),
      'Estimate Quotation of the Construction Vehicles.xlsx',
    )
    const output = createDickyCustomerQuoteWorkbook(result)
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))
    const quote = parsed.sheets.find((sheet) => sheet.name === 'Quotation')
    const remarkText = Array.from({ length: 11 }, (_, index) => quote?.rows[16 + index]?.[1] ?? '')

    expect(quote?.rows[16][1]).toBe('This quotation is based on the sample provided by the customer. The final price will be confirmed by the approved sample. Any changes will require a revised quotation.')
    expect(remarkText.join(' ')).not.toMatch(/[\u4E00-\u9FFF]/)
  })

  it('translates a short Baby sitter remark block in place without adding fixed trailing rows', () => {
    const result = convertDickyInternalQuote(
      createBabySitterDickyWorkbook(),
      'Estimate Quotation of the Baby sitter.xlsx',
    )
    const output = createDickyCustomerQuoteWorkbook(result)
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))
    const quote = parsed.sheets.find((sheet) => sheet.name === 'Quotation')

    expect(quote?.rows[16][1]).toBe('Picture estimate: plastic parts 218g; rotocast vinyl 69g. Requote if changed.')
    expect(quote?.rows[17][1]).toBe('Head, hands and feet: rotocast vinyl; body and accessories: plastic.')
    expect(quote?.rows[18][1]).toBe('Production following RoHS & Non-Phthalates,Cadmium,ASTM,EN71,EN62115,FCC.')
    expect(quote?.rows[19][1]).toBe('This is not included any CFS and THC Cost.')
    expect(quote?.rows[20][1]).toBe('Plastic Quotation(HK$/LB):')
    expect(quote?.rows[21][1]).toBe('Type')
    expect(quote?.rows[21][2]).toBe('Cost')
    expect(quote?.rows[21][4]).toBe('Type')
    expect(quote?.rows[21][5]).toBe('Cost')
    expect(quote?.rows[24][1]).toBe('If the Material cost increased more than 5% and the exchange rate of RMB more than 2%,this quote will be revised.')
    expect(quote?.rows[25][1]).toBe('Client has their own responsibility about the patent, design concept and legal issue of their products.')
    expect(quote?.rows[26][1]).toBe('Except client has already paid all the amount of tooling cost, product cost and relevant inventory material cost,we (Royal Regent) has the right of use and own the product.')

    for (let rowIndex = 27; rowIndex <= 33; rowIndex += 1) {
      expect(quote?.rows[rowIndex]?.[1] ?? '').toBe('')
    }
  })

  it('uses the standard English remark style for the first translated notes', () => {
    const source = createBabySitterDickyWorkbook()
    const sourceZip = unzipSync(new Uint8Array(source))
    const result = convertDickyInternalQuote(source, 'Estimate Quotation of the Baby sitter.xlsx')
    const outputZip = unzipSync(createDickyCustomerQuoteWorkbook(result))
    const quotationPath = findSheetPath(outputZip, 'Quotation')

    expect(readCellStyle(sourceZip, 'xl/worksheets/sheet1.xml', 'B17')).toBe('4')
    expect(readCellStyle(sourceZip, 'xl/worksheets/sheet1.xml', 'B20')).toBe('3')
    expect(readCellStyle(outputZip, quotationPath, 'B17')).toBe('3')
    expect(readCellStyle(outputZip, quotationPath, 'B18')).toBe('3')
    expect(readCellStyle(outputZip, quotationPath, 'B19')).toBe('3')
  })

  it('translates every Disney cable-car mold part and its non-empty mold remark', () => {
    const result = convertDickyInternalQuote(
      createDisneyCableMoldPartsWorkbook(),
      'Quotation of the Disney Cable car.xlsx',
    )
    const output = createDickyCustomerQuoteWorkbook(result)
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))
    const quote = parsed.sheets.find((sheet) => sheet.name === 'Quotation')

    disneyCableMoldParts.forEach(([_moldNo, _part, expectedTranslation, sourceRemark], index) => {
      const row = quote?.rows[47 + index] ?? []
      expect(row[2]).toBe(expectedTranslation)
      expect(String(row[2] ?? '')).not.toMatch(/[\u4E00-\u9FFF]/)

      if (sourceRemark) {
        expect(String(row[10] ?? '')).not.toMatch(/[\u4E00-\u9FFF]/)
      }
    })
  })

  it('creates an English Quotation sheet from the imported 总表 workbook', () => {
    const result = convertDickyInternalQuote(
      createMinimalDickyWorkbook(),
      'Dicky Cable internal quote.xlsx',
    )

    expect(result.summarySheetName).toBe('总表')
    expect(result.sheets[0].details[0].description).toContain('Stitch Cable Buggy')
    expect(result.sheets[0].details.some((row) => row.description === 'Car Light')).toBe(true)

    const output = createDickyCustomerQuoteWorkbook(result)
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))
    const quote = parsed.sheets.find((sheet) => sheet.name === 'Quotation')

    expect(parsed.sheets.map((sheet) => sheet.name)).toEqual(['总表', 'Quotation'])
    expect(quote?.rows[8][2]).toBe('Ben/ Dickie')
    expect(quote?.rows[11][1]).toBe('20 307 3001\nStitch Cable Buggy\n(2xAA-LR6 INCLUDED)')
    expect(quote?.rows[12][1]).toBe('20 307 3000\nMinnie Cable\n(2xAA-LR6 EXCLUDED)')
    expect(quote?.rows[24][1]).toBe('Production following RoHS & Non-Phthalates,Cadmium,ASTM,EN71,EN62115,FCC.')
    expect(quote?.rows[27][1]).toBe('Type')
    expect(quote?.rows[27][2]).toBe('Cost')
    expect(quote?.rows[47][2]).toBe('Car Light')
    const fileName = buildDickyCustomerQuoteFileName(result)
    expect(fileName).toBe('Dicky Cable internal quote.xlsx')

    const outputXml = strFromU8(unzipSync(output)['xl/worksheets/sheet2.xml'])
    expect(outputXml).toContain("<f>'Stitch史迪仔'!D52</f>")
  })

  it('keeps the generated Quotation sheet as a 总表 copy when a template is available', () => {
    if (!existsSync(dickyTemplatePath)) {
      return
    }

    const template = readFileSync(dickyTemplatePath)
    const source = createMinimalDickyWorkbook()
    const sourceZip = unzipSync(new Uint8Array(source))
    const result = convertDickyInternalQuote(source, 'Dickie Cable internal quote.xlsx')
    const output = createDickyCustomerQuoteWorkbook(result, template)
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))
    const quote = parsed.sheets.find((sheet) => sheet.name === 'Quotation')
    const outputZip = unzipSync(output)
    const quotationPath = findSheetPath(outputZip, 'Quotation')

    expect(parsed.sheets.map((sheet) => sheet.name)).toEqual(['总表', 'Quotation'])
    expect(quote?.rows[11][1]).toContain('Stitch Cable Buggy')
    expect(quote?.rows[24][1]).toBe('Production following RoHS & Non-Phthalates,Cadmium,ASTM,EN71,EN62115,FCC.')
    expect(quote?.rows[47][2]).toBe('Car Light')

    expect(quotationPath).toBeTruthy()
    expect(strFromU8(outputZip['xl/worksheets/sheet1.xml'])).toBe(strFromU8(sourceZip['xl/worksheets/sheet1.xml']))
    expect(strFromU8(outputZip['xl/styles.xml'])).toBe(strFromU8(sourceZip['xl/styles.xml']))
    expect(readCellStyle(outputZip, quotationPath, 'A37')).toBe(readCellStyle(sourceZip, 'xl/worksheets/sheet1.xml', 'A37'))
    expect(readCellFormula(outputZip, quotationPath, 'J85')).toBe('')
    expect(readCellFormula(outputZip, quotationPath, 'J86')).toBe('SUM(J48:J85)')
    expect(findSelfReferencingFormulaRefs(outputZip, quotationPath)).toEqual([])
  })

  it('keeps the P4 source filename distinct from the generated customer quotation', () => {
    const result = convertDickyInternalQuote(
      createMinimalDickyWorkbook(),
      'IQ-L5-3-DICKIE-P4-v2.xlsx',
    )
    const p4Result = {
      ...result,
      p4QuoteData: {} as NonNullable<typeof result.p4QuoteData>,
    }

    expect(buildDickyCustomerQuoteFileName(p4Result)).toBe(
      'IQ-L5-3-DICKIE-Customer-Quotation.xlsx',
    )
  })

  it('translates mold detail cells that come from linked formula references', () => {
    const source = createFormulaLinkedDickyWorkbook()
    const result = convertDickyInternalQuote(source, 'Dickie Cable internal quote.xlsx')
    const output = createDickyCustomerQuoteWorkbook(result)
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))
    const quote = parsed.sheets.find((sheet) => sheet.name === 'Quotation')

    expect(quote?.rows[47][0]).toBe('20 307 3001\nStitch Cable Buggy')
    expect(quote?.rows[47][2]).toBe('Car Light')
    expect(quote?.rows[47][10]).toBe('Minnie / Stitch / Woody / Olaf (Common Mold)')
    expect(quote?.rows[48][2]).toBe('Gearbox Cover, Gear Cover, Front Small Wheel Cap, Accessories')
  })

  it('does not rewrite the imported 总表 sheet or its existing style definitions', () => {
    const template = createMinimalDickyTemplateWorkbook()
    const sourceZip = unzipSync(new Uint8Array(createMinimalDickyWorkbook()))
    const summaryPath = 'xl/worksheets/sheet1.xml'
    const summaryStyleId = readCellStyle(sourceZip, summaryPath, 'A37')
    const originalStyleXml = strFromU8(sourceZip['xl/styles.xml'])
    const originalXf = readCellXf(sourceZip, summaryStyleId)
    const originalFontId = Number(readXmlAttr(originalXf, 'fontId') || 0)
    const patchedFontId = originalFontId === 4 ? 1 : 4

    sourceZip['xl/styles.xml'] = strToU8(replaceCellXf(
      originalStyleXml,
      summaryStyleId,
      (xf) => xf.replace(/\bfontId="\d+"/, `fontId="${patchedFontId}"`),
    ))

    const sourceBuffer = zipSync(sourceZip)
    const result = convertDickyInternalQuote(asArrayBuffer(sourceBuffer), 'Dickie Cable internal quote.xlsx')
    const outputZip = unzipSync(createDickyCustomerQuoteWorkbook(result, template))
    const quotationPath = findSheetPath(outputZip, 'Quotation')

    expect(summaryStyleId).toBe('13')
    expect(strFromU8(outputZip[summaryPath])).toBe(strFromU8(sourceZip[summaryPath]))
    expect(strFromU8(outputZip['xl/styles.xml'])).toBe(strFromU8(sourceZip['xl/styles.xml']))
    expect(readCellStyle(outputZip, summaryPath, 'A37')).toBe(summaryStyleId)
    expect(readCellXf(outputZip, summaryStyleId)).toBe(readCellXf(sourceZip, summaryStyleId))
    expect(readCellStyle(outputZip, quotationPath, 'A37')).toBe(summaryStyleId)
  })

  it('decodes XML newline entities before writing translated cells', () => {
    const sourceZip = unzipSync(new Uint8Array(createMinimalDickyWorkbook()))
    const sourceSheetPath = 'xl/worksheets/sheet1.xml'
    const sourceXml = strFromU8(sourceZip[sourceSheetPath])
    const encodedXml = sourceXml.replace('20 307 3001\n', '20 307 3001&#10;')

    expect(encodedXml).toContain('&#10;')
    sourceZip[sourceSheetPath] = strToU8(encodedXml)

    const sourceBuffer = zipSync(sourceZip)
    const result = convertDickyInternalQuote(asArrayBuffer(sourceBuffer), 'Dickie Cable internal quote.xlsx')
    const output = createDickyCustomerQuoteWorkbook(result)
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))
    const quote = parsed.sheets.find((sheet) => sheet.name === 'Quotation')
    const outputZip = unzipSync(output)
    const quotationPath = findSheetPath(outputZip, 'Quotation')
    const outputXml = strFromU8(outputZip[quotationPath])

    expect(quote?.rows[11][1]).toContain('\nStitch Cable Buggy')
    expect(outputXml).not.toContain('&amp;#10;')
  })
})
