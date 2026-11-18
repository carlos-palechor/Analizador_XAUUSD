# Analizador Adaptativo Multimercado

Proyecto de análisis técnico auditable para comenzar con `XAUUSDm` de Exness.
No envía órdenes ni opera automáticamente. Conserva datos del mercado y explica qué
estructura técnica detectó con cada conjunto de velas.

## Componentes actuales

- Adaptador de MetaTrader 5 para descubrir símbolo, velas y sesiones.
- Históricos CSV conservados como respaldo verificable.
- Repositorio común de datos para CSV y PostgreSQL.
- PostgreSQL con migraciones Alembic, importaciones trazables y datos versionados.
- Cerebro técnico H4/H1/M15/M5: estructura, BOS, POI, confirmación, niveles,
  objetivos y consolidaciones.
- Reproductor histórico cronológico que usa exclusivamente velas cerradas.
- Auditoría: ejecución, parámetros, snapshot de velas y resultados técnicos.

Pendiente antes del cerebro de sesiones: completar las correcciones de
[`docs/correction_stage_status.md`](docs/correction_stage_status.md).

## Seguridad y configuración

Nunca escriba la contraseña de PostgreSQL en código, CSV, reportes ni `alembic.ini`.
Defina la conexión únicamente en la sesión actual de PowerShell:

```powershell
$env:XAU_DATABASE_URL = "postgresql+psycopg://USUARIO:CONTRASENA@localhost:5432/xau_analyzer"
```

No comparta ese comando si incluye una contraseña real. Si una contraseña se expone,
cámbiela antes de continuar.
El archivo [`.env.example`](.env.example) muestra la forma de la variable sin secretos;
`.env` está excluido del control de versiones.

## Instalación

```powershell
python -m pip install -e ".[postgres]"
$env:PYTHONPATH = "src"
```

MetaTrader 5 debe estar instalado y conectado para comandos que consulten datos vivos.

## Preparar la base de datos

Con `XAU_DATABASE_URL` definido, aplique las migraciones:

```powershell
python -m alembic upgrade head
python -m alembic current
```

El segundo comando debe mostrar la revisión más reciente. Las migraciones crean los
esquemas `market`, `technical`, `analysis` y `system`; no borran los CSV.

## Importar y verificar históricos

Los archivos deben estar dentro de `data/raw` en sus carpetas por temporalidad.

```powershell
python -m xau_collector import-history --root data/raw
python -m xau_collector verify-history-import
```

La importación registra hash del archivo, filas aceptadas, duplicadas o rechazadas.
Repetir el mismo archivo no duplica velas en PostgreSQL.

## Comparar CSV y PostgreSQL

Antes de confiar en PostgreSQL, compare el análisis completo por el mismo corte UTC:

```powershell
python -m xau_collector compare-multitimeframe-sources --root data/raw --at 2026-10-30T20:00
```

Debe devolver equivalencia para H4, H1, M15 y M5. La fecha `--at` es un corte
histórico: el análisis no puede leer velas posteriores.

## Persistir y verificar un análisis técnico

```powershell
python -m xau_collector persist-history-analysis --root data/raw --at 2026-10-30T20:00
python -m xau_collector verify-technical-analysis --analysis-run-id ID_DEVUELTO
```

Cada ejecución queda asociada a versión de algoritmo, parámetros, snapshot de datos,
estructuras, eventos, niveles, objetivos y explicaciones. Los resultados anteriores
no se sobrescriben.

## Validación final de PostgreSQL

Después de aplicar las migraciones, este único comando compara CSV con PostgreSQL,
persiste un análisis nuevo y verifica su snapshot y resultados auditables:

```powershell
python -m xau_collector validate-postgres-stage --root data/raw --at 2026-10-30T20:00
```

El resultado debe indicar `equivalent: true`, una huella de snapshot con velas y los
conteos de estructuras, eventos, consolidaciones, niveles, objetivos y explicaciones.

## Pruebas

```powershell
python -m ruff check src tests
python -m pytest
```

La suite cubre contratos de datos, validación de velas, calendario, reproducción sin
información futura, equivalencia de fuentes y regresión de estructura técnica.

## Límites actuales

- No hay operaciones automáticas ni gestión de dinero real.
- Las velas en formación se podrán monitorear en vivo, pero las confirmaciones que
  requieren cierre solo se guardarán como confirmadas tras cerrar su vela.
- Un cambio histórico de horario del bróker requiere exportar y registrar el período
  efectivo correspondiente desde MT5.
- CSV sigue siendo respaldo hasta que el usuario autorice explícitamente eliminarlo.
