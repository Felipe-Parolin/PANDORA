# Rastreabilidade da modelagem de padrões

Fonte comparada: `ARTEFATOS DO PROJETO/LINGUAGEM DE PROGRAMAÇÃO III/MODELAGEM DOS PADRÕES (PRELIMINAR).pdf`, versão atual de `origin/main`.

Os nomes do documento estão em português e os nomes de código seguem a convenção Python em inglês. A tabela abaixo registra a correspondência.

| Padrão | Elemento da modelagem | Implementação | Uso real |
|---|---|---|---|
| Singleton | `ConfiguracaoSistema` | `core.patterns.AISettings` | `AIService` recebe a mesma configuração imutável por processo através de `get_instance()` |
| Builder | `AberturaOSBuilder` | `ServiceOrderBuilderContract` | contrato das etapas de criação |
| Builder | `OrdemServicoBuilder` | `ServiceOrderBuilder` | monta e valida os dados antes de persistir a OS |
| Builder | `DiretorAberturaOS` | `ServiceOrderOpeningDirector` | usado pelo `ServiceOrderSerializer.create()` |
| Factory Method | `CriadorProcessador` | `ReportProcessorCreator` | define o fluxo comum `process()` e o factory method `create_processor()` |
| Factory Method | `CriadorTexto` / `CriadorAudio` | `TextReportProcessorCreator` / `AudioReportProcessorCreator` | criam produtos que realizam `ReportProcessor` |
| Abstract Factory | `FabricaManutencao` | `MaintenanceFamilyFactory` | contrato para criar checklist e roteiro compatíveis |
| Abstract Factory | `FabricaPreventiva` / `FabricaCorretiva` | `PreventiveMaintenanceFactory` / `CorrectiveMaintenanceFactory` | criam as famílias concretas |
| Abstract Factory | `ServicoPlanejamentoManutencao` | `MaintenancePlanningService` | consome somente as interfaces dos produtos |

## Resultado da auditoria

- O Singleton já representava corretamente a unicidade por processo, mas agora possui bloqueio explícito para inicialização concorrente e um consumidor real.
- O Builder já montava a OS em etapas; foi incluído o contrato abstrato e o Director descrito no diagrama.
- A implementação anterior de relatos era uma Simple Factory. Agora os creators concretos implementam Factory Method, preservando a fachada compatível.
- A implementação anterior de kits era uma Simple Factory de dados. Agora existem interfaces de produtos, produtos concretos, fábricas de famílias e o serviço cliente previstos pelo Abstract Factory.
- Os padrões continuam fora das entidades de domínio e não duplicam `ServiceOrder`, como recomenda o documento.

## Verificação

Os testes automatizados cobrem unicidade do Singleton, reinicialização e direção do Builder, seleção dos creators e compatibilidade das famílias do Abstract Factory.
