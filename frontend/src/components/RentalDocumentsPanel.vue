<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { Download, FileText } from 'lucide-vue-next'
import { api, apiError, can } from '../services/api'

const props = defineProps({ quote: { type: Object, required: true } })
const documents = ref([]), loading = ref(false), busy = ref(false), error = ref('')
let request = 0

async function load() {
  const current = ++request
  documents.value = []; error.value = ''; loading.value = true
  try {
    const { data } = await api.get(`/rental-quotes/${props.quote.id}/documents/`)
    if (current === request) documents.value = data
  } catch (event) { if (current === request) error.value = apiError(event) }
  finally { if (current === request) loading.value = false }
}
async function download(item) {
  busy.value = true; error.value = ''
  try {
    const { data } = await api.get(`/rental-quotes/${props.quote.id}/documents/${item.id}/pdf/`, { responseType: 'blob' })
    const url = URL.createObjectURL(data)
    const link = document.createElement('a')
    link.href = url
    link.download = `pandora-${props.quote.number.toLowerCase()}-${item.kind.toLowerCase()}-v${item.version}.pdf`
    document.body.appendChild(link); link.click(); link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (event) {
    if (event.response?.data instanceof Blob) {
      try { event.response.data = JSON.parse(await event.response.data.text()) } catch { /* Falha sem resposta JSON. */ }
    }
    error.value = apiError(event)
  } finally { busy.value = false }
}
async function generate(kind) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const { data } = await api.post(`/rental-quotes/${props.quote.id}/documents/`, { kind })
    await load()
    await download(data)
  } catch (event) { error.value = apiError(event) }
  finally { busy.value = false }
}
const dateTime = value => new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
watch(() => props.quote.id, load, { immediate: true })
onBeforeUnmount(() => { request += 1 })
</script>

<template>
  <details class="rental-documents" open>
    <summary>Documentos e comprovantes</summary>
    <p>Documentos comerciais/operacionais não fiscais, sem assinatura ou validade fiscal. Cada versão preserva os dados usados na geração.</p>
    <div class="rental-document-actions">
      <template v-if="can('rentals.manage')">
      <button class="btn secondary" :disabled="busy || loading" @click="generate('QUOTE')">Gerar orçamento em PDF</button>
      <button v-if="quote.delivered_at" class="btn secondary" :disabled="busy || loading" @click="generate('DELIVERY')">Gerar comprovante de entrega</button>
      <button v-if="quote.returned_at || quote.items?.some(item => item.returned_at)" class="btn secondary" :disabled="busy || loading" @click="generate('RETURN')">Gerar comprovante de devolução</button>
      </template>
      <button class="btn secondary" :disabled="busy || loading" @click="load">Atualizar histórico</button>
    </div>
    <p v-if="loading" role="status">Carregando versões...</p>
    <GeneralError v-if="error" :message="error" @close="error = ''" />
    <div v-if="documents.length" class="rental-document-list">
      <button v-for="item in documents" :key="item.id" class="rental-document-item" :disabled="busy || loading" @click="download(item)">
        <FileText :size="25" class="document-file-icon" /><span class="document-description"><strong>{{ item.kind_label }} · versão {{ item.version }}</strong><small>{{ dateTime(item.created_at) }} · {{ item.created_by_name }}</small></span>
        <span class="document-download-action"><Download :size="17" />Baixar PDF</span>
      </button>
    </div>
    <small v-else-if="!loading && !error">Nenhum documento gerado para esta locação.</small>
  </details>
</template>

<style scoped>
.rental-documents { margin-top: 17px; border: 1px solid var(--line); border-radius: 9px; background: #fafafa; }
.rental-documents > summary { padding: 13px 15px; font-size: 12px; font-weight: 800; cursor: pointer; }
.rental-documents > p, .rental-documents > small { display: block; margin: 0; padding: 0 15px 13px; color: var(--muted); font-size: 12px; line-height: 1.6; }
.rental-document-actions { display: flex; flex-wrap: wrap; gap: 8px; padding: 0 15px 14px; }
.rental-document-actions .btn { min-height: 36px; }
.rental-document-list { display: grid; gap: 10px; padding: 0 15px 16px; }
.rental-document-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; padding: 16px; border: 1px solid var(--line); border-radius: 9px; background: white; text-align: left; cursor: pointer; }
.rental-document-item strong, .rental-document-item small { display: block; }
.rental-document-item strong { font-size: 13px; }.rental-document-item small { margin-top: 3px; color: var(--muted); font-size: 11px; }
.rental-document-item > span:last-child { flex: 0 0 auto; color: #9b5700; font-size: 10px; font-weight: 800; }
@media (max-width: 600px) {
  .rental-document-actions { display: grid; }
  .rental-document-actions .btn { width: 100%; }
  .rental-document-item { flex-wrap: wrap; }
}
.document-description { flex: 1; min-width: 0; }.document-file-icon { color: var(--burnt); flex-shrink: 0; }.document-download-action { display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 40px; padding: 8px 12px; border-radius: 7px; background: #fff2d2; font-size: 12px !important; }.rental-document-item:hover { border-color: var(--amber); }.rental-document-actions .btn { min-height: 44px; }
@media (max-width: 600px) { .document-download-action { width: 100%; }.document-description { flex-basis: 70%; } }
</style>
