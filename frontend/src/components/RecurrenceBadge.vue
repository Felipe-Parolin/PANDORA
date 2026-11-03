<script setup>
import { computed } from 'vue'
import { levelTone } from '../services/ai'

const props = defineProps({ assessment: { type: Object, default: null }, detailed: Boolean })
const tone = computed(() => levelTone[props.assessment?.level] || 'neutral')
</script>

<template>
  <div v-if="assessment" class="ai-risk" :class="tone">
    <div class="ai-risk-score"><strong>{{ assessment.score }}</strong><small>/100</small></div>
    <div class="ai-risk-body">
      <span class="eyebrow">RISCO DE RECORRÊNCIA · {{ assessment.level_label.toUpperCase() }}</span>
      <div class="ai-risk-bar" role="img" :aria-label="`Risco ${assessment.level_label}: ${assessment.score} de 100`"><i :style="{ width: `${assessment.score}%` }" /></div>
      <ul v-if="detailed" class="ai-risk-factors">
        <li v-for="factor in assessment.factors" :key="factor.key"><strong>{{ factor.label }} · {{ factor.points }}/{{ factor.max }}</strong><span>{{ factor.detail }}</span></li>
      </ul>
      <small v-if="detailed && assessment.metrics.recurring_terms?.length">Termos recorrentes nos relatos: {{ assessment.metrics.recurring_terms.join(', ') }}.</small>
      <small v-if="detailed" class="ai-risk-note">Indicador de apoio para priorizar a análise humana; não altera prioridade nem situação do equipamento.</small>
    </div>
  </div>
</template>
