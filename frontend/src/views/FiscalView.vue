<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Building2, FileCheck2, Download, RefreshCw } from 'lucide-vue-next'
import ModalDialog from '../components/ModalDialog.vue'
import FiscalAddressFields from '../components/FiscalAddressFields.vue'
import { api, apiError, can, money, rows } from '../services/api'

const route = useRoute()
const company = ref({})
const rentals = ref([])
const nextPage = ref(null)
const loadingMore = ref(false)
const selectedRental = ref('')
const report = ref(null)
const loading = ref(false)
const saving = ref(false)
const exporting = ref(false)
const error = ref('')
const editorError = ref('')
const editor = ref(null)
const form = reactive({})
let reportRequest = 0
const regimes = [['UNKNOWN', 'A confirmar'], ['SIMPLE', 'Simples Nacional'], ['MEI', 'MEI'], ['PRESUMED', 'Lucro Presumido'], ['REAL', 'Lucro Real']]
const icmsOptions = [['UNKNOWN', 'A confirmar'], ['CONTRIBUTOR', 'Contribuinte do ICMS'], ['EXEMPT', 'Contribuinte isento de inscrição'], ['NON_CONTRIBUTOR', 'Não contribuinte do ICMS']]
const addressDefaults = () => ({ postal_code: '', street: '', number: '', complement: '', neighborhood: '', city: '', state: '', municipality_code: '' })

