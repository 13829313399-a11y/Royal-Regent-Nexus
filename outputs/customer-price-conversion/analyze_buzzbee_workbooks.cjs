const fs = require('fs')
const path = require('path')
const vm = require('vm')

const sourceDir = 'D:/360安全云盘同步版/成果文件/李悦/内部转报客网页'
const bundlePath = path.join(sourceDir, 'js/xlsx.bundle.js')
const bundleCode = fs.readFileSync(bundlePath, 'utf8')
const context = { window: {}, console }
vm.createContext(context)
vm.runInContext(bundleCode, context)
const XLSX = context.XLSX || context.window.XLSX

const files = [
  {
    kind: 'internal',
    path: path.join(sourceDir, '露营火堆套装枪报价2026-3-15（内部价钱）.xlsx'),
  },
  {
    kind: 'customer',
    path: path.join(sourceDir, 'R0 RR ltem 露营火堆套装 box(2026-3-18）（报客价钱）.xls'),
  },
]

function cellValue(ws, addr) {
  const cell = ws[addr]
  return cell ? cell.v : null
}

function findRows(aoa, matcher) {
  const rows = []
  aoa.forEach((row, idx) => {
    if (matcher(row || [])) rows.push(idx + 1)
  })
  return rows
}

function nonEmptyRows(aoa, limit = 20) {
  const rows = []
  for (let r = 0; r < aoa.length && rows.length < limit; r += 1) {
    const row = aoa[r] || []
    if (row.some((cell) => cell !== null && cell !== undefined && cell !== '')) {
      rows.push({
        row: r + 1,
        values: row.slice(0, 12),
      })
    }
  }
  return rows
}

function inspectWorkbook(file) {
  const buffer = fs.readFileSync(file.path)
  const workbook = XLSX.read(buffer, { type: 'buffer', cellFormula: true, cellStyles: false, raw: true })
  const sheets = workbook.SheetNames.map((name) => {
    const ws = workbook.Sheets[name]
    const aoa = XLSX.utils.sheet_to_json(ws, { header: 1, defval: null, raw: true, blankrows: true })
    const ref = ws['!ref'] || ''
    return {
      name,
      ref,
      anchors: {
        injectionHeaderRows: findRows(aoa, (row) => row[2] === '名称' && row[3] === '料型'),
        internalCostStartRows: findRows(aoa, (row) => row[1] === '料价'),
        clientInjectionRows: findRows(aoa, (row) => row[0] === 'INJECTION'),
        clientPurchaseRows: findRows(aoa, (row) => row[0] === 'PURCHASE'),
        clientCartonRows: findRows(aoa, (row) => row[0] === 'CARTON SIZE'),
        clientOutterRows: findRows(aoa, (row) => row[0] === 'OUTTER'),
        additionalPartsRows: findRows(aoa, (row) => row[5] === 'Additional Parts'),
        totalExFtyRows: findRows(aoa, (row) => row[5] === 'TOTAL Ex-fty cost'),
        usdRows: findRows(aoa, (row) => row[8] === 'US$'),
        colorBoxRows: findRows(aoa, (row) => row.some((cell) => cell === '报客彩盒')),
      },
      keyCells: {
        A1: cellValue(ws, 'A1'),
        A4: cellValue(ws, 'A4'),
        A5: cellValue(ws, 'A5'),
        F1: cellValue(ws, 'F1'),
        G1: cellValue(ws, 'G1'),
        I27: cellValue(ws, 'I27'),
        J27: cellValue(ws, 'J27'),
      },
      firstRows: nonEmptyRows(aoa, 25),
    }
  })
  return {
    kind: file.kind,
    fileName: path.basename(file.path),
    sheetNames: workbook.SheetNames,
    sheets,
  }
}

const result = files.map(inspectWorkbook)
const outputPath = path.join(process.cwd(), 'outputs/customer-price-conversion/buzzbee_workbook_analysis.json')
fs.writeFileSync(outputPath, JSON.stringify(result, null, 2), 'utf8')
console.log(outputPath)
for (const wb of result) {
  console.log(`\n${wb.kind}: ${wb.fileName}`)
  console.log(`sheets: ${wb.sheetNames.join(' | ')}`)
  for (const sheet of wb.sheets) {
    console.log(`- ${sheet.name} ${sheet.ref}`)
    console.log(JSON.stringify(sheet.anchors))
  }
}
