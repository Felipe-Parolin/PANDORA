<script setup>
defineProps({ model: { type: Object, required: true }, prefix: { type: String, default: 'fiscal' } })
const states = 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(' ')
</script>

<template>
  <div class="form-grid fiscal-address-fields">
    <div class="form-field"><label :for="`${prefix}-postal`">CEP</label><input :id="`${prefix}-postal`" v-model="model.postal_code" maxlength="9" placeholder="00000-000" /></div>
    <div class="form-field"><label :for="`${prefix}-state`">UF</label><select :id="`${prefix}-state`" v-model="model.state"><option value="">Selecione</option><option v-for="state in states" :key="state">{{ state }}</option></select></div>
    <div class="form-field span-2"><label :for="`${prefix}-street`">Logradouro</label><input :id="`${prefix}-street`" v-model="model.street" maxlength="150" /></div>
    <div class="form-field"><label :for="`${prefix}-number`">Número</label><input :id="`${prefix}-number`" v-model="model.number" maxlength="20" placeholder="Número ou S/N" /></div>
    <div class="form-field"><label :for="`${prefix}-complement`">Complemento</label><input :id="`${prefix}-complement`" v-model="model.complement" maxlength="120" /></div>
    <div class="form-field"><label :for="`${prefix}-neighborhood`">Bairro</label><input :id="`${prefix}-neighborhood`" v-model="model.neighborhood" maxlength="100" /></div>
    <div class="form-field"><label :for="`${prefix}-city`">Município</label><input :id="`${prefix}-city`" v-model="model.city" maxlength="100" /></div>
    <div class="form-field span-2"><label :for="`${prefix}-ibge`">Código IBGE do município</label><input :id="`${prefix}-ibge`" v-model="model.municipality_code" inputmode="numeric" maxlength="7" placeholder="7 dígitos" /></div>
  </div>
</template>
