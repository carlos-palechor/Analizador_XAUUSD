from logging.config import fileConfig
import os

from alembic import context

config = context.config
database_url = context.get_x_argument(as_dictionary=True).get("database_url")
database_url = database_url or os.environ.get("XAU_DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)
elif not context.is_offline_mode():
    raise RuntimeError("Falta XAU_DATABASE_URL para conectar Alembic con PostgreSQL")
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Ejecuta migraciones en modo SQL o conectado, sin modelos ORM ocultos.
def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


# Ejecuta migraciones contra la URL explícitamente configurada para el entorno.
def run_migrations_online() -> None:
    from sqlalchemy import engine_from_config, pool

    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
