<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Download, FileImage, FileText, Plus, RotateCw, Trash2, UploadCloud } from 'lucide-vue-next'
import { api, apiError, can, rows, shortDate } from '../services/api'
import ConfirmDialog from './ConfirmDialog.vue'
import ModalDialog from './ModalDialog.vue'

const props = defineProps({ equipment: { type: Object, required: true }, order: { type: Object, default: null } })
const emit = defineEmits(['close', 'changed'])
const items = ref([]), adding = ref(false), file = ref(null), error = ref(''), deleting = ref(null), busy = ref(false)
const loading = ref(false), selectedId = ref(null), previewUrl = ref(''), previewLoading = ref(false), previewError = ref(''), downloading = ref(false)
const selected = computed(() => items.value.find(item => item.id === selectedId.value))
const filename = item => String(item?.file || item?.file_url || item?.name || 'arquivo').split('/').pop().split('?')[0]
const previewType = item => {
  const extension = filename(item).split('.').pop().toLowerCase()
  if (['jpg', 'jpeg', 'png', 'webp'].includes(extension)) return 'image'
  return extension === 'pdf' ? 'pdf' : 'unsupported'
}
let previewRequest = 0
let disposed = false
const form = reactive({ name: '', category: 'MANUAL', description: '' })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const result = []
    let page = 1, more = true
    while (more) {
      const { data } = await api.get('/media/', { params: { ...(props.order ? { service_order: props.order.id } : { equipment: props.equipment.id }), page } })
      if (disposed) return
      result.push(...rows(data))
      more = Boolean(data.next)
      page += 1
    }
    items.value = result
    const next = items.value.find(item => item.id === selectedId.value) || items.value[0]
    await selectItem(next)
  } catch (event) { error.value = apiError(event) || 'Não foi possível carregar as mídias.' }
  finally { loading.value = false }
}
function clearPreview() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}
async function selectItem(item) {
  if (disposed) return
  const request = ++previewRequest
  clearPreview()
  selectedId.value = item?.id ?? null
  previewError.value = ''
  previewLoading.value = false
  if (!item || previewType(item) === 'unsupported') return
  previewLoading.value = true
  try {
    const { data } = await api.get(`/media/${item.id}/content/`, { responseType: 'blob' })
    if (request !== previewRequest) return
    previewUrl.value = URL.createObjectURL(data)
  } catch {
    if (request === previewRequest) previewError.value = 'Não foi possível carregar a prévia. Tente novamente ou baixe o arquivo.'
  } finally { if (request === previewRequest) previewLoading.value = false }
}
async function download() {
  const item = selected.value
  if (!item || downloading.value) return
  downloading.value = true
  try {
    const { data } = await api.get(`/media/${item.id}/content/`, { params: { download: '1' }, responseType: 'blob' })
    const url = URL.createObjectURL(data)
    const link = document.createElement('a')
    link.href = url
    link.download = filename(item)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch { error.value = 'Não foi possível baixar o arquivo.' }
  finally { downloading.value = false }
}
function openUpload() {
  Object.assign(form, { name: '', category: props.order ? 'INSPECTION' : 'MANUAL', description: '' })
  file.value = null; error.value = ''; adding.value = true
}
async function save() {
  if (!file.value || busy.value) return
  busy.value = true
  const body = new FormData()
  Object.entries(form).forEach(([key, value]) => body.append(key, value))
  body.append(props.order ? 'service_order' : 'equipment', props.order?.id || props.equipment.id)
  body.append('file', file.value)
  try {
    const { data } = await api.post('/media/', body)
    selectedId.value = data.id
    adding.value = false
    await load()
    emit('changed')
  } catch (e) { error.value = apiError(e) }
  finally { busy.value = false }
}
async function remove() {
  busy.value = true
  try { await api.delete(`/media/${deleting.value.id}/`); deleting.value = null; await load(); emit('changed') }
  catch (e) { error.value = apiError(e) }
  finally { busy.value = false }
}
onMounted(load)
onBeforeUnmount(() => { disposed = true; previewRequest += 1; clearPreview() })
</script>

<template>
  <ModalDialog :title="`Mídias · ${order?.number || equipment.name}`" wide @close="emit('close')">
    <div class="context-banner"><div><span class="eyebrow">{{ equipment.internal_code }}</span><strong>{{ equipment.brand }} {{ equipment.model }}</strong></div><button v-if="can('media.manage')" class="btn primary" @click="openUpload"><Plus :size="17" />Adicionar arquivo</button></div>
    <div v-if="items.length" class="equipment-media-browser">
      <nav class="equipment-file-list" aria-label="Arquivos do equipamento"><article v-for="item in items" :key="item.id" :class="{ selected: item.id === selectedId }"><button class="equipment-file-select" :aria-pressed="item.id === selectedId" @click="selectItem(item)"><FileImage v-if="previewType(item) === 'image'" :size="20" /><FileText v-else :size="20" /><span><strong>{{ item.name }}</strong><small>{{ item.category_label }}</small></span></button><button v-if="can('media.manage')" class="icon-btn danger-icon" :aria-label="`Excluir ${item.name}`" @click="deleting = item"><Trash2 :size="15" /></button></article></nav>
      <section v-if="selected" class="equipment-file-preview" aria-label="Prévia do arquivo"><header><div><span class="eyebrow">{{ selected.category_label }} · {{ shortDate(selected.created_at?.slice(0, 10)) }}</span><h3>{{ selected.name }}</h3><p v-if="selected.description">{{ selected.description }}</p></div><button class="btn secondary" :disabled="downloading" @click="download"><Download :size="16" />{{ downloading ? 'Baixando...' : 'Baixar' }}</button></header>
        <div v-if="previewLoading" class="file-preview-placeholder" role="status">Carregando prévia...</div>
        <div v-else-if="previewError" class="file-preview-placeholder"><FileText :size="28" /><p>{{ previewError }}</p><button class="btn secondary" @click="selectItem(selected)"><RotateCw :size="15" />Tentar novamente</button></div>
        <div v-else-if="previewType(selected) === 'image' && previewUrl" class="file-image-preview"><img :src="previewUrl" :alt="selected.description || selected.name" @error="previewError = 'Não foi possível exibir esta imagem.'" /></div>
        <iframe v-else-if="previewType(selected) === 'pdf' && previewUrl" class="file-pdf-preview" :src="previewUrl" :title="`Prévia de ${selected.name}`" @error="previewError = 'Não foi possível exibir este PDF. Tente novamente ou baixe o arquivo.'" />
        <div v-else class="file-preview-placeholder"><FileText :size="30" /><strong>{{ filename(selected) }}</strong><p>Este formato não tem prévia no navegador. Use “Baixar” para abri-lo no aplicativo correspondente.</p></div>
      </section>
    </div>
    <div v-else-if="loading" class="empty-state compact" role="status">Carregando mídias...</div>
    <div v-else class="empty-state compact"><UploadCloud :size="30" /><h2>Nenhuma mídia vinculada</h2><p>Adicione manuais, fotos ou documentos deste equipamento.</p></div>
    <GeneralError v-if="error && !adding" :message="error" @close="error = ''" />
  </ModalDialog>

  <ModalDialog v-if="adding" title="Adicionar mídia ao equipamento" @close="adding = false; error = ''">
    <form @submit.prevent="save"><div class="form-grid"><div class="form-field span-2"><label>Nome<span class="required-mark" aria-hidden="true"> *</span></label><input v-model="form.name" placeholder="Ex.: Manual de operação" required /></div><div class="form-field span-2"><label>Categoria</label><AppSelect v-model="form.category"><option value="PHOTO">Foto</option><option value="MANUAL">Manual</option><option value="DOCUMENT">Documento</option><option value="INSPECTION">Evidência de inspeção</option><option value="SERVICE">Evidência de manutenção</option><option value="OTHER">Outro</option></AppSelect></div><div class="form-field span-2"><label>Descrição</label><textarea v-model="form.description" rows="3" placeholder="Descreva o conteúdo e a aplicação deste arquivo." /></div><div class="form-field span-2"><label>Arquivo<span class="required-mark" aria-hidden="true"> *</span></label><input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx" required @change="file = $event.target.files[0]" /></div></div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="adding = false; error = ''">Fechar</button><span class="spacer" /><button class="btn primary" :disabled="busy">{{ busy ? 'Enviando...' : 'Enviar arquivo' }}</button></div></form>
  </ModalDialog>
  <ConfirmDialog v-if="deleting" title="Excluir mídia" :message="`Excluir definitivamente “${deleting.name}”?`" :busy="busy" @cancel="deleting = null" @confirm="remove" />
</template>

<style scoped>
.equipment-media-browser { display: grid; grid-template-columns: minmax(180px, .75fr) minmax(0, 1.65fr); gap: 16px; align-items: start; margin-top: 18px; }
.equipment-file-list { display: grid; gap: 7px; max-height: 650px; overflow-y: auto; }.equipment-file-list article { display: flex; align-items: center; min-width: 0; padding-right: 5px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }.equipment-file-list article.selected { border-color: #e0a524; background: #fff8e9; }
.equipment-file-select { display: flex; flex: 1; align-items: center; gap: 9px; min-width: 0; padding: 12px 10px; border: 0; background: transparent; text-align: left; cursor: pointer; }.equipment-file-select > svg { flex: 0 0 auto; color: #b57600; }.equipment-file-select > span { min-width: 0; }.equipment-file-select strong { display: block; font-size: 11px; overflow-wrap: anywhere; }.equipment-file-select small { display: block; margin-top: 4px; color: var(--muted); font-size: 9px; }
.equipment-file-preview { min-width: 0; overflow: hidden; border: 1px solid var(--line); border-radius: 10px; }.equipment-file-preview > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 15px; border-bottom: 1px solid var(--line); }.equipment-file-preview > header > div { min-width: 0; }.equipment-file-preview h3 { margin: 4px 0 0; font-size: 14px; overflow-wrap: anywhere; }.equipment-file-preview p { margin: 7px 0 0; color: var(--muted); font-size: 11px; line-height: 1.5; }.equipment-file-preview > header .btn { flex: 0 0 auto; min-height: 34px; }
.file-image-preview { display: grid; min-height: 270px; place-items: center; padding: 12px; background: #f4f5f6; }.file-image-preview img { display: block; width: 100%; max-height: 520px; object-fit: contain; }
.file-pdf-preview { display: block; width: 100%; height: 62vh; min-height: 360px; border: 0; background: #f4f5f6; }
.file-preview-placeholder { display: grid; justify-items: center; align-content: center; gap: 12px; min-height: 300px; padding: 25px; color: var(--muted); text-align: center; font-size: 12px; }.file-preview-placeholder strong { max-width: 100%; overflow-wrap: anywhere; }.file-preview-placeholder p { margin: 0; }.file-preview-placeholder > svg { color: #a7a8ac; }
@media (max-width: 820px) { .equipment-media-browser { grid-template-columns: minmax(0, 1fr); }.equipment-file-list { display: flex; max-height: none; padding-bottom: 4px; overflow-x: auto; }.equipment-file-list article { flex: 0 0 210px; }.file-image-preview img { max-height: 430px; } }
@media (max-width: 600px) {
  .equipment-file-preview > header { flex-wrap: wrap; }
  .file-preview-placeholder { min-height: 240px; }
  .file-pdf-preview { height: 58dvh; min-height: 300px; }
}
</style>
