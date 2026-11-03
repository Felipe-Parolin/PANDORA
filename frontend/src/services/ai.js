import { api, can } from './api'

const get = async (url, params) => (await api.get(url, { params })).data
const post = async (url, body, config) => (await api.post(url, body, config)).data

export const canUseAI = () => can('ai.assist')

export const aiApi = {
  status: () => get('/ai/status/'),
  diagnose: payload => post('/ai/diagnose/', payload),
  ask: payload => post('/ai/ask/', payload),
  search: payload => post('/ai/search/', payload),
  extractReport: payload => post('/ai/extract-report/', payload),
  transcribe: (blob) => {
    const body = new FormData()
    const extension = blob.type.includes('mp4') ? 'm4a' : blob.type.includes('ogg') ? 'ogg' : 'webm'
    body.append('audio', blob, `relato.${extension}`)
    return post('/ai/transcribe/', body)
  },
  decide: (id, payload) => post(`/ai/consultations/${id}/decision/`, payload),
  consultations: params => get('/ai/consultations/', params),
  recurrence: (limit = 5) => get('/ai/recurrence/', { limit }),
  equipmentRecurrence: id => get(`/ai/recurrence/${id}/`),
  report: params => get('/ai/reports/operational/', params),
  summarizeReport: payload => post('/ai/reports/summary/', payload),
  knowledge: equipment => get('/ai/knowledge/', { equipment }),
  reindex: payload => post('/ai/knowledge/', payload),
}

export const confidenceLabel = { baixa: 'Confiança baixa', média: 'Confiança média', alta: 'Confiança alta' }
export const levelTone = { LOW: 'success', MEDIUM: 'warning', HIGH: 'danger' }
