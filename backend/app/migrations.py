import json
import logging

from sqlalchemy import inspect

from app.database import Base

logger = logging.getLogger(__name__)


def _default_value(column):
    default = column.default
    if default is None:
        return None
    if default.is_scalar:
        return default.arg
    if default.is_callable:
        try:
            return default.arg(None)
        except Exception:
            return None
    return None


def _literal(value, dialect_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        if dialect_name == "sqlite":
            return "1" if value else "0"
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, dict | list):
        value = json.dumps(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def migrate_schema(connection) -> None:
    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())
    dialect = connection.dialect
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        present = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            column_type = column.type.compile(dialect=dialect)
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}'
            literal = _literal(_default_value(column), dialect.name)
            if literal is not None:
                ddl += f" DEFAULT {literal}"
            connection.exec_driver_sql(ddl)
            logger.info("Schema upgrade: added %s.%s", table.name, column.name)
