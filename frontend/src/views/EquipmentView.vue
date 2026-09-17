<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Files, Pencil, Plus, QrCode, Search, SlidersHorizontal, Trash2 } from 'lucide-vue-next'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import EquipmentMediaModal from '../components/EquipmentMediaModal.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api, apiError, can, money, rows } from '../services/api'

const route = useRoute(), router = useRouter()
const equipment = ref([]), categories = ref([]), search = ref(''), status = ref(''), modal = ref(false), editing = ref(null), deleting = ref(null), mediaEquipment = ref(null), qrEquipment = ref(null), qrUrl = ref(''), scanNotice = ref(''), error = ref(''), busy = ref(false)
const form = reactive({ category: '', name: '', brand: '', model: '', serial_number: '', internal_code: '', status: 'AVAILABLE', daily_rate: '', technical_details: '', current_usage_hours: 0 })
const filtered = computed(() => equipment.value.filter(x => (!status.value || x.status === status.value) && `${x.name} ${x.internal_code} ${x.serial_number}`.toLowerCase().includes(search.value.toLowerCase())))

async function load() {
  const [e, c] = await Promise.all([api.get('/equipment/'), api.get('/categories/')])
  equipment.value = rows(e.data); categories.value = rows(c.data)
}
function open(item = null) {
  editing.value = item; error.value = ''; modal.value = true
  Object.assign(form, item ? { category: item.category, name: item.name, brand: item.brand, model: item.model, serial_number: item.serial_number, internal_code: item.internal_code, status: item.status, daily_rate: item.daily_rate, technical_details: item.technical_details, current_usage_hours: item.current_usage_hours } : { category: categories.value[0]?.id || '', name: '', brand: '', model: '', serial_number: '', internal_code: '', status: 'AVAILABLE', daily_rate: '', technical_details: '', current_usage_hours: 0 })
}
async function save() {
  busy.value = true; error.value = ''
  try { editing.value ? await api.patch(`/equipment/${editing.value.id}/`, form) : await api.post('/equipment/', form); modal.value = false; editing.value = null; await load() }
  catch (e) { error.value = apiError(e) }
  finally { busy.value = false }
}
async function remove() {
  busy.value = true
  try { await api.delete(`/equipment/${deleting.value.id}/`); deleting.value = null; await load() }
  catch (e) { error.value = apiError(e); deleting.value = null }
  finally { busy.value = false }
}
async function openQr(item) {
  qrEquipment.value = item; error.value = ''
  if (qrUrl.value) URL.revokeObjectURL(qrUrl.value)
  try { const { data } = await api.get(`/equipment/${item.id}/qr-code/`, { responseType: 'blob' }); qrUrl.value = URL.createObjectURL(data) }
  catch (e) { error.value = apiError(e) }
}
async function resolveScan() {
  if (!route.query.qr) return
  try {
    const { data } = await api.get(`/equipment/resolve-qr/?token=${encodeURIComponent(route.query.qr)}`)
    scanNotice.value = `QR identificado: ${data.internal_code} · ${data.name}`
    search.value = data.internal_code
    await openQr(data)
  } catch (e) { error.value = apiError(e) }
  finally { router.replace({ path: '/equipamentos' }) }
}
onMounted(async () => { await load(); await resolveScan() })
onBeforeUnmount(() => { if (qrUrl.value) URL.revokeObjectURL(qrUrl.value) })
</script>

