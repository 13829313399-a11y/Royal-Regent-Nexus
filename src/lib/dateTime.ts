export const BUSINESS_TIME_ZONE = 'Asia/Shanghai'

const BUSINESS_UTC_OFFSET = '+08:00'
const DATE_ONLY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/
const LEGACY_DATE_TIME_PATTERN = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?$/
const EXPLICIT_OFFSET_PATTERN = /(?:Z|[+-]\d{2}:?\d{2})$/i
const EXPLICIT_DATE_TIME_PATTERN = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,9})?)?(?:Z|[+-](\d{2}):?(\d{2}))$/i

export interface BusinessDateTimeFormatOptions {
  includeSeconds?: boolean
  fallback?: string
}

function isValidDateParts(year: number, month: number, day: number) {
  if (year < 1 || month < 1 || month > 12 || day < 1) return false
  const daysInMonth = [31, (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0 ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
  return day <= daysInMonth[month - 1]!
}

function isValidTimeParts(hour: number, minute: number, second: number) {
  return hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59 && second >= 0 && second <= 59
}

function normalizedDateOnly(value: string) {
  const match = DATE_ONLY_PATTERN.exec(value)
  if (!match) return null

  const [, yearText, monthText, dayText] = match
  const year = Number(yearText)
  const month = Number(monthText)
  const day = Number(dayText)
  return isValidDateParts(year, month, day) ? value : null
}

function normalizeExplicitOffset(value: string) {
  const isoValue = value.replace(' ', 'T')
  return isoValue.replace(/([+-]\d{2})(\d{2})$/, '$1:$2')
}

function explicitDateTimeIsValid(value: string) {
  const match = EXPLICIT_DATE_TIME_PATTERN.exec(value)
  if (!match) return false
  const [, yearText, monthText, dayText, hourText, minuteText, secondText = '00', offsetHourText, offsetMinuteText] = match
  const dateIsValid = isValidDateParts(Number(yearText), Number(monthText), Number(dayText))
  const timeIsValid = isValidTimeParts(Number(hourText), Number(minuteText), Number(secondText))
  const offsetIsValid = offsetHourText === undefined
    || (Number(offsetHourText) <= 23 && Number(offsetMinuteText) <= 59)
  return dateIsValid && timeIsValid && offsetIsValid
}

function parseLegacyDateTime(value: string) {
  const match = LEGACY_DATE_TIME_PATTERN.exec(value)
  if (!match) return null

  const [, yearText, monthText, dayText, hourText, minuteText, secondText = '00', fractionText = ''] = match
  const year = Number(yearText)
  const month = Number(monthText)
  const day = Number(dayText)
  const hour = Number(hourText)
  const minute = Number(minuteText)
  const second = Number(secondText)
  if (
    !isValidDateParts(year, month, day)
    || !isValidTimeParts(hour, minute, second)
  ) {
    return null
  }

  const fraction = fractionText ? `.${fractionText.slice(0, 3).padEnd(3, '0')}` : ''
  const timestamp = Date.parse(
    `${yearText}-${monthText}-${dayText}T${hourText}:${minuteText}:${secondText}${fraction}${BUSINESS_UTC_OFFSET}`,
  )
  return Number.isFinite(timestamp) ? timestamp : null
}

export function parseBusinessTimestamp(value: string | null | undefined): number | null {
  const normalizedValue = value?.trim()
  if (!normalizedValue) return null

  const dateOnly = normalizedDateOnly(normalizedValue)
  if (dateOnly) return Date.parse(`${dateOnly}T00:00:00${BUSINESS_UTC_OFFSET}`)

  if (EXPLICIT_OFFSET_PATTERN.test(normalizedValue)) {
    if (!explicitDateTimeIsValid(normalizedValue)) return null
    const timestamp = Date.parse(normalizeExplicitOffset(normalizedValue))
    return Number.isFinite(timestamp) ? timestamp : null
  }

  return parseLegacyDateTime(normalizedValue)
}

function businessDateParts(timestamp: number, includeTime: boolean) {
  const formatter = new Intl.DateTimeFormat('zh-CN', {
    timeZone: BUSINESS_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    ...(includeTime
      ? {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hourCycle: 'h23' as const,
        }
      : {}),
  })
  return Object.fromEntries(
    formatter.formatToParts(timestamp)
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, part.value]),
  )
}

export function formatBusinessDate(
  value: string | null | undefined,
  fallback = '-',
) {
  const normalizedValue = value?.trim()
  if (!normalizedValue) return fallback

  const dateOnly = normalizedDateOnly(normalizedValue)
  if (dateOnly) return dateOnly

  const timestamp = parseBusinessTimestamp(normalizedValue)
  if (timestamp === null) return fallback
  const parts = businessDateParts(timestamp, false)
  return `${parts.year}-${parts.month}-${parts.day}`
}

export function formatBusinessDateTime(
  value: string | null | undefined,
  options: BusinessDateTimeFormatOptions = {},
) {
  const fallback = options.fallback ?? '-'
  const timestamp = parseBusinessTimestamp(value)
  if (timestamp === null) return fallback

  const parts = businessDateParts(timestamp, true)
  const dateTime = `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`
  return options.includeSeconds ? `${dateTime}:${parts.second}` : dateTime
}
