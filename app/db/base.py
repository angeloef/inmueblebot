"""
Base de SQLAlchemy para todos los modelos.
Define la base declarativa y metadatos comunes.
"""
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData
from sqlalchemy.sql import func

# MetaData recomendado for SQLAlchemy 2.0
# Simplified naming convention to avoid conflicts
metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        # Include the local column so a table with two FKs to the same target gets
        # distinct names (e.g. contracts.tenant_id (renter), contracts.owner_id and
        # contracts.org_id (agency) all reference different tables but must not collide).
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


class Base(DeclarativeBase):
    """
    Base declarativa para todos los modelos ORM.
    Todos los modelos deben heredar de esta clase.
    """
    metadata = metadata