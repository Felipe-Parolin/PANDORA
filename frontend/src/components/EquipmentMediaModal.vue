<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Download, FileImage, FileText, Plus, RotateCw, Trash2, UploadCloud } from 'lucide-vue-next'
import { api, apiError, can, rows, shortDate } from '../services/api'
import ConfirmDialog from './ConfirmDialog.vue'
import ModalDialog from './ModalDialog.vue'

const props = defineProps({ equipment: { type: Object, required: true } })
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
      const { data } = await api.get('/media/', { params: { equipment: props.equipment.id, page } })
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
  Object.assign(form, { name: '', category: 'MANUAL', description: '' })
  file.value = null; error.value = ''; adding.value = true
}
async function save() {
  if (!file.value || busy.value) return
  busy.value = true
  const body = new FormData()
  Object.entries(form).forEach(([key, value]) => body.append(key, value))
  body.append('equipment', props.equipment.id)
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
  <ModalDialog v-if="!adding && !deleting" :title="`Mídias · ${equipment.name}`" wide @close="emit('close')">
    <div class="context-banner"><div><span class="eyebrow">{{ equipment.internal_code }}</span><strong>{{ equipment.brand }} {{ equipment.model }}</strong></div><button v-if="can('media.manage')" class="btn primary" @click="openUpload"><Plus :size="17" />Adicionar arquivo</button></div>
    <div v-if="items.length" class="equipment-media-browser">
      <nav class="equipment-file-list" aria-label="Arquivos do equipamento"><article v-for="item in items" :key="item.id" :class="{ selected: item.id === selectedId }"><button class="equipment-file-select" :aria-pressed="item.id === selectedId" @click="selectItem(item)"><FileImage v-if="previewType(item) === 'image'" :size="20" /><FileText v-else :size="20" /><span><strong>{{ item.name }}</strong><small>{{ item.category_label }}</small></span></button><button v-if="can('media.manage')" class="icon-btn danger-icon" :aria-label="`Excluir ${item.name}`" @click="deleting = item"><Trash2 :size="15" /></button></article></nav>
      <section v-if="selected" class="equipment-file-preview" aria-label="Prévia do arquivo"><header><div><span class="eyebrow">{{ selected.category_label }} · {{ shortDate(selected.created_at?.slice(0, 10)) }}</span><h3>{{ selected.name }}</h3><p v-if="selected.description">{{ selected.description }}</p></div><button class="btn secondary" :disabled="downloading" @click="download"><Download :size="16" />{{ downloading ? 'Baixando...' : 'Baixar' }}</button></header>
        <div v-if="previewLoading" class="file-preview-placeholder" role="status">Carregando prévia...</div>
        <div v-else-if="previewError" class="file-preview-placeholder"><FileText :size="28" /><p>{{ previewError }}</p><button class="btn secondary" @click="selectItem(selected)"><RotateCw :size="15" />Tentar novamente</button></div>
        <div v-else-if="previewType(selected) === 'image' && previewUrl" class="file-image-preview"><img :src="previewUrl" :alt="selected.description || selected.name" @error="previewError = 'Não foi possível exibir esta imagem.'" /></div>
        <iframe v-else-if="previewType(selected) === 'pdf' && previewUrl" class="file-pdf-preview" :src="previewUrl" :title="`Prévia de ${selected.name}`" />
        <div v-else class="file-preview-placeholder"><FileText :size="30" /><strong>{{ filename(selected) }}</strong><p>Este formato não tem prévia no navegador. Use “Baixar” para abri-lo no aplicativo correspondente.</p></div>
      </section>
    </div>
    <div v-else-if="loading" class="empty-state compact" role="status">Carregando mídias...</div>
    <div v-else class="empty-state compact"><UploadCloud :size="30" /><h2>Nenhuma mídia vinculada</h2><p>Adicione manuais, fotos ou documentos deste equipamento.</p></div>
    <div v-if="error && !adding" class="error-message">{{ error }}</div>
    <div class="modal-actions"><span class="spacer" /><button type="button" class="btn secondary" @click="emit('close')">Fechar</button></div>
  </ModalDialog>

  <ModalDialog v-if="adding" title="Adicionar mídia ao equipamento" @close="adding = false">
    <form @submit.prevent="save"><div class="form-grid"><div class="form-field span-2"><label>Nome</label><input v-model="form.name" required /></div><div class="form-field span-2"><label>Categoria</label><select v-model="form.category"><option value="PHOTO">Foto</option><option value="MANUAL">Manual</option><option value="DOCUMENT">Documento</option><option value="INSPECTION">Evidência de inspeção</option><option value="SERVICE">Evidência de manutenção</option><option value="OTHER">Outro</option></select></div><div class="form-field span-2"><label>Descrição</label><textarea v-model="form.description" rows="3" /></div><div class="form-field span-2"><label>Arquivo</label><input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx" required @change="file = $event.target.files[0]" /></div></div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" :disabled="busy" @click="adding = false">Cancelar</button><span class="spacer" /><button class="btn primary" :disabled="busy">{{ busy ? 'Enviando...' : 'Enviar arquivo' }}</button></div></form>
  </ModalDialog>
  <ConfirmDialog v-if="deleting" title="Excluir mídia" :message="`Excluir definitivamente “${deleting.name}”?`" :busy="busy" @cancel="deleting = null" @confirm="remove" />
</template>