async function loadRentals(page = 1) {
  const { data } = await api.get('/fiscal/rentals/', { params: { page } })
  rentals.value = page === 1 ? rows(data) : [...rentals.value, ...rows(data)]
  nextPage.value = data.next ? page + 1 : null
}
async function moreRentals() {
  if (loadingMore.value || !nextPage.value) return
  loadingMore.value = true
  try { await loadRentals(nextPage.value) } catch (event) { error.value = apiError(event) }
  finally { loadingMore.value = false }
}
async function loadReport() {
  const request = ++reportRequest
  report.value = null
  if (!selectedRental.value) { loading.value = false; return }
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get(`/fiscal/rentals/${selectedRental.value}/readiness/`)
    if (request === reportRequest) report.value = data
  } catch (event) { if (request === reportRequest) error.value = apiError(event) }
  finally { if (request === reportRequest) loading.value = false }
}
watch(selectedRental, loadReport)
const issuesFor = (group, id = null) => report.value?.issues.filter(item => item.group === group && (id === null || item.entity_id === id)) || []
function issueOwner(item) {
  if (item.group === 'company') return 'Empresa'
  if (item.group === 'customer') return 'Cliente'
  if (item.group === 'equipment') return report.value.equipment.find(entry => entry.id === item.entity_id)?.code || 'Equipamento'
  return 'Locação'
}
function resetForm(data) {
  Object.keys(form).forEach(key => delete form[key])
  const { updated_at, ...values } = data
  Object.assign(form, values)
  editorError.value = ''
}
function editCompany() {
  resetForm({ ...addressDefaults(), ...company.value })
  editor.value = { kind: 'company', title: 'Empresa emitente' }
}
function editCustomer() {
  resetForm({ ...addressDefaults(), ...report.value.customer.fiscal })
  editor.value = { kind: 'customer', id: report.value.customer.id, title: `Dados fiscais · ${report.value.customer.name}` }
}
function editEquipment(item) {
  resetForm({ ...item.fiscal, asset_value: item.fiscal.asset_value ?? '' })
  editor.value = { kind: 'equipment', id: item.id, title: `Dados fiscais · ${item.code}` }
}
async function save() {
  saving.value = true
  editorError.value = ''
  const config = editor.value
  const path = config.kind === 'company' ? '/fiscal/company/' : `/fiscal/${config.kind === 'customer' ? 'customers' : 'equipment'}/${config.id}/`
  const payload = { ...form }
  if (config.kind === 'equipment' && payload.asset_value === '') payload.asset_value = null
  try {
    const { data } = await api.patch(path, payload)
    if (config.kind === 'company') company.value = data.company
    editor.value = null
    await loadReport()
  } catch (event) { editorError.value = apiError(event) }
  finally { saving.value = false }
}
async function exportPreparation() {
  exporting.value = true
  try {
    const { data } = await api.get(`/fiscal/rentals/${selectedRental.value}/export/`, { responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([data], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `pandora-preparacao-fiscal-${report.value.rental.number}.json`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (event) { error.value = apiError(event) }
  finally { exporting.value = false }
}
onMounted(async () => {
  try {
    const [companyResponse] = await Promise.all([api.get('/fiscal/company/'), loadRentals()])
    company.value = companyResponse.data.company
    if (route.query.rental && /^[0-9]+$/.test(String(route.query.rental))) {
      const id = Number(route.query.rental)
      if (!rentals.value.some(item => item.id === id)) rentals.value.unshift((await api.get(`/fiscal/rentals/${id}/`)).data)
      selectedRental.value = id
    }
  } catch (event) { error.value = apiError(event) }
})
</script>

<template>
  <div class="page fiscal-page">
    <header class="page-heading"><div><span class="eyebrow">PREPARAÇÃO DA EMISSÃO</span><h1>Fiscal</h1><p>Confira os dados da empresa, do cliente e dos equipamentos antes de integrar um emissor.</p></div><span class="fiscal-mode">Emissão ainda não conectada</span></header>
    <div v-if="error" class="error-message">{{ error }}</div>
    <section class="panel fiscal-company-card"><div class="fiscal-company-icon"><Building2 :size="24" /></div><div><span class="eyebrow">EMPRESA EMITENTE</span><h2>{{ company.legal_name || 'Configure sua empresa' }}</h2><p>{{ company.cnpj || 'Nenhum CNPJ cadastrado' }}<template v-if="company.city"> · {{ company.city }}/{{ company.state }}</template></p><small>Dados configuráveis para esta instalação. O cadastro começa vazio.</small></div><button v-if="can('fiscal.configure')" class="btn secondary" @click="editCompany">Dados da empresa</button></section>
    <section class="panel fiscal-rental-panel">
      <header class="fiscal-selection"><div class="form-field"><label for="fiscal-rental">Locação para conferir</label><select id="fiscal-rental" v-model="selectedRental"><option value="">Selecione uma locação</option><option v-for="item in rentals" :key="item.id" :value="item.id">{{ item.number }} · {{ item.customer_name }} · {{ item.status_label }}</option></select></div><button v-if="nextPage" class="btn secondary" :disabled="loadingMore" @click="moreRentals">{{ loadingMore ? 'Carregando...' : 'Carregar mais locações' }}</button><button v-if="selectedRental" class="btn secondary" :disabled="loading" @click="loadReport"><RefreshCw :size="15" />Conferir novamente</button></header>
      <div v-if="loading" class="empty-state">Conferindo os cadastros...</div>
      <div v-else-if="!report" class="empty-state"><FileCheck2 :size="28" /><p>Escolha uma locação para ver as informações e as pendências fiscais.</p></div>
      <div v-else class="fiscal-report">
        <header class="fiscal-report-heading"><div><span class="eyebrow">{{ report.rental.number }}</span><h2>{{ report.data_ready ? 'Dados básicos preenchidos' : `${report.issues.length} campo(s) para completar` }}</h2><p>Valor comercial {{ money(report.rental.commercial_totals.total) }} · tributos ainda não calculados</p></div><button class="btn secondary" :disabled="exporting" @click="exportPreparation"><Download :size="16" />Exportar prévia (JSON)</button></header>
        <section class="fiscal-recipient"><div><span class="eyebrow">CLIENTE</span><strong>{{ report.customer.name }}</strong><p>{{ report.customer.document }}</p><small>{{ report.customer.legacy_address || 'Endereço operacional não informado.' }}</small><small>{{ issuesFor('customer').length ? `${issuesFor('customer').length} pendência(s) no cadastro fiscal` : 'Dados fiscais básicos preenchidos' }}</small></div><button v-if="can('fiscal.manage')" class="btn secondary" @click="editCustomer">Dados fiscais do cliente</button></section>
        <div class="table-wrap"><table class="fiscal-equipment-table"><thead><tr><th>Equipamento</th><th>NCM</th><th>Valor do bem</th><th class="right">Cadastro</th></tr></thead><tbody><tr v-for="item in report.equipment" :key="item.id"><td><strong>{{ item.name }}</strong><small>{{ item.code }} · Série {{ item.serial_number }}</small></td><td>{{ item.fiscal.ncm || 'Pendente' }}</td><td>{{ item.fiscal.asset_value ? money(item.fiscal.asset_value) : 'Pendente' }}<small>Base para preparar remessa/retorno</small></td><td class="right"><button v-if="can('fiscal.manage')" class="btn secondary" @click="editEquipment(item)">{{ issuesFor('equipment', item.id).length ? 'Completar' : 'Revisar' }}</button><span v-else>{{ issuesFor('equipment', item.id).length ? 'Pendente' : 'Preenchido' }}</span></td></tr></tbody></table></div>
        <details v-if="report.issues.length" class="fiscal-pending" open><summary>O que falta nos cadastros</summary><ul><li v-for="(item, index) in report.issues" :key="index"><strong>{{ issueOwner(item) }}</strong><span>{{ item.message }}</span></li></ul></details>
        <section class="fiscal-integration-note"><h3>Próxima etapa: integrar e homologar a emissão</h3><p>Esta conferência e a prévia JSON organizam os dados. Não geram nota fiscal, XML autorizado ou protocolo.</p><ul><li v-for="item in report.integration_pending" :key="item">{{ item }}</li></ul></section>
      </div>
    </section>
    <section class="fiscal-operation-cards"><article class="panel"><h3>Cobrança da locação</h3><p>Dados comerciais e dos bens preparados para o documento aplicável à receita de locação, conforme o enquadramento da empresa.</p></article><article class="panel"><h3>Remessa e retorno</h3><p>Movimentação física dos equipamentos tratada separadamente da cobrança. NCM e valor do bem ficam distintos do valor da diária.</p></article></section>

    <ModalDialog v-if="editor" :title="editor.title" :wide="editor.kind !== 'equipment'" @close="editor = null">
      <form class="fiscal-editor" @submit.prevent="save">
        <template v-if="editor.kind === 'company'"><p class="quick-order-lead">Informe os dados da empresa que usará esta instalação. Campos desconhecidos podem ficar em branco para revisão posterior.</p><div class="form-grid"><div class="form-field span-2"><label for="issuer-name">Razão social</label><input id="issuer-name" v-model="form.legal_name" maxlength="180" /></div><div class="form-field"><label for="issuer-trade">Nome fantasia</label><input id="issuer-trade" v-model="form.trade_name" maxlength="150" /></div><div class="form-field"><label for="issuer-cnpj">CNPJ</label><input id="issuer-cnpj" v-model="form.cnpj" maxlength="18" placeholder="Numérico ou alfanumérico" /></div><div class="form-field"><label for="issuer-regime">Regime tributário</label><select id="issuer-regime" v-model="form.tax_regime"><option v-for="option in regimes" :key="option[0]" :value="option[0]">{{ option[1] }}</option></select></div><div class="form-field"><label for="issuer-cnae">CNAE da atividade</label><input id="issuer-cnae" v-model="form.cnae" inputmode="numeric" maxlength="7" placeholder="7 dígitos" /></div><div class="form-field"><label for="issuer-im">Inscrição municipal</label><input id="issuer-im" v-model="form.municipal_registration" maxlength="30" /></div><div class="form-field"><label for="issuer-email">E-mail</label><input id="issuer-email" v-model="form.email" type="email" /></div><div class="form-field"><label for="issuer-phone">Telefone</label><input id="issuer-phone" v-model="form.phone" maxlength="24" /></div></div></template>
        <template v-if="editor.kind !== 'equipment'"><div class="form-grid"><div class="form-field"><label for="fiscal-icms-status">Situação perante o ICMS</label><select id="fiscal-icms-status" v-model="form.icms_status"><option v-for="option in icmsOptions" :key="option[0]" :value="option[0]">{{ option[1] }}</option></select></div><div class="form-field"><label for="fiscal-ie">Inscrição estadual</label><input id="fiscal-ie" v-model="form.state_registration" maxlength="30" /><small>Preencha quando contribuinte com inscrição estadual.</small></div></div><h3>Endereço fiscal</h3><FiscalAddressFields :model="form" :prefix="editor.kind" /></template>
        <div v-else class="form-grid"><div class="form-field span-2"><label for="fiscal-ncm">NCM do equipamento</label><input id="fiscal-ncm" v-model="form.ncm" inputmode="numeric" maxlength="8" placeholder="8 dígitos, sem pontuação" /><small>Use a classificação confirmada para este equipamento.</small></div><div class="form-field span-2"><label for="fiscal-asset-value">Valor do bem (R$)</label><input id="fiscal-asset-value" v-model="form.asset_value" type="number" min="0.01" step="0.01" /><small>Valor informado para preparar a movimentação do bem; não é o preço da diária nem um tributo.</small></div></div>
        <div v-if="editorError" class="error-message">{{ editorError }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="editor = null">Cancelar</button><span class="spacer" /><button class="btn primary" :disabled="saving">{{ saving ? 'Salvando...' : 'Salvar dados' }}</button></div>
      </form>
    </ModalDialog>
  </div>
</template>
