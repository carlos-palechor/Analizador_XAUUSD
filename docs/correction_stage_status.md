# Estado de correcciones antes del cerebro de sesiones

Este documento registra el avance real de la etapa de estabilización. No sustituye
las pruebas: cada punto solo pasa a completado cuando tenga verificación automatizada
y, cuando corresponda, comprobación en PostgreSQL.

| # | Punto | Estado | Evidencia o pendiente |
| --- | --- | --- | --- |
| 1 | Snapshots con velas exactas | Completado | Migración `0004` aplicada. Snapshot real con 17.513 velas, huella SHA-256 y fingerprint 2 verificados en PostgreSQL. |
| 2 | Cerebro independiente de CSV | Completado | El análisis multitemporal completo desde CSV y PostgreSQL fue equivalente en la validación real. |
| 3 | Auditoría multitemporal | Completado | Se confirmaron 4 estructuras, 4 eventos estructurales, explicaciones, niveles, objetivos y estado `CONFIRMED`. |
| 4 | Consolidaciones auditables | Completado | Migración `0005` aplicada y 115 consolidaciones auditables persistidas en PostgreSQL. |
| 5 | Reproducción sin información futura | Completado | Replay incremental, velas cerradas y pivotes confirmados solo al existir velas posteriores. |
| 6 | Calidad y cobertura histórica | Completado | El análisis usa velas validadas y registra cobertura suficiente, insuficiente o huecos para revisión de sesiones. |
| 7 | Calendario de sesiones | Completado | Snapshot MT5 renovable y períodos históricos de vigencia con desfase propio. |
| 8 | Alembic seguro | Completado | Alembic lee `XAU_DATABASE_URL`, no conserva claves reales y existe configuración de ejemplo sin secretos. |
| 9 | Replay para volúmenes grandes | Completado | Eliminada repetición de escaneo por paso y comprobada equivalencia con el recorrido de referencia. |
| 10 | Modularidad técnica | Completado | Pivotes, tipos de dominio y contrato de vela están separados en módulos reutilizables con regresión aprobada. |
| 11 | Documentación | Completado | README actualizado con instalación, migraciones, importación, auditoría, seguridad y límites. |
| 12 | Validación integral | Completado | Migraciones aplicadas, CSV/PostgreSQL equivalentes, snapshot exacto y resultados auditables persistidos. |

## Regla de cierre

No se iniciará el cerebro de sesiones hasta que los doce puntos estén marcados como
**Completado** y las pruebas de regresión e integración estén aprobadas.
