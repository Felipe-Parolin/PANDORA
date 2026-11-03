// datetime-local usa o horário do navegador; a API recebe um instante com fuso.
export function toDateTimeInput(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

export function toDateTimePayload(value) {
  if (!value || !String(value).trim()) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) throw new Error('Informe uma data e horário válidos.')
  return date.toISOString()
}
