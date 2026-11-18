# Diseño técnico de persistencia v1

## Principios

Las velas originales son hechos inmutables versionados. Estructuras, niveles, POI,
consolidaciones y objetivos son interpretaciones vinculadas a una ejecución; nunca
verdades permanentes del mercado. Un análisis no se sobrescribe.

## Esquemas

| Esquema | Responsabilidad |
| --- | --- |
| `market` | fuentes, instrumentos, velas cerradas, ticks bajo política, sesiones y cierres |
| `technical` | estructuras, eventos BOS/CHoCH, POI, consolidaciones, niveles y objetivos |
| `analysis` | ejecuciones, snapshots, evidencias, explicaciones y decisiones |
| `system` | versiones, parámetros, lotes de importación y auditoría |

## Identidad y tiempo

Una vela se identifica por `data_source_id`, `symbol_id`, `timeframe`, `open_time_utc`
y `revision`. Sus tiempos son independientes: `open_time_utc`, `close_time_utc`,
`received_at_utc` y `analyzed_at_utc`. Todas las fechas se guardan UTC.

## Tablas mínimas iniciales

`market.data_sources`, `market.symbols`, `market.market_bars`, `market.trading_sessions`,
`market.market_closures`, `system.algorithm_versions`, `system.analysis_parameters`,
`system.import_batches`, `analysis.technical_analysis_runs`, `analysis.analysis_evidence`.

La segunda migración añadirá resultados técnicos: `technical.market_structures`,
`technical.structural_breaks`, `technical.points_of_interest`,
`technical.consolidations`, `technical.technical_levels` y
`technical.structural_targets`.

## Correcciones

Una corrección no actualiza silenciosamente una vela: inserta una nueva revisión,
registra procedencia y deja la anterior no vigente. Los análisis conservan el
`source_snapshot_id` utilizado, por lo que se puede localizar cuáles dependieron de
una revisión anterior.

## Ejecución auditable

Cada ejecución usa `analysis_run_id`, `analyzed_at_utc`, `data_cutoff_utc`,
`algorithm_version_id`, `parameters_hash`, `source_snapshot_id` y estado
`PROVISIONAL`, `CONFIRMED`, `INVALIDATED` o `FINALIZED`.

## Importación CSV

Cada lote guarda archivo, hash SHA-256, fuente, símbolo, temporalidad, periodo,
filas leídas/aceptadas/duplicadas/rechazadas, resultado de calidad, importador y
fecha. La importación es idempotente. Los CSV se conservan hasta autorización del usuario.

## Calendarios

`market.trading_sessions` describe cuándo cotiza/negocia el instrumento.
`market.market_closures` registra fines de semana, pausa diaria, feriados,
mantenimiento o cambios documentados. El calendario de procesamiento del software
es otro componente: determina cuándo ejecutar confirmaciones, no cuándo el mercado
está abierto.

## Pruebas de aceptación

- Reimportar el mismo CSV no duplica velas.
- Una importación interrumpida puede repetirse.
- OHLC y UTC se conservan sin pérdida.
- CSV y PostgreSQL dan el mismo resultado técnico con el mismo corte.
- Un replay no entrega velas posteriores al corte.
- Pausas de mercado no se confunden con fallos de adquisición.
