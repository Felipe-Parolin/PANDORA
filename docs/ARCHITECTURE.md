# Arquitetura inicial

## Visão de contexto

```text
Usuário interno
      │ HTTPS + JWT
      ▼
Vue 3 / Vite ───────► Django REST API ───────► PostgreSQL
                              │
                              ├── armazenamento de arquivos (MEDIA_ROOT no MVP)
                              └── serviço de IA/transcrição (integração futura e opcional)
```

A locação e a manutenção não dependem da disponibilidade de IA. Uma futura integração deve consultar apenas conteúdo autorizado, indicar fontes e manter a decisão final com o técnico.

As movimentações de entrega e devolução são centralizadas em `rentals/fulfillment.py`: tanto o balcão quanto a conclusão integrada do transporte reutilizam as mesmas validações, permissões, auditoria e transações. A conclusão da viagem com avanço da locação é atômica; uma falha não deixa apenas metade do fluxo confirmada. A composição estimada do frete fica registrada no orçamento para preservar os valores históricos.

O painel de transporte usa como referências de organização a fila de entregas/coletas do [Booqable](https://booqable.com/features/) e as confirmações de movimentação do [Odoo Rental](https://www.odoo.com/documentation/19.0/applications/sales/rental/rental_orders/pickup_return.html), adaptadas às liberações técnicas e ACL do PANDORA. Não há integração com esses produtos.

## Módulos de domínio

| Módulo | Responsabilidade |
|---|---|
| `accounts` | usuário interno, grupos ACL configuráveis, JWT e permissões |
| `customers` | cliente PF/PJ, documento, contato e situação |
| `assets` | categoria, equipamento, QR token e acervo de mídias |
| `maintenance` | plano, alertas, ordem de serviço, atividades e liberação |
| `rentals` | orçamento, reserva, inspeções, entrega, prorrogação, devolução e disponibilidade |
| `logistics` | frota, viagem de entrega e coleta opcional por locação |
| `fiscal` | emitente configurável e dados complementares para preparar futura emissão, sem transmissão |
| `core` | dashboard, auditoria e configuração compartilhada |

## Regras críticas implementadas

1. Um cliente deve possuir CPF ou CNPJ compatível com seu tipo.
2. Número de série, código interno e token de QR Code são únicos.
3. Uma mídia pertence a exatamente um equipamento, OS, orçamento ou inspeção.
4. Um orçamento aprovado bloqueia sobreposições do mesmo equipamento.
5. OS aberta ou manutenção crítica vencida impede a aprovação de nova reserva.
6. A liberação técnica exige OS concluída, teste final e técnico responsável.
7. Valores do orçamento são recalculados no backend; o frontend não é a fonte de verdade.
8. A mesma permissão ACL controla a rota da API e a ação exibida na interface.
9. Exclusões com vínculos protegidos retornam conflito em vez de remover histórico operacional.
10. O QR Code aponta para a consulta autenticada do equipamento e pode ser baixado em PNG.
11. Um chamado abandonado exige justificativa, mantém o equipamento bloqueado e fica disponível para redistribuição.
12. A seleção de locação antecipa a mesma regra de disponibilidade reaplicada na aprovação.
13. Cada equipamento reservado abre uma OS de pré-locação na Manutenção, vinculada à inspeção. A própria OS pendente não bloqueia sua reserva; outras OS abertas continuam bloqueando.
14. A entrega exige avaliação pré-locação **operante** e OS liberada para todos os itens. Equipamento **inoperante** mantém a OS aberta e o uso bloqueado.
15. A prorrogação repete a verificação de disponibilidade e preserva o histórico de datas e condições.
16. A devolução mantém o equipamento indisponível até a inspeção final; avarias geram OS pós-locação.
17. Planos podem vencer por data ou horas de uso, com faixas de aviso configuráveis.
18. A opção de transporte é definida no orçamento; o preço do frete entra no total recalculado no servidor.
19. A viagem de entrega só inicia após inspeção e OS pré-locação liberadas, e a entrega só é registrada após a viagem concluída.
20. Quando há coleta contratada, a devolução só é registrada após a viagem de retorno concluída. Veículos em viagem não podem ser atribuídos a outra viagem.
21. O intervalo operacional de cada equipamento amplia a janela de conflito em ambos os lados da reserva, inclusive na prorrogação.
22. A procura não atendida só é registrada por ação explícita, com cliente e período indisponível, e não pela mera visualização da disponibilidade.
23. Orçamento e comprovantes preservam snapshots versionados; o PDF é gerado a partir do snapshot e verificado por hash. Um orçamento com documentos não pode ser excluído.
24. A sugestão de compra é uma heurística explicável baseada em 180 dias de solicitações, ocupação, procura não atendida e custo de manutenção em relação ao preço de aquisição.
25. A preparação fiscal mantém os dados do emitente configuráveis e vazios por padrão. Conferência e exportação não autorizam emissão nem calculam tributos; o valor do bem não é confundido com a diária.

## Ciclo da locação

```text
Rascunho/Enviado → Reservado → Inspeção pré-locação → [Transporte de entrega] → Em locação → [Coleta] → Devolvido/em inspeção → Concluído
        │              │
        └──────────────┴──→ Cancelado (antes da entrega)
```

Cada transição operacional registra usuário, data, condições e `AuditLog`. As avaliações são individuais por equipamento; a decisão operante/inoperante é adaptada aos campos históricos de inspeção sem apagar registros antigos.

## Padrões criacionais da modelagem

- **Singleton:** `core.patterns.AISettings` usa cache de instância para configuração imutável por processo. Dados de usuário não são guardados nela.
- **Builder:** `maintenance.patterns.ServiceOrderBuilder` monta a abertura da OS por etapas e reinicia o estado após cada construção.
- **Factory Method:** `ReportProcessorFactory` seleciona processadores de texto e, futuramente, áudio/transcrição.
- **Abstract Factory:** `MaintenanceKitFactory` entrega checklist e roteiro compatíveis com manutenção preventiva ou corretiva.

Esses padrões ficam no serviço de aplicação, sem duplicar as entidades de domínio.

## Padrão estrutural da avaliação

`rentals.adapters.InspectionDecisionAdapter` traduz a decisão operacional simples (`OPERATING`/`BROKEN`) para os campos persistidos de condição e resultado da inspeção. O serializer usa o adaptador tanto na escrita quanto na leitura (`operational_status`). Isso permite retirar o checklist do fluxo atual e manter a compatibilidade com inspeções históricas, sem migração destrutiva. O dashboard usa `core.recommendations` para gerar uma sugestão explicável de compra a partir de solicitações e disponibilidade; não chama um modelo externo de IA.

A correspondência detalhada entre os diagramas acadêmicos e as classes Python está em [Rastreabilidade dos padrões](PATTERN_TRACEABILITY.md).

## Evolução recomendada

- trocar `MEDIA_ROOT` por armazenamento de objetos com verificação antimalware;
- adicionar trilha automática para CRUD genérico por middleware, complementando os eventos de locação;
- implementar aceite eletrônico assinado dos PDFs comerciais e validação jurídica do fluxo;
- adotar tarefas assíncronas para relatórios, transcrição e IA;
- incluir OpenAPI/Swagger, testes de integração concorrente e CI no GitHub Actions.
