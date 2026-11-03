<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Camera, CheckCircle2, Download, Save, ShieldAlert, Trash2, UploadCloud } from 'lucide-vue-next'
import ModalDialog from './ModalDialog.vue'
import StatusBadge from './StatusBadge.vue'
import { api, apiError, can, rows, shortDate } from '../services/api'

const props = defineProps({
  quote: { type: Object, required: true },
  type: { type: String, required: true },
  initialId: { type: Number, default: null },
  embedded: Boolean,
  beforeSave: Function,
  afterSave: Function,
})
const emit = defineEmits(['close', 'changed'])

const inspections = ref([])
const selectedId = ref(props.initialId)
const media = ref([])
const files = ref([])
const error = ref('')
const busy = ref(false)
const savedSignatures = ref({})
let disposed = false
const payloadFor = item => ({ checklist: item.checklist, result: item.result, condition: item.condition, observations: item.observations, critical_impediment: item.critical_impediment })

const selected = computed(() => inspections.value.find(item => item.id === selectedId.value) || inspections.value[0])
const title = computed(() => props.type === 'PRE_RENTAL' ? 'Inspeção pré-locação' : 'Inspeção de devolução')
const itemStage = computed(() => selected.value?.item_stage || props.quote.items?.find(item => item.equipment === selected.value?.equipment)?.stage || ({ APPROVED: 'PENDING', ACTIVE: 'DELIVERED', RETURNED: 'RETURNED', COMPLETED: 'COMPLETED' }[props.quote.status]))
const editable = computed(() => (
  (props.type === 'PRE_RENTAL' && can('maintenance.manage') && ['APPROVED', 'ACTIVE'].includes(props.quote.status) && itemStage.value === 'PENDING')
  || (props.type === 'RETURN' && (can('maintenance.manage') || can('maintenance.view') && can('rentals.inspect')) && ['ACTIVE', 'RETURNED'].includes(props.quote.status) && itemStage.value === 'RETURNED')
))
const completed = computed(() => inspections.value.filter(item => item.result !== 'PENDING').length)
const previous = computed(() => props.quote.inspections?.find(item => item.inspection_type === 'PRE_RENTAL' && item.equipment === selected.value?.equipment))
const hasChanges = computed(() => Boolean(selected.value) && (files.value.length > 0 || JSON.stringify(payloadFor(selected.value)) !== savedSignatures.value[selected.value.id]))

async function load() {
  const { data } = await api.get('/rental-inspections/', { params: { quote: props.quote.id, type: props.type } })
  if (disposed) return
  inspections.value = rows(data).filter(item => !props.embedded || item.id === props.initialId).map(item => ({ ...item, checklist: item.checklist.map(check => ({ ...check })) }))
  savedSignatures.value = Object.fromEntries(inspections.value.map(item => [item.id, JSON.stringify(payloadFor(item))]))
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
  if (!can('media.view')) { media.value = []; return }
  if (!selected.value) return
  const { data } = await api.get('/media/', { params: { rental_inspection: selected.value.id } })
  if (disposed) return
  media.value = rows(data)
}

