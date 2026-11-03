<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { api, apiError } from '../services/api'
const props = defineProps({modelValue:{type:Object,required:true}, transport:Boolean, label:String})
const emit = defineEmits(['update:modelValue','lookup-state'])
const loading=ref(false), error=ref('')
let request=0, disposed=false
function change(key,value) {
  if (key === 'cep' || key === 'address') { request++; loading.value=false; emit('lookup-state',false) }
  error.value='';emit('update:modelValue',{...props.modelValue,[key]:value})
}
async function lookup() {
  if (!/^\d{8}$/.test(props.modelValue.cep)) {error.value='Informe um CEP com oito dígitos.';return}
  const id=++request, cep=props.modelValue.cep
  loading.value=true;error.value='';emit('lookup-state',true)
  try {
    const {data}=await api.get('/rental-quotes/lookup-address/',{params:{cep}})
    if(disposed||id!==request||cep!==props.modelValue.cep)return
    emit('update:modelValue',{...props.modelValue,cep:data.cep,address:[data.street,data.neighborhood,`${data.city}/${data.state}`].filter(Boolean).join(', ')})
  } catch(event) {if(id===request&&!disposed)error.value=apiError(event)}
  finally {if(id===request&&!disposed){loading.value=false;emit('lookup-state',false)}}
}
onBeforeUnmount(()=>{disposed=true;request++;emit('lookup-state',false)})
</script>
<template>
  <div class="item-destination-fields form-grid">
    <template v-if="transport">
      <div class="form-field"><label>{{ label }} · CEP<span class="required-mark" aria-hidden="true"> *</span></label><div class="address-lookup-row"><AppInput mask="cep" :model-value="modelValue.cep" required placeholder="00000-000" @update:model-value="change('cep',$event)"/><button type="button" class="btn secondary" :disabled="loading" @click="lookup">{{loading?'Buscando…':'Buscar CEP'}}</button></div></div>
      <div class="form-field"><label>Número<span class="required-mark" aria-hidden="true"> *</span></label><input :value="modelValue.number" required maxlength="20" placeholder="Ex.: 120 ou S/N" @input="change('number',$event.target.value)"/></div>
      <div class="form-field span-2"><label>Logradouro, bairro e cidade<span class="required-mark" aria-hidden="true"> *</span></label><input :value="modelValue.address" required maxlength="230" placeholder="Preencha pelo CEP ou informe o logradouro" @input="change('address',$event.target.value)"/></div>
      <div class="form-field"><label>Complemento</label><input :value="modelValue.complement" maxlength="120" placeholder="Bloco, portão ou ponto de referência" @input="change('complement',$event.target.value)"/></div>
    </template>
    <div class="form-field"><label>Horário combinado (opcional)</label><AppDateTime :model-value="modelValue.time" type="time" @update:model-value="change('time',$event)"/></div>
    <div v-if="error" class="error-message span-2" role="alert">{{error}}</div>
  </div>
</template>
