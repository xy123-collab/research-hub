export const CHINA_TIME_ZONE = 'Asia/Shanghai'

/** 后端历史字段是 naive UTC；带 Z/+08:00 的新字段按自身时区解析。 */
export function parsePlatformTime(value: unknown): Date | null {
  if (value === null || value === undefined || value === '') return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  if (typeof value === 'number') {
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? null : date
  }
  let text = String(value).trim()
  if (!text) return null
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) text += 'T00:00:00Z'
  else {
    text = text.replace(' ', 'T')
    if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(text)) text += 'Z'
  }
  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? null : date
}

function parts(value: unknown) {
  const date = parsePlatformTime(value)
  if (!date) return null
  const values: Record<string, string> = {}
  new Intl.DateTimeFormat('zh-CN', {
    timeZone: CHINA_TIME_ZONE,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date).forEach(part => {
    if (part.type !== 'literal') values[part.type] = part.value
  })
  return values
}

export function formatChinaDateTime(value: unknown, fallback = ''): string {
  const p = parts(value)
  return p ? `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}` : fallback
}

export function formatChinaDate(value: unknown, fallback = ''): string {
  const p = parts(value)
  return p ? `${p.year}-${p.month}-${p.day}` : fallback
}

export function platformTimeMs(value: unknown): number {
  return parsePlatformTime(value)?.getTime() ?? Number.NaN
}