async function save() {
  if (disposed || !selected.value || busy.value || !editable.value) return false
  busy.value = true
  error.value = ''
  try {
    if (props.beforeSave && await props.beforeSave() === false || disposed) return false
    await api.patch(`/rental-inspections/${selected.value.id}/`, payloadFor(selected.value))
    if (disposed) return false
    if (props.afterSave) await props.afterSave()
    for (const file of [...files.value]) {
      const body = new FormData()
      body.append('name', `${title.value} · ${selected.value.internal_code}`)
      body.append('category', 'INSPECTION')
      body.append('description', selected.value.observations || title.value)
      body.append('rental_inspection', selected.value.id)
      body.append('file', file)
      await api.post('/media/', body)
      files.value = files.value.filter(pending => pending !== file)
    }
    files.value = []
    await load()
    emit('changed')
    return true
  } catch (event) {
    error.value = apiError(event)
    return false
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

async function downloadMedia(item) {
  try {
    const { data } = await api.get(`/media/${item.id}/content/`, { params: { download: '1' }, responseType: 'blob' })
    const url = URL.createObjectURL(data), link = document.createElement('a')
    link.href = url
    link.download = String(item.file || item.name || 'evidencia').split('/').pop()
    document.body.appendChild(link); link.click(); link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (event) { error.value = apiError(event) }
}

onMounted(async () => { try { await load() } catch (event) { error.value = apiError(event) } })
onBeforeUnmount(() => { disposed = true })
defineExpose({ save, hasChanges, editable, busy, selected })
</script>

<template>
  <component :is="embedded ? 'section' : ModalDialog" :class="{ 'inspection-embedded': embedded }" :title="`${title} · ${quote.number}`" wide @close="emit('close')">
    <div class="inspection-progress">
      <div><span class="eyebrow">PROGRESSO</span><strong>{{ completed }}/{{ inspections.length }} equipamentos concluídos</strong></div>
      <div class="progress-track"><i :style="{ width: `${inspections.length ? completed / inspections.length * 100 : 0}%` }" /></div>
    </div>

    <div v-if="type === 'PRE_RENTAL'" class="inspection-flow-hint"><ShieldAlert :size="18" /><span>Chamado da manutenção: conclua o checklist para liberar a entrega. Uma falha mantém o equipamento bloqueado.</span></div>
    <div v-else class="inspection-flow-hint"><ShieldAlert :size="18" /><span>Inspeção final vinculada à OS pós-locação. Se houver avaria, a mesma OS seguirá para reparo antes de liberar o equipamento.</span></div>
    <div v-if="inspections.length" class="inspection-layout">
      <nav class="inspection-equipment-list" aria-label="Equipamentos da inspeção">
        <button v-for="item in inspections" :key="item.id" type="button" :class="{ active: item.id === selected?.id }" @click="selectInspection(item)">
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
            <div><strong>{{ check.label }}</strong><input v-model="check.notes" :disabled="!editable || busy" placeholder="Observação do item (opcional)" /></div>
            <AppSelect v-model="check.status" :disabled="!editable || busy" :class="check.status.toLowerCase()">
              <option value="PENDING">Pendente</option><option value="OK">Conforme</option><option value="WARNING">Ressalva</option><option value="FAIL">Falha</option><option value="NA">Não se aplica</option>
            </AppSelect>
          </article>
        </div>

        <div class="form-grid inspection-summary-form">
          <div class="form-field"><label>Condição geral</label><AppSelect v-model="selected.condition" :disabled="!editable || busy"><option value="GOOD">Bom</option><option value="REGULAR">Regular</option><option value="DAMAGED">Avariado</option><option value="CRITICAL">Crítico</option></AppSelect></div>
          <div class="form-field"><label>Resultado</label><AppSelect v-model="selected.result" :disabled="!editable || busy"><option value="PENDING">Pendente</option><option value="APPROVED">Aprovado</option><option value="APPROVED_WITH_NOTES">Aprovado com ressalvas</option><option value="BLOCKED">Impedido</option></AppSelect></div>
          <div class="form-field span-2"><label>Observações</label><textarea v-model="selected.observations" :disabled="!editable || busy" rows="3" placeholder="Registre estado, avarias, acessórios e demais evidências." /></div>
          <label v-if="editable" class="check-line span-2 critical-check"><input v-model="selected.critical_impediment" type="checkbox" />{{ type === 'RETURN' ? 'Avaria crítica — manter equipamento bloqueado e encaminhar para reparo' : 'Impedimento crítico — bloquear entrega e encaminhar para manutenção' }}</label>
        </div>

        <div class="inspection-media">
          <header><div><span class="eyebrow">EVIDÊNCIAS</span><strong>Fotos e documentos</strong></div><label v-if="editable && can('media.manage')" class="btn secondary"><Camera :size="16" />Selecionar fotos<input type="file" accept="image/*,.pdf" multiple hidden :disabled="busy" @change="files = Array.from($event.target.files)" /></label></header>
          <div v-if="files.length" class="pending-files"><UploadCloud :size="17" />{{ files.length }} arquivo(s) serão enviados ao salvar.</div>
          <div v-if="media.length" class="inspection-media-list"><article v-for="item in media" :key="item.id"><span><strong>{{ item.name }}</strong><small>{{ shortDate(item.created_at?.slice(0, 10)) }} · {{ item.uploaded_by_name }}</small></span><button type="button" class="icon-btn table-action" :aria-label="`Baixar ${item.name}`" @click="downloadMedia(item)"><Download :size="16" /></button><button v-if="editable && can('media.manage')" type="button" class="icon-btn danger-icon" @click="removeMedia(item)"><Trash2 :size="16" /></button></article></div>
        </div>

        <div v-if="selected.performed_by_name" class="inspection-signature"><CheckCircle2 :size="17" /><span>Última conclusão por <strong>{{ selected.performed_by_name }}</strong></span></div>
      </section>
    </div>
    <div v-else class="empty-state compact"><UploadCloud :size="28" /><h2>Nenhuma inspeção gerada</h2><p>Reserve ou registre a devolução antes de iniciar esta etapa.</p></div>
    <div v-if="error" class="error-message">{{ error }}</div>
    <div :class="embedded ? 'inspection-save-actions' : 'modal-actions'"><button v-if="!embedded" type="button" class="btn secondary" @click="emit('close')">Fechar</button><span class="spacer" /><button v-if="editable && selected" type="button" class="btn primary" :disabled="busy" @click="save"><Save :size="17" />{{ busy ? 'Salvando...' : 'Salvar inspeção' }}</button></div>
  </component>
</template>
