# Preparación local de PostgreSQL

## 1. Instalar el servidor

Instale PostgreSQL 17 para Windows. Durante el instalador elija una contraseña
propia para el usuario administrador `postgres`; no la escriba en archivos del
proyecto ni la comparta. Mantenga el puerto local `5432` salvo que ya esté ocupado.

## 2. Crear usuario y base de desarrollo

Abra **SQL Shell (psql)** y ejecute, sustituyendo una contraseña privada:

```sql
CREATE ROLE xau_app LOGIN PASSWORD 'CONTRASENA_PRIVADA' NOSUPERUSER;
CREATE DATABASE xau_analyzer OWNER xau_app;
```

La base será exclusivamente local durante desarrollo. No se importarán CSV todavía.

## 3. Ejecutar migración

En PowerShell, desde la raíz del proyecto:

```powershell
$env:XAU_DATABASE_URL = "postgresql+psycopg://xau_app:CONTRASENA_PRIVADA@localhost:5432/xau_analyzer"
python -m alembic -x database_url=$env:XAU_DATABASE_URL upgrade head
```

La migración `0001_market_and_audit` crea los esquemas `market`, `technical`,
`analysis` y `system`, pero todavía no importa velas ni crea órdenes.

## 4. Verificar

```powershell
python -m alembic current
```

El resultado debe mostrar `0001_market_and_audit`.

## Seguridad

- La URL y contraseña solo se usan en la sesión actual de PowerShell.
- Nunca suba contraseñas ni `config.toml` a un repositorio.
- Los históricos CSV se mantienen intactos hasta autorización explícita para borrarlos.
