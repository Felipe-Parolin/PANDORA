import assert from 'node:assert/strict'
import test from 'node:test'
import { splitAddress, fullAddress, effectiveLocation, destinationGroups } from '../src/services/rentalDestinations.js'
import { mountView, flush } from './helpers/mountView.mjs'

test('endereços antigos separam somente o número e preservam rua, bairro e cidade',()=>{
  assert.deepEqual(splitAddress('Rua 7 de setembro, 120, Centro, Leme/SP'),{address:'Rua 7 de setembro, Centro, Leme/SP',number:'120'})
  assert.equal(fullAddress('Rua 7 de setembro, 120, Centro, Leme/SP','200'),'Rua 7 de setembro, 200, Centro, Leme/SP')
  assert.deepEqual(splitAddress('Rua 7 de setembro, Centro, Leme/SP'),{address:'Rua 7 de setembro, Centro, Leme/SP',number:''})
})

test('grupo de endereço mantém todos os horários para a API separar as viagens',()=>{
  const form={delivery_address:'Rua de teste, Bairro, Leme/SP',delivery_number:'100',delivery_cep:'13614032',requested_delivery_at:'2026-11-02T09:00'}
  const items=[{equipment_id:1},{equipment_id:2,delivery_location:{address:form.delivery_address,number:'200',cep:'13614032',time:'08:00'}},{equipment_id:3,delivery_location:{address:form.delivery_address,number:'200',cep:'13614032',time:'11:00'}}]
  const groups=destinationGroups(items,form,'delivery')
  assert.equal(groups.length,2);assert.deepEqual(groups[1].items.map(item=>item.time),['08:00','11:00'])
  assert.equal(effectiveLocation(items[1],form,'delivery',false).number,'100')
})

test('frete soma destinos, envia número e horários separados e não pede confirmação aproximada',async t=>{
  const requests=[],writes=[]
  const {state}=mountView(t,'RentalsView',{api:{get:async(url,config)=>{
    if(url.endsWith('/lookup-address/')) {requests.push(config.params);return {data:{estimate:{fee:config.params.number==='100'?'25.00':'50.00',trip_count:config.params.number==='100'?1:2,approximate_destination:true}}}}
    return {data:{available:[1,2,3].map(id=>({equipment:{id}})),blocked:[],next_page:null,results:[]}}
  },patch:async(url,payload)=>{writes.push(payload);return {data:{}}}}})
  await flush()
  state.open({id:10,customer:1,status:'DRAFT',discount:'0',discount_percent:'0',start_date:'2026-11-02',end_date:'2026-11-03',delivery_address:'Rua de teste, Bairro, Leme/SP',delivery_number:'100',delivery_cep:'13614032',delivery_transport_required:true,return_transport_required:false,subtotal:'300',transport_fee:'0',estimated_transport_fee:'0',conditions:'Teste',items:[1,2,3].map(equipment=>({equipment,daily_rate:'100',start_date:'2026-11-02',end_date:'2026-11-02'}))})
  await flush();state.separateDestinations=true
  state.form.items[1].delivery_location={address:state.form.delivery_address,number:'200',cep:'13614032',time:'08:00',complement:''}
  state.form.items[2].delivery_location={address:state.form.delivery_address,number:'200',cep:'13614032',time:'11:00',complement:''}
  await state.calculateFreight('delivery')
  assert.equal(requests.length,2);assert.equal(state.form.transport_fee,75)
  assert.ok(requests.every(params=>params.allow_approximate===true))
  assert.deepEqual(JSON.parse(requests[1].periods).map(item=>item.time),['08:00','11:00'])
  assert.equal(state.addressLookup.delivery.result.estimate.approximate_destination,true)
  state.selectionChecked=true;state.selectionLoading=false
  await state.save();assert.equal(writes.length,1,state.error)
  assert.equal(writes[0].delivery_number,'100')
  assert.equal(writes[0].items[1].delivery_location.number,'200')
  assert.equal(writes[0].items[2].delivery_location.time,'11:00')
})
