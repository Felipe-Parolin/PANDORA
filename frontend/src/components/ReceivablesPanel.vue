<script setup>
import { formatTaxId, formatPercent } from '../services/formatters'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ModalDialog from './ModalDialog.vue'
import { Download, Eye, Pencil, RefreshCw, Search, Wallet } from 'lucide-vue-next'
import { api, apiError, can, money, shortDate } from '../services/api'
import { usePagination } from '../services/pagination'

const customers = ref([]), count = ref(0), page = ref(1), search = ref(''), situation = ref(''), ordering = ref('name')
const loading = ref(false), error = ref('')
const client = ref(null), titleStatus = ref('OPEN'), titleSearch = ref(''), titleOrdering = ref('due_date'), titlePage = ref(1)
const titles = ref([]), titleCount = ref(0), titlesBusy = ref(false), selected = ref([])
const selectionTotals = ref(null), selectionBusy = ref(false), selectionError = ref('')
const editor = ref(null), formError = ref(''), saving = ref(false)
const paymentOpen = ref(false), preview = ref(null), payment = ref(null), paymentError = ref(''), paymentBusy = ref(false), previewBusy = ref(false)
const paymentDate = ref(today()), method = ref('PIX'), notes = ref(''), attemptKey = ref('')
const downloadBusy = ref(false)
let customerRequest = 0, titleRequest = 0, previewRequest = 0, selectionRequest = 0, disposed = false, customerTimer, titleTimer, selectionTimer
const manageable = computed(() => can('commercial.receivables.manage'))
const customerSort = [['name','Nome A–Z'],['-name','Nome Z–A'],['-open_principal','Maior saldo'],['-paid_principal','Mais recebido'],['-billed','Mais faturado']]
const titleSort = [['due_date','Vencimento'],['-due_date','Vence depois'],['-issue_date','Mais recentes'],['amount','Menor valor'],['-amount','Maior valor']]
const selectedVisible = computed(() => titles.value.length > 0 && titles.value.every(item => selected.value.includes(item.id)))
const detailItems = computed(() => payment.value?.snapshot?.items || preview.value?.items || [])
const { page: detailPage, items: detailRows } = usePagination(detailItems, [preview, payment])
function today() { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}` }

async function refresh() {
  const id = ++customerRequest
  loading.value = true
  try {
    const {data} = await api.get('/receivables/customers/', {params:{page:page.value,search:search.value,situation:situation.value,ordering:ordering.value}})
    if (disposed || id !== customerRequest) return
    customers.value = data.results; count.value = data.count
    if (page.value > 1 && !data.results.length) page.value = 1
  } catch (event) { if (!disposed && id === customerRequest) error.value = apiError(event) }
  finally { if (id === customerRequest) loading.value = false }
}
async function refreshClient() {
  if (!client.value) return
  const id = client.value.id
  const {data} = await api.get('/receivables/customers/', {params:{customer:id,include_empty:'true'}})
  if (client.value?.id === id && !disposed) client.value = data.results[0] || client.value
}
function openClient(item) { client.value = item; selected.value = []; titles.value = []; titleStatus.value = 'OPEN'; titleSearch.value = ''; titleOrdering.value = 'due_date'; titlePage.value = 1; loadTitles() }
function closeClient() { if (paymentBusy.value || saving.value) return; client.value = null; titleRequest++; selected.value = []; titles.value = [] }
async function loadTitles() {
  if (!client.value) return
  const id = ++titleRequest, customer = client.value.id
  titlesBusy.value = true; titles.value = []
  try {
    const {data} = await api.get('/receivables/', {params:{customer,status:titleStatus.value,page:titlePage.value,search:titleSearch.value,ordering:titleOrdering.value}})
    if (disposed || id !== titleRequest || client.value?.id !== customer) return
    titles.value = data.results; titleCount.value = data.count
    if (titlePage.value > 1 && !data.results.length) titlePage.value = 1
  } catch (event) { if (!disposed && id === titleRequest) error.value = apiError(event) }
  finally { if (id === titleRequest) titlesBusy.value = false }
}
function selectVisible() {
  const ids = titles.value.map(item => item.id)
  selected.value = selectedVisible.value ? selected.value.filter(id => !ids.includes(id)) : [...new Set([...selected.value,...ids])]
}
async function loadSelectedTotal() {
  clearTimeout(selectionTimer)
  if (!client.value || !selected.value.length) return
  const request = ++selectionRequest, customer = client.value.id
  selectionBusy.value = true; selectionError.value = ''; selectionTotals.value = null
  try {
    const {data} = await api.post('/receivables/settlement-preview/', {
      customer, receivable_ids: [...selected.value], payment_date: today(),
    })
    if (disposed || request !== selectionRequest || client.value?.id !== customer) return
    selectionTotals.value = {principal:data.principal,interest:data.interest,total:data.total}
  } catch (event) {
    if (!disposed && request === selectionRequest) selectionError.value = apiError(event)
  } finally { if (request === selectionRequest) selectionBusy.value = false }
}
function openEditor(item) {
  formError.value = ''
  editor.value = {id:item.id,number:item.number,description:item.description,due_date:item.due_date,monthly_interest_rate:item.monthly_interest_rate,grace_days:item.grace_days,amount:item.amount,issue_date:item.issue_date}
}
async function saveTitle() {
  saving.value = true; formError.value = ''
  try {
    const {id,description,due_date,monthly_interest_rate,grace_days} = editor.value
    await api.patch(`/receivables/${id}/`,{description,due_date,monthly_interest_rate,grace_days})
    editor.value = null
    await Promise.all([loadTitles(),refreshClient(),refresh()])
    if (selected.value.length) await loadSelectedTotal()
  } catch (event) { formError.value = apiError(event) }
  finally { saving.value = false }
}
function openPayment() {
  payment.value = null; preview.value = null; paymentError.value = ''; paymentDate.value = today(); method.value = 'PIX'; notes.value = ''; attemptKey.value = ''; paymentOpen.value = true
  loadPreview()
}
async function loadPreview() {
  if (!paymentOpen.value || payment.value || !selected.value.length || !client.value) return
  const id = ++previewRequest
  previewBusy.value = true; preview.value = null; paymentError.value = ''; attemptKey.value = ''
  try {
    const {data} = await api.post('/receivables/settlement-preview/',{customer:client.value.id,receivable_ids:[...selected.value],payment_date:paymentDate.value})
    if (disposed || id !== previewRequest || !paymentOpen.value) return
    preview.value = data
  } catch (event) { if (id === previewRequest && !disposed) paymentError.value = apiError(event) }
  finally { if (id === previewRequest) previewBusy.value = false }
}
async function settlePayment() {
  if (paymentBusy.value || !preview.value || payment.value) return
  if (!attemptKey.value) attemptKey.value = crypto.randomUUID()
  paymentBusy.value = true; paymentError.value = ''
  try {
    const {data} = await api.post('/receivables/settle/',{
      customer:client.value.id,receivable_ids:preview.value.items.map(item=>item.id),payment_date:paymentDate.value,
      method:method.value,notes:notes.value,idempotency_key:attemptKey.value,
      expected_total:preview.value.total,calculation_token:preview.value.calculation_token,
    })
    payment.value = data; selected.value = []; titleStatus.value = 'PAID'; titlePage.value = 1
    await Promise.all([loadTitles(),refreshClient(),refresh()])
  } catch (event) { paymentError.value = apiError(event) }
  finally { paymentBusy.value = false }
}
function closePayment() { if (paymentBusy.value) return; paymentOpen.value = false; previewRequest++; payment.value = null; preview.value = null; paymentError.value = '' }
async function viewReceipt(item) {
  paymentError.value = ''; preview.value = null; payment.value = null; paymentOpen.value = true; previewBusy.value = true
  const id = ++previewRequest
  try {
    const {data} = await api.get(`/payments/${item.payment.id}/`)
    if (!disposed && id === previewRequest && paymentOpen.value) payment.value = data
  } catch (event) { if (id === previewRequest) paymentError.value = apiError(event) }
  finally { if (id === previewRequest) previewBusy.value = false }
}
async function downloadReceipt() {
  if (!payment.value || downloadBusy.value) return
  downloadBusy.value = true; paymentError.value = ''
  try {
    const {data} = await api.get(`/payments/${payment.value.id}/receipt/`,{responseType:'blob'})
    const url = URL.createObjectURL(data), link = document.createElement('a')
    link.href = url; link.download = `${payment.value.number}.pdf`; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000)
  } catch (event) { paymentError.value = 'Não foi possível baixar o recibo. Tente novamente.' }
  finally { downloadBusy.value = false }
}
watch([search,situation,ordering],()=>{page.value=1; clearTimeout(customerTimer); customerTimer=setTimeout(refresh,200)})
watch(page,refresh)
watch([titleStatus,titleSearch,titleOrdering],()=>{titlePage.value=1; clearTimeout(titleTimer); titleTimer=setTimeout(loadTitles,200)})
watch(titlePage,loadTitles)
watch(selected,()=>{
  selectionRequest++; clearTimeout(selectionTimer)
  selectionTotals.value = null; selectionError.value = ''
  selectionBusy.value = Boolean(client.value && selected.value.length)
  if (selectionBusy.value) selectionTimer = setTimeout(loadSelectedTotal,150)
},{deep:true,flush:'sync'})
watch(paymentDate,()=>{ if(paymentOpen.value&&!payment.value&&!paymentBusy.value)loadPreview() })
watch([method,notes],()=>{attemptKey.value='';paymentError.value=''})
onMounted(refresh)
onBeforeUnmount(()=>{disposed=true;customerRequest++;titleRequest++;previewRequest++;selectionRequest++;clearTimeout(customerTimer);clearTimeout(titleTimer);clearTimeout(selectionTimer)})
defineExpose({refresh})
</script>

<template>
  <section class="receivables-section">
    <GeneralError v-if="error" :message="error" @close="error=''" />
    <header class="section-heading finance-heading"><div><h2>Contas a receber</h2><p>Faturamento por cliente, contas em aberto e pagamentos registrados.</p></div><button class="btn secondary" :disabled="loading" @click="refresh"><RefreshCw :size="16" :class="{spinning:loading}"/> Atualizar</button></header>
    <div class="panel finance-table-panel">
      <div class="list-toolbar list-controls">
        <label class="list-control list-search"><span>Pesquisar cliente</span><span class="search-box"><Search :size="17"/><input v-model="search" type="search" placeholder="Nome ou documento" aria-label="Pesquisar contas por cliente" /></span></label>
        <label class="list-control"><span>Situação</span><AppSelect v-model="situation"><option value="">Todas</option><option value="open">Em aberto</option><option value="overdue">Com atraso</option><option value="paid">Com baixas</option></AppSelect></label>
        <ListOrdering v-model="ordering" :options="customerSort" />
      </div>
      <div class="table-wrap"><table><thead><tr><th>Cliente</th><th class="right">Faturado</th><th class="right">Em aberto</th><th class="right">Recebido</th><th class="right">Ações</th></tr></thead><tbody>
        <tr v-for="item in customers" :key="item.id"><td><div class="finance-cell-detail"><strong>{{item.name}}</strong><small>{{formatTaxId(item.document)}}</small></div></td><td class="right"><div class="finance-cell-detail">{{money(item.billed)}}<small>{{item.title_count}} conta(s)</small></div></td><td class="right"><div class="finance-cell-detail"><strong>{{money(item.open_total)}}</strong><small>{{item.open_count}} aberta(s)<template v-if="Number(item.interest)>0"> · juros {{money(item.interest)}}</template></small></div></td><td class="right"><div class="finance-cell-detail">{{money(item.paid_total)}}<small>{{item.paid_count}} baixada(s)</small></div></td><td class="right"><button class="btn secondary" :disabled="loading" @click="openClient(item)"><Eye :size="16"/> Visualizar</button></td></tr>
        <tr v-if="!customers.length"><td colspan="5" class="empty">{{loading?'Carregando contas…':'Nenhuma conta encontrada. As locações são faturadas na primeira entrega.'}}</td></tr>
      </tbody></table></div>
      <PaginationBar v-model="page" :total="count" :loading="loading" />
    </div>
    <p class="commercial-footnote">Juros padrão: 1% ao mês, simples e proporcional por dia, a partir do 6º dia de atraso. As condições e o vencimento podem ser ajustados nas contas em aberto.</p>

    <ModalDialog v-if="client" :title="`Contas · ${client.name}`" wide @close="closeClient">
      <div class="finance-client-summary"><div><span>Faturado</span><strong>{{money(client.billed)}}</strong></div><div><span>Em aberto, com juros</span><strong>{{money(client.open_total)}}</strong></div><div><span>Recebido</span><strong>{{money(client.paid_total)}}</strong></div></div>
      <nav class="tabs finance-status-tabs" aria-label="Situação das contas"><button :class="{active:titleStatus==='OPEN'}" @click="titleStatus='OPEN'">Em aberto</button><button :class="{active:titleStatus==='PAID'}" @click="titleStatus='PAID'">Baixadas</button></nav>
      <div class="list-toolbar list-controls finance-title-filters"><label class="list-control list-search"><span>Pesquisar conta</span><span class="search-box"><Search :size="16"/><input v-model="titleSearch" type="search" placeholder="Conta, locação ou descrição" /></span></label><ListOrdering v-model="titleOrdering" :options="titleSort" /></div>
      <div class="table-wrap finance-title-table"><table><thead><tr><th v-if="titleStatus==='OPEN'&&manageable"><input type="checkbox" aria-label="Selecionar contas desta página" :checked="selectedVisible" :disabled="titlesBusy||!titles.length" @change="selectVisible"/></th><th>Conta</th><th>Vencimento</th><th class="right">Principal</th><th class="right">Juros</th><th class="right">Total</th><th class="right">Ações</th></tr></thead><tbody>
        <tr v-for="item in titles" :key="item.id"><td v-if="titleStatus==='OPEN'&&manageable"><input v-model="selected" type="checkbox" :value="item.id" :aria-label="`Selecionar ${item.number}`" /></td><td><div class="finance-cell-detail"><strong>{{item.number}}</strong><small>{{item.description}}</small><small v-if="item.payment">{{item.payment.number}} · pago em {{shortDate(item.payment.payment_date)}}</small></div></td><td><div class="finance-cell-detail"><span :class="{'finance-overdue':titleStatus==='OPEN'&&item.charges?.late_days>0}">{{shortDate(item.due_date)}}</span><small v-if="titleStatus==='OPEN'">{{formatPercent(item.monthly_interest_rate)}} a.m. · {{item.grace_days}} dias de carência</small></div></td><td class="right">{{money(item.amount)}}</td><td class="right">{{money(item.charges?.interest)}}</td><td class="right"><strong>{{money(item.charges?.total)}}</strong></td><td class="right"><button v-if="titleStatus==='OPEN'&&manageable" class="btn secondary" @click="openEditor(item)"><Pencil :size="15"/> Alterar</button><button v-if="item.payment" class="btn secondary" @click="viewReceipt(item)"><Eye :size="15"/> Recibo</button></td></tr>
        <tr v-if="!titles.length"><td :colspan="titleStatus==='OPEN'&&manageable?7:6" class="empty">{{titlesBusy?'Carregando…':'Nenhuma conta nesta situação.'}}</td></tr>
      </tbody></table></div>
      <PaginationBar v-model="titlePage" :total="titleCount" :loading="titlesBusy"/>
      <div v-if="titleStatus==='OPEN'&&manageable" class="finance-selection-bar">
        <span>{{selected.length}} conta(s) selecionada(s)</span>
        <div class="finance-selection-total" role="status" aria-live="polite" aria-atomic="true"><span>Total selecionado</span><strong>{{selectionBusy?'Somando…':selectionError?'Indisponível':money(selectionTotals?.total||0)}}</strong><small v-if="selectionTotals">Principal {{money(selectionTotals.principal)}} · juros {{money(selectionTotals.interest)}}</small></div>
        <button v-if="selected.length" class="btn secondary" @click="selected=[]">Limpar seleção</button><button class="btn primary" :disabled="!selected.length||titlesBusy||selectionBusy||Boolean(selectionError)" @click="openPayment"><Wallet :size="17"/> Liquidar selecionadas</button>
        <div v-if="selectionError" class="finance-selection-error" role="alert"><span>{{selectionError}}</span><button type="button" class="btn secondary" :disabled="selectionBusy" @click="loadSelectedTotal">Atualizar total</button></div>
      </div>
    </ModalDialog>

    <ModalDialog v-if="editor" :title="`Alterar ${editor.number}`" @close="!saving&&(editor=null)">
      <form @submit.prevent="saveTitle"><div class="form-grid"><div class="form-field span-2"><label>Descrição <span class="required-mark">*</span></label><input v-model="editor.description" maxlength="240" placeholder="Descrição da conta" required /></div><div class="form-field"><label>Vencimento <span class="required-mark">*</span></label><AppDateTime v-model="editor.due_date" type="date" :min="editor.issue_date" required /></div><div class="form-field"><label>Juros mensais (%) <span class="required-mark">*</span></label><AppInput mask="percent" v-model="editor.monthly_interest_rate" min="0" max="100" required placeholder="Ex.: 1,00" /></div><div class="form-field"><label>Carência em dias <span class="required-mark">*</span></label><input v-model.number="editor.grace_days" type="number" min="0" max="365" required placeholder="Ex.: 5" /></div><div class="form-field"><label>Valor original</label><input :value="money(editor.amount)" readonly /></div></div><p class="commercial-footnote">A taxa deve refletir a condição combinada com o cliente. Use zero para não cobrar juros.</p><div v-if="formError" class="error-message" role="alert">{{formError}}</div><div class="modal-actions"><span class="spacer"/><button class="btn primary" :disabled="saving">{{saving?'Salvando…':'Salvar alterações'}}</button></div></form>
    </ModalDialog>

    <ModalDialog v-if="paymentOpen" :title="payment?`Recibo ${payment.number}`:'Conferir pagamento'" wide @close="closePayment">
      <form @submit.prevent="settlePayment">
        <div v-if="!payment" class="form-grid finance-payment-fields"><div class="form-field"><label>Data do pagamento <span class="required-mark">*</span></label><AppDateTime v-model="paymentDate" type="date" :max="today()" required :disabled="paymentBusy"/></div><div class="form-field"><label>Forma de pagamento <span class="required-mark">*</span></label><AppSelect v-model="method" required :disabled="paymentBusy"><option value="PIX">Pix</option><option value="CASH">Dinheiro</option><option value="TRANSFER">Transferência</option><option value="CARD">Cartão</option><option value="OTHER">Outro</option></AppSelect></div><div class="form-field span-2"><label>Observações</label><textarea v-model="notes" rows="2" maxlength="2000" placeholder="Ex.: referência da transferência ou condição acordada" :disabled="paymentBusy"/></div></div>
        <div v-if="payment" class="finance-receipt-info"><strong>{{payment.snapshot.customer.name}}</strong><span>Pago em {{shortDate(payment.payment_date)}} · {{payment.snapshot.method}}</span><p v-if="payment.snapshot.notes">{{payment.snapshot.notes}}</p></div>
        <p v-if="previewBusy" class="commercial-empty">Conferindo valores…</p>
        <div v-if="detailItems.length" class="table-wrap finance-title-table"><table><thead><tr><th>Conta / vencimento</th><th class="right">Principal</th><th class="right">Juros</th><th class="right">Total</th></tr></thead><tbody><tr v-for="item in detailRows" :key="item.id"><td><div class="finance-cell-detail"><strong>{{item.number}} · {{item.description}}</strong><small>{{shortDate(item.due_date)}} · {{formatPercent(item.monthly_interest_rate)}} a.m. · {{item.charged_days}} dia(s) com juros</small></div></td><td class="right">{{money(item.principal)}}</td><td class="right">{{money(item.interest)}}</td><td class="right">{{money(item.total)}}</td></tr></tbody></table><PaginationBar v-model="detailPage" :total="detailItems.length"/></div>
        <div v-if="preview||payment" class="finance-payment-total"><span>{{detailItems.length}} conta(s) · principal {{money((payment||preview).principal)}} + juros {{money((payment||preview).interest)}}</span><strong>{{money((payment||preview).total)}}</strong></div>
        <div v-if="paymentError" class="error-message" role="alert">{{paymentError}}</div>
        <p v-if="!payment" class="commercial-footnote">Confirme somente após receber o pagamento. A baixa quitará integralmente as contas selecionadas e ficará registrada no histórico.</p>
        <div v-if="payment" class="finance-receipt-download"><div><strong>Recibo de pagamento</strong><small>{{payment.number}} · PDF · documento não fiscal</small></div><button type="button" class="btn primary" :disabled="downloadBusy" @click="downloadReceipt"><Download :size="17"/> {{downloadBusy?'Baixando…':'Baixar recibo'}}</button></div>
        <div v-else class="modal-actions"><button type="button" class="btn secondary" :disabled="previewBusy||paymentBusy" @click="loadPreview">Recalcular prévia</button><span class="spacer"/><button class="btn primary" :disabled="!preview||previewBusy||paymentBusy">{{paymentBusy?'Registrando…':'Confirmar recebimento'}}</button></div>
      </form>
    </ModalDialog>
  </section>
</template>

<style scoped>
.finance-cell-detail{min-width:0;flex:1}.finance-cell-detail strong{display:block}.finance-cell-detail small{display:block;margin-top:5px;color:var(--muted);font-size:12px;line-height:1.5}

.receivables-section{display:grid;gap:18px}.finance-heading{padding:0}.finance-table-panel{overflow:hidden}.finance-client-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:20px}.finance-client-summary>div{display:grid;gap:8px;padding:16px;background:#f6f5f2;border:1px solid var(--line);border-radius:10px}.finance-client-summary span{font-size:12px;color:var(--muted)}.finance-client-summary strong{font-size:20px;overflow-wrap:anywhere}.finance-status-tabs{margin-bottom:18px}.finance-title-filters{padding:0 0 18px}.finance-title-table{border:1px solid var(--line);border-radius:10px}.finance-title-table td:first-child{max-width:320px}.finance-overdue{color:#a34433;font-weight:600}.finance-selection-bar{position:sticky;bottom:-24px;z-index:2;background:white;display:flex;align-items:center;flex-wrap:wrap;gap:12px;margin-top:18px;padding-top:18px;border-top:1px solid var(--line)}.finance-selection-total{display:grid;gap:4px;text-align:right}.finance-selection-total>span,.finance-selection-total>small{color:var(--muted);font-size:11px}.finance-selection-total>strong{font-size:20px;font-variant-numeric:tabular-nums}.finance-selection-error{display:flex;align-items:center;justify-content:space-between;gap:12px;flex:1 1 100%;font-size:12px;color:#a34433}.finance-selection-bar>span{margin-right:auto;font-size:13px;color:var(--muted)}.finance-payment-fields{margin-bottom:22px}.finance-payment-total{display:flex;justify-content:space-between;align-items:center;gap:18px;flex-wrap:wrap;padding:20px 0}.finance-payment-total>span{font-size:13px;color:var(--muted)}.finance-payment-total strong{font-size:25px}.finance-receipt-info{display:grid;gap:8px;margin-bottom:20px}.finance-receipt-info>span,.finance-receipt-info p{color:var(--muted);font-size:13px}.finance-receipt-download{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;padding:18px;background:#f6f5f2;border:1px solid var(--line);border-radius:10px}.finance-receipt-download small{display:block;margin-top:6px;color:var(--muted)}
@media(max-width:640px){.finance-client-summary{grid-template-columns:1fr;gap:8px}.finance-client-summary>div{display:flex;justify-content:space-between;align-items:center;padding:12px}.finance-client-summary strong{font-size:17px}.finance-selection-bar{bottom:-16px}.finance-selection-total{flex:1 1 auto}.finance-selection-bar .btn.primary,.finance-receipt-download .btn{width:100%}}
</style>
