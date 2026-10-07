<script setup>
import { computed, onMounted, ref } from 'vue'
import { Camera, CheckCircle2, Download, Save, ShieldAlert, Trash2, UploadCloud } from 'lucide-vue-next'
import ModalDialog from './ModalDialog.vue'
import StatusBadge from './StatusBadge.vue'
import { api, apiError, can, rows, shortDate } from '../services/api'

const props = defineProps({
  quote: { type: Object, required: true },
  type: { type: String, required: true },
})
const emit = defineEmits(['close', 'changed'])

const inspections = ref([])
const selectedId = ref(null)
const media = ref([])
const files = ref([])
const error = ref('')
const busy = ref(false)

const selected = computed(() => inspections.value.find(item => item.id === selectedId.value) || inspections.value[0])
const title = computed(() => props.type === 'PRE_RENTAL' ? 'Inspeção pré-locação' : 'Inspeção de devolução')
const editable = computed(() => can('rentals.inspect') && (
  (props.type === 'PRE_RENTAL' && props.quote.status === 'APPROVED')
  || (props.type === 'RETURN' && props.quote.status === 'RETURNED')
))
const completed = computed(() => inspections.value.filter(item => item.result !== 'PENDING').length)
const previous = computed(() => props.quote.inspections?.find(item => item.inspection_type === 'PRE_RENTAL' && item.equipment === selected.value?.equipment))

async function load() {
  const { data } = await api.get('/rental-inspections/', { params: { quote: props.quote.id, type: props.type } })
  inspections.value = rows(data).map(item => ({ ...item, checklist: item.checklist.map(check => ({ ...check })) }))
  if (!inspections.value.some(item => item.id === selectedId.value)) selectedId.value = inspections.value[0]?.id
  await loadMedia()
}

async function selectInspection(item) {
  selectedId.value = item.id
  error.value = ''
  files.value = []
  await loadMedia()
}

async function loadMedia() {
  if (!selected.value) return
  const { data } = await api.get('/media/', { params: { rental_inspection: selected.value.id } })
  media.value = rows(data)
}

async function save() {
  if (!selected.value) return
  busy.value = true
  error.value = ''
  try {
    await api.patch(`/rental-inspections/${selected.value.id}/`, {
      checklist: selected.value.checklist,
      result: selected.value.result,
      condition: selected.value.condition,
      observations: selected.value.observations,
      critical_impediment: selected.value.critical_impediment,
    })
    for (const file of files.value) {
      const body = new FormData()
      body.append('name', `${title.value} · ${selected.value.internal_code}`)
      body.append('category', 'INSPECTION')
      body.append('description', selected.value.observations || title.value)
      body.append('rental_inspection', selected.value.id)
      body.append('file', file)
      await api.post('/media/', body)
    }
    files.value = []
    await load()
    emit('changed')
  } catch (event) {
    error.value = apiError(event)
  } finally {
    busy.value = false
  }
}

