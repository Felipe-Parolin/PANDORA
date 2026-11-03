<script setup>
import { Eye, PackageCheck } from 'lucide-vue-next'
import { shortDate } from '../services/api'
defineProps({ quote: { type: Object, required: true } })
defineEmits(['open'])
</script>

<template>
  <div class="rental-equipment-names">
    <button v-if="quote.items.length > 2" type="button" class="btn secondary rental-equipment-button" :aria-label="`Ver ${quote.items.length} equipamentos de ${quote.number}`" @click="$emit('open', quote)"><PackageCheck :size="17" /><span>Ver {{ quote.items.length }} equipamentos</span><Eye :size="16" /></button>
    <template v-else><strong v-for="item in quote.items" :key="item.id || item.equipment">{{ item.equipment_name }}<small>{{ item.internal_code }}<template v-if="item.start_date"> · {{ shortDate(item.start_date) }} a {{ shortDate(item.end_date) }}</template></small><small v-if="item.stage_label">{{ item.stage_label }}</small></strong><span v-if="!quote.items.length">Sem equipamentos</span></template>
  </div>
</template>
