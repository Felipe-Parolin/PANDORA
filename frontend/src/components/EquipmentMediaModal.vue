<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Download, FileImage, FileText, Plus, Trash2, UploadCloud } from 'lucide-vue-next'
import { api, apiError, can, rows, shortDate } from '../services/api'
import ConfirmDialog from './ConfirmDialog.vue'
import ModalDialog from './ModalDialog.vue'

const props = defineProps({ equipment: { type: Object, required: true } })
const emit = defineEmits(['close', 'changed'])
const items = ref([]), adding = ref(false), file = ref(null), error = ref(''), deleting = ref(null), busy = ref(false)
const form = reactive({ name: '', category: 'MANUAL', description: '' })

async function load() {
  const { data } = await api.get(`/media/?equipment=${props.equipment.id}`)
  items.value = rows(data)
}
function openUpload() {
  Object.assign(form, { name: '', category: 'MANUAL', description: '' })
  file.value = null; error.value = ''; adding.value = true
}
async function save() {
  const body = new FormData()
  Object.entries(form).forEach(([key, value]) => body.append(key, value))
  body.append('equipment', props.equipment.id)
  body.append('file', file.value)
  try {
    await api.post('/media/', body)
    adding.value = false
    await load()
    emit('changed')
  } catch (e) { error.value = apiError(e) }
}
async function remove() {
  busy.value = true
  try { await api.delete(`/media/${deleting.value.id}/`); deleting.value = null; await load(); emit('changed') }
  catch (e) { error.value = apiError(e) }
  finally { busy.value = false }
}
onMounted(load)
</script>

<template>
  <ModalDialog :title="`Mídias · ${equipment.name}`" wide @close="emit('close')">
    <div class="context-banner"><div><span class="eyebrow">{{ equipment.internal_code }}</span><strong>{{ equipment.brand }} {{ equipment.model }}</strong></div><button v-if="can('media.manage')" class="btn primary" @click="openUpload"><Plus :size="17" />Adicionar arquivo</button></div>
    <div v-if="items.length" class="media-list">
      <article v-for="item in items" :key="item.id">
        <div class="media-list-icon"><FileImage v-if="item.category === 'PHOTO'" :size="22" /><FileText v-else :size="22" /></div>
        <div><span class="eyebrow">{{ item.category_label }} · {{ shortDate(item.created_at?.slice(0, 10)) }}</span><strong>{{ item.name }}</strong><p>{{ item.description || 'Sem descrição.' }}</p></div>
        <a class="icon-btn table-action" :href="item.file_url" target="_blank" title="Abrir arquivo"><Download :size="18" /></a>
        <button v-if="can('media.manage')" class="icon-btn danger-icon" title="Excluir arquivo" @click="deleting = item"><Trash2 :size="18" /></button>
      </article>
    </div>
    <div v-else class="empty-state compact"><UploadCloud :size="30" /><h2>Nenhuma mídia vinculada</h2><p>Adicione manuais, fotos ou documentos deste equipamento.</p></div>
    <div v-if="error && !adding" class="error-message">{{ error }}</div>
  </ModalDialog>

  <ModalDialog v-if="adding" title="Adicionar mídia ao equipamento" @close="adding = false">
    <form @submit.prevent="save"><div class="form-grid"><div class="form-field span-2"><label>Nome</label><input v-model="form.name" required /></div><div class="form-field span-2"><label>Categoria</label><select v-model="form.category"><option value="PHOTO">Foto</option><option value="MANUAL">Manual</option><option value="DOCUMENT">Documento</option><option value="INSPECTION">Evidência de inspeção</option><option value="SERVICE">Evidência de manutenção</option><option value="OTHER">Outro</option></select></div><div class="form-field span-2"><label>Descrição</label><textarea v-model="form.description" rows="3" /></div><div class="form-field span-2"><label>Arquivo</label><input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx" required @change="file = $event.target.files[0]" /></div></div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="adding = false">Cancelar</button><span class="spacer" /><button class="btn primary">Enviar arquivo</button></div></form>
  </ModalDialog>
  <ConfirmDialog v-if="deleting" title="Excluir mídia" :message="`Excluir definitivamente “${deleting.name}”?`" :busy="busy" @cancel="deleting = null" @confirm="remove" />
</template>