async function removeMedia(item) {
  busy.value = true
  error.value = ''
  try {
    await api.delete(`/media/${item.id}/`)
    await loadMedia()
    emit('changed')
  } catch (event) {
    error.value = apiError(event)
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <ModalDialog :title="`${title} · ${quote.number}`" wide @close="emit('close')">
    <div class="inspection-progress">
      <div><span class="eyebrow">PROGRESSO</span><strong>{{ completed }}/{{ inspections.length }} equipamentos concluídos</strong></div>
      <div class="progress-track"><i :style="{ width: `${inspections.length ? completed / inspections.length * 100 : 0}%` }" /></div>
    </div>

    <div v-if="inspections.length" class="inspection-layout">
      <nav class="inspection-equipment-list" aria-label="Equipamentos da inspeção">
        <button v-for="item in inspections" :key="item.id" :class="{ active: item.id === selected?.id }" @click="selectInspection(item)">
          <span><strong>{{ item.internal_code }}</strong><small>{{ item.equipment_name }}</small></span>
          <StatusBadge :value="item.result" :label="item.result === 'PENDING' ? 'Pendente' : (item.result === 'BLOCKED' ? 'Impedido' : 'Concluído')" />
        </button>
      </nav>

      <section v-if="selected" class="inspection-editor">
        <div v-if="type === 'RETURN' && previous" class="comparison-strip">
          <div><span class="eyebrow">CONDIÇÃO NA SAÍDA</span><strong>{{ previous.condition_label }}</strong><small>{{ previous.observations || 'Sem ressalvas registradas.' }}</small></div>
          <div><span class="eyebrow">CONDIÇÃO NA DEVOLUÇÃO</span><strong>{{ selected.condition_label || 'Em avaliação' }}</strong><small>Compare os registros antes de concluir.</small></div>
        </div>

        <header class="inspection-editor-heading">
          <div><span class="eyebrow">{{ selected.category_name }}</span><h3>{{ selected.internal_code }} · {{ selected.equipment_name }}</h3></div>
          <ShieldAlert v-if="selected.critical_impediment" :size="24" />
        </header>

        <div class="checklist-editor">
          <article v-for="check in selected.checklist" :key="check.id">
            <div><strong>{{ check.label }}</strong><input v-model="check.notes" :disabled="!editable" placeholder="Observação do item (opcional)" /></div>
            <select v-model="check.status" :disabled="!editable" :class="check.status.toLowerCase()">
              <option value="PENDING">Pendente</option><option value="OK">Conforme</option><option value="WARNING">Ressalva</option><option value="FAIL">Falha</option><option value="NA">Não se aplica</option>
            </select>
          </article>
        </div>

        <div class="form-grid inspection-summary-form">
          <div class="form-field"><label>Condição geral</label><select v-model="selected.condition" :disabled="!editable"><option value="GOOD">Bom</option><option value="REGULAR">Regular</option><option value="DAMAGED">Avariado</option><option value="CRITICAL">Crítico</option></select></div>
          <div class="form-field"><label>Resultado</label><select v-model="selected.result" :disabled="!editable"><option value="PENDING">Pendente</option><option value="APPROVED">Aprovado</option><option value="APPROVED_WITH_NOTES">Aprovado com ressalvas</option><option value="BLOCKED">Impedido</option></select></div>
          <div class="form-field span-2"><label>Observações</label><textarea v-model="selected.observations" :disabled="!editable" rows="3" placeholder="Registre estado, avarias, acessórios e demais evidências." /></div>
          <label v-if="editable" class="check-line span-2 critical-check"><input v-model="selected.critical_impediment" type="checkbox" />Impedimento crítico — bloquear entrega e encaminhar para manutenção</label>
        </div>

        <div class="inspection-media">
          <header><div><span class="eyebrow">EVIDÊNCIAS</span><strong>Fotos e documentos</strong></div><label v-if="editable" class="btn secondary"><Camera :size="16" />Selecionar fotos<input type="file" accept="image/*,.pdf" multiple hidden @change="files = Array.from($event.target.files)" /></label></header>
          <div v-if="files.length" class="pending-files"><UploadCloud :size="17" />{{ files.length }} arquivo(s) serão enviados ao salvar.</div>
          <div v-if="media.length" class="inspection-media-list"><article v-for="item in media" :key="item.id"><span><strong>{{ item.name }}</strong><small>{{ shortDate(item.created_at?.slice(0, 10)) }} · {{ item.uploaded_by_name }}</small></span><a :href="item.file_url" target="_blank" class="icon-btn table-action"><Download :size="16" /></a><button v-if="editable && can('media.manage')" class="icon-btn danger-icon" @click="removeMedia(item)"><Trash2 :size="16" /></button></article></div>
        </div>

        <div v-if="selected.performed_by_name" class="inspection-signature"><CheckCircle2 :size="17" /><span>Última conclusão por <strong>{{ selected.performed_by_name }}</strong></span></div>
      </section>
    </div>
    <div v-else class="empty-state compact"><UploadCloud :size="28" /><h2>Nenhuma inspeção gerada</h2><p>Reserve ou registre a devolução antes de iniciar esta etapa.</p></div>
    <div v-if="error" class="error-message">{{ error }}</div>
    <div class="modal-actions"><button type="button" class="btn secondary" @click="emit('close')">Fechar</button><span class="spacer" /><button v-if="editable && selected" class="btn primary" :disabled="busy" @click="save"><Save :size="17" />{{ busy ? 'Salvando...' : 'Salvar inspeção' }}</button></div>
  </ModalDialog>
</template>