<template>
  <div class="page"><header class="page-heading compact"><div><span class="eyebrow">PATRIMÔNIO LOCÁVEL</span><h1>Equipamentos</h1><p>Cadastro, QR Code, documentos e histórico técnico no mesmo contexto.</p></div><button v-if="can('assets.manage')" class="btn primary" @click="open()"><Plus :size="18" />Novo equipamento</button></header>
    <div v-if="scanNotice" class="success-strip">{{ scanNotice }}</div><div v-if="error && !modal && !qrEquipment" class="floating-error">{{ error }}</div>
    <section class="panel list-panel"><header class="list-toolbar"><div class="search-box"><Search :size="17" /><input v-model="search" placeholder="Buscar equipamento, código ou série" /></div><div class="filter-select"><SlidersHorizontal :size="16" /><select v-model="status"><option value="">Todos os status</option><option value="AVAILABLE">Disponível</option><option value="RESERVED">Reservado</option><option value="RENTED">Locado</option><option value="MAINTENANCE">Em manutenção</option><option value="INSPECTION">Em inspeção</option><option value="INACTIVE">Inativo</option></select></div></header><div class="table-wrap"><table><thead><tr><th>Equipamento</th><th>Categoria</th><th>Identificação</th><th>Diária</th><th>Status</th><th>Mídias</th><th class="right">Ações</th></tr></thead><tbody><tr v-for="item in filtered" :key="item.id"><td><strong>{{ item.name }}</strong><small>{{ item.brand }} · {{ item.model }}</small></td><td>{{ item.category_name }}</td><td><strong>{{ item.internal_code }}</strong><small>Série {{ item.serial_number }}</small></td><td><strong>{{ money(item.daily_rate) }}</strong></td><td><StatusBadge :value="item.status" :label="item.status_label" /></td><td><button class="media-count" @click="mediaEquipment = item"><Files :size="15" />{{ item.media_count }} arquivo(s)</button></td><td class="right"><div class="row-actions"><button class="icon-btn table-action" title="Abrir QR Code" @click="openQr(item)"><QrCode :size="17" /></button><button class="icon-btn table-action" title="Documentos e mídias" @click="mediaEquipment = item"><Files :size="17" /></button><button v-if="can('assets.manage')" class="icon-btn table-action" title="Editar" @click="open(item)"><Pencil :size="17" /></button><button v-if="can('assets.manage')" class="icon-btn danger-icon" title="Excluir" @click="deleting = item"><Trash2 :size="17" /></button></div></td></tr></tbody></table></div></section>

    <ModalDialog v-if="modal" :title="editing ? 'Editar equipamento' : 'Cadastrar equipamento'" wide @close="modal = false"><form @submit.prevent="save"><div class="form-grid three"><div class="form-field"><label>Categoria</label><select v-model="form.category" required><option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option></select></div><div class="form-field"><label>Código interno</label><input v-model="form.internal_code" placeholder="EQ-001" required /></div><div class="form-field"><label>Status</label><select v-model="form.status"><option value="AVAILABLE">Disponível</option><option value="RESERVED">Reservado</option><option value="RENTED">Locado</option><option value="MAINTENANCE">Em manutenção</option><option value="INSPECTION">Em inspeção</option><option value="INACTIVE">Inativo</option></select></div><div class="form-field span-2"><label>Nome do equipamento</label><input v-model="form.name" required /></div><div class="form-field"><label>Valor da diária</label><input v-model="form.daily_rate" type="number" min="0" step="0.01" required /></div><div class="form-field"><label>Marca</label><input v-model="form.brand" required /></div><div class="form-field"><label>Modelo</label><input v-model="form.model" required /></div><div class="form-field"><label>Número de série</label><input v-model="form.serial_number" required /></div><div class="form-field"><label>Horas de uso</label><input v-model="form.current_usage_hours" type="number" min="0" /></div><div class="form-field span-2"><label>Características técnicas</label><textarea v-model="form.technical_details" rows="3" /></div></div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = false">Cancelar</button><span class="spacer" /><button class="btn primary" :disabled="busy">{{ editing ? 'Salvar alterações' : 'Salvar equipamento' }}</button></div></form></ModalDialog>

    <ModalDialog v-if="qrEquipment" title="QR Code do equipamento" @close="qrEquipment = null"><div class="qr-dialog"><div class="qr-image"><img v-if="qrUrl" :src="qrUrl" :alt="`QR Code ${qrEquipment.internal_code}`" /><span v-else>Gerando QR Code...</span></div><span class="eyebrow">IDENTIFICAÇÃO ÚNICA</span><h2>{{ qrEquipment.internal_code }} · {{ qrEquipment.name }}</h2><p>Ao escanear, um usuário autenticado abre diretamente este equipamento no PANDORA.</p><code>{{ qrEquipment.qr_code_token }}</code><a v-if="qrUrl" class="btn primary" :href="qrUrl" :download="`qr-${qrEquipment.internal_code}.png`">Baixar QR Code</a></div><div v-if="error" class="error-message">{{ error }}</div></ModalDialog>
    <EquipmentMediaModal v-if="mediaEquipment" :equipment="mediaEquipment" @close="mediaEquipment = null" @changed="load" />
    <ConfirmDialog v-if="deleting" title="Excluir equipamento" :message="`Excluir “${deleting.name}”? Locações, ordens ou documentos vinculados podem impedir a exclusão.`" :busy="busy" @cancel="deleting = null" @confirm="remove" />
  </div>
</template>
