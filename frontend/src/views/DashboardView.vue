<script setup>
import { computed, onMounted, ref } from 'vue'
import { CircleDollarSign, Lightbulb, PackageCheck, Plus, Wrench, UsersRound } from 'lucide-vue-next'
import { api, money } from '../services/api'

const data = ref(null)
const loading = ref(true)
const error = ref('')
const cards = computed(() => data.value ? [
  { label: 'Equipamentos', value: data.value.equipment, note: `${data.value.equipment_by_status?.AVAILABLE || 0} disponíveis agora`, icon: PackageCheck, tone: 'amber' },
  { label: 'Clientes ativos', value: data.value.customers, note: 'Base interna atualizada', icon: UsersRound, tone: 'dark' },
  { label: 'OS em andamento', value: data.value.open_orders, note: `${data.value.overdue_maintenance} manutenções vencidas`, icon: Wrench, tone: 'orange' },
  { label: 'Carteira em orçamento', value: money(data.value.quotes_total), note: `${data.value.active_quotes} propostas ativas`, icon: CircleDollarSign, tone: 'light' },
] : [])
onMounted(async () => {
  try { data.value = (await api.get('/dashboard/')).data }
  catch { error.value = 'Não foi possível carregar a visão geral.' }
  finally { loading.value = false }
})
</script>

<template>
  <div class="page dashboard-page">
    <header class="page-heading"><div><span class="eyebrow">CENTRAL OPERACIONAL</span><h1>Visão geral</h1><p>Indicadores da operação e oportunidades de investimento.</p></div><router-link to="/locacoes" class="btn primary"><Plus :size="18" />Novo orçamento</router-link></header>
    <div v-if="error" class="error-message">{{ error }}</div>
    <section v-if="!loading && data" class="metric-grid"><article v-for="card in cards" :key="card.label" class="metric-card" :class="card.tone"><div class="metric-icon"><component :is="card.icon" :size="22" /></div><span>{{ card.label }}</span><strong>{{ card.value }}</strong><small>{{ card.note }}</small></article></section>
    <section v-if="data" class="panel purchase-advice"><div class="purchase-advice-icon"><Lightbulb :size="24" /></div><div><span class="eyebrow">SUGESTÃO DE COMPRA · ÚLTIMOS {{ data.purchase_suggestion?.period_days || 180 }} DIAS</span><h2>{{ data.purchase_suggestion?.status === 'REVIEW' ? data.purchase_suggestion.suggestion : 'Ainda não há dados para recomendar uma compra' }}</h2><p>{{ data.purchase_suggestion?.status === 'REVIEW' ? data.purchase_suggestion.reason : data.purchase_suggestion?.message }}</p><div v-if="data.purchase_suggestion?.status === 'REVIEW'" class="purchase-evidence"><div><strong>{{ data.purchase_suggestion.evidence.requests }}</strong><span>solicitações</span></div><div><strong>{{ data.purchase_suggestion.evidence.unmet_demand }}</strong><span>procuras não atendidas</span></div><div><strong>{{ data.purchase_suggestion.evidence.utilization_percent }}%</strong><span>ocupação</span></div><div><strong>{{ money(data.purchase_suggestion.evidence.maintenance_cost) }}</strong><span>custo de manutenção</span></div><div><strong>{{ data.purchase_suggestion.evidence.acquisition_cost ? money(data.purchase_suggestion.evidence.acquisition_cost) : 'Não informado' }}</strong><span>preço de aquisição</span></div></div><small>{{ data.purchase_suggestion?.status === 'REVIEW' ? `Confiança ${data.purchase_suggestion.confidence === 'LOW' ? 'baixa' : data.purchase_suggestion.confidence === 'MEDIUM' ? 'moderada' : 'alta'} · análise automática e explicável, não uma decisão de compra` : 'A sugestão aparecerá após registrar orçamentos ou procura não atendida.' }}. Não considera preços de fornecedores nem substitui análise financeira.</small></div><router-link v-if="data.purchase_suggestion?.status === 'REVIEW'" to="/equipamentos" class="btn secondary">Ver equipamento</router-link></section>
  </div>
</template>
