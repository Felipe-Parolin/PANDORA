import test from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { formatTaxId, formatPhone, formatPlate, formatCep, formatNumber, formatPercent, formatDate, rentalStatusLabel, transportStatusLabel } from '../src/services/formatters.js'
import { matchesSearch } from '../src/services/listFilters.js'

test('exibição: documentos, telefone, CEP e placa usam máscaras sem alterar o valor original',()=>{
  const customer={document:'12345678909',phone:'19999991111'}
  assert.equal(formatTaxId(customer.document),'123.456.789-09')
  assert.equal(formatTaxId('11222333000181'),'11.222.333/0001-81')
  assert.equal(formatTaxId('AB123456000195','PJ'),'AB.123.456/0001-95')
  assert.equal(formatPhone(customer.phone),'(19) 99999-1111')
  assert.equal(formatPhone('(19) 3333-4444'),'(19) 3333-4444')
  assert.equal(formatPlate('pdr1a23'),'PDR-1A23')
  assert.equal(formatPlate('PDR-1234'),'PDR-1234')
  assert.equal(formatCep('13614032'),'13614-032')
  assert.deepEqual(customer,{document:'12345678909',phone:'19999991111'})
  assert.equal(formatTaxId('123'),'123')
})

test('exibição: números, percentuais e ausências seguem o padrão brasileiro',()=>{
  assert.equal(formatNumber('1500.50'),'1.500,5')
  assert.equal(formatPercent('0.50'),'0,5%')
  assert.equal(formatPercent('1.00'),'1%')
  assert.equal(formatNumber(0),'0')
  for(const value of [null,undefined,'']){
    for(const formatter of [formatTaxId,formatPhone,formatPlate,formatCep,formatNumber,formatPercent,formatDate])assert.equal(formatter(value),'—')
  }
  assert.equal(formatNumber('inválido'),'—');assert.equal(formatPercent('inválido'),'—')
})

test('exibição: datas sem horário preservam o dia em diferentes fusos e instantes respeitam Brasília',()=>{
  const path=new URL('../src/services/formatters.js',import.meta.url).href
  for(const timezone of ['UTC','America/Sao_Paulo','Pacific/Auckland']){
    const result=spawnSync(process.execPath,['--input-type=module','-e',`import {formatDate} from ${JSON.stringify(path)};console.log(formatDate('2026-11-02'))`],{env:{...process.env,TZ:timezone},encoding:'utf8'})
    assert.equal(result.status,0,result.stderr);assert.equal(result.stdout.trim(),'02/11/2026')
  }
  const result=spawnSync(process.execPath,['--input-type=module','-e',`import {formatDate} from ${JSON.stringify(path)};console.log(formatDate('2026-11-03T00:30:00Z'))`],{env:{...process.env,TZ:'America/Sao_Paulo'},encoding:'utf8'})
  assert.equal(result.status,0,result.stderr);assert.equal(result.stdout.trim(),'02/11/2026')
  assert.equal(formatDate('inválido'),'—')
})

test('busca: encontra os mesmos cadastros com ou sem a pontuação da máscara',()=>{
  assert.ok(matchesSearch('12345678909','Cliente · 123.456.789-09'))
  assert.ok(matchesSearch('11.222.333/0001-81','11222333000181'))
  assert.ok(matchesSearch('(19) 99999-1111','19999991111'))
  assert.ok(matchesSearch('PDR-1A23','PDR1A23'))
  assert.equal(matchesSearch('...','Cliente sem documento'),false)
  assert.equal(matchesSearch('99999999999','123.456.789-09'),false)
})

test('status: contrato e transporte têm rótulos próprios em português',()=>{
  assert.equal(rentalStatusLabel('ACTIVE'),'Em locação')
  assert.equal(rentalStatusLabel('COMPLETED'),'Concluído')
  assert.equal(transportStatusLabel('IN_TRANSIT'),'Em transporte')
  assert.equal(transportStatusLabel('PLANNED'),'Planejado')
})
