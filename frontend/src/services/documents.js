// Mantém o mesmo valor canônico usado pela API; a máscara não calcula dígitos.
export const normalizeDocument = value => String(value ?? '').replace(/[.\-/\s]/g, '').toUpperCase()

export function formatDocument(value, personType) {
  const raw = normalizeDocument(value)
  const sizes = personType === 'PF' ? [3, 3, 3, 2] : [2, 3, 3, 4, 2]
  const separators = personType === 'PF' ? ['.', '.', '-'] : ['.', '.', '/', '-']
  let position = 0, formatted = ''
  sizes.forEach((size, index) => {
    if (position >= raw.length) return
    if (index) formatted += separators[index-1]
    formatted += raw.slice(position, index === sizes.length-1 ? undefined : position+size)
    position += size
  })
  return formatted
}

export function documentCaret(formatted, rawPosition) {
  if (!rawPosition) return 0
  let count = 0
  for (let index = 0; index < formatted.length; index++) {
    if (!/[.\-/\s]/.test(formatted[index])) count++
    if (count === rawPosition) return index+1
  }
  return formatted.length
}
