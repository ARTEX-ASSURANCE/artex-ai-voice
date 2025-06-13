import datetime
from typing import List, Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    ForeignKey,
    Text,
    DECIMAL,
    DateTime,
    func,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import TINYINT  # MySQL-specific small integer type
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs

class Base(AsyncAttrs, DeclarativeBase):
    pass

# Adherents Table
class Adherent(Base):
    __tablename__ = "adherents"

    id_adherent: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nom: Mapped[str] = mapped_column(String(255))
    prenom: Mapped[str] = mapped_column(String(255))
    date_naissance: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    adresse: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    code_postal: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    ville: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    telephone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    numero_securite_sociale: Mapped[Optional[str]] = mapped_column(
        String(15), unique=True, index=True, nullable=True
    )
    date_adhesion_mutuelle: Mapped[Optional[datetime.date]] = mapped_column(
        Date,
        server_default=func.current_date(),
        nullable=True,
    )

    # Relationships
    contrats_adherent_principal: Mapped[List["Contrat"]] = relationship(
        back_populates="adherent_principal"
    )
    sinistres_artex: Mapped[List["SinistreArtex"]] = relationship(
        back_populates="adherent"
    )

# Association Table: formules_garanties
formules_garanties_association = Table(
    "formules_garanties",
    Base.metadata,
    Column(
        "id_formule",
        Integer,
        ForeignKey("formules.id_formule", name="fk_formules_garanties_formule_id"),
        primary_key=True,
    ),
    Column(
        "id_garantie",
        Integer,
        ForeignKey("garanties.id_garantie", name="fk_formules_garanties_garantie_id"),
        primary_key=True,
    ),
    Column("plafond_remboursement", DECIMAL(10, 2), nullable=True),
    Column("taux_remboursement_pourcentage", TINYINT, nullable=True),
    Column("franchise", DECIMAL(10, 2), nullable=True),
    Column("conditions_specifiques", Text, nullable=True),
)

# Garanties Table
class Garantie(Base):
    __tablename__ = "garanties"

    id_garantie: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    libelle: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    formules: Mapped[List["Formule"]] = relationship(
        secondary=formules_garanties_association,
        back_populates="garanties",
    )

# Formules Table
class Formule(Base):
    __tablename__ = "formules"

    id_formule: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nom_formule: Mapped[str] = mapped_column(String(100), unique=True)
    description_formule: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tarif_base_mensuel: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 2))

    contrats: Mapped[List["Contrat"]] = relationship(back_populates="formule")
    garanties: Mapped[List["Garantie"]] = relationship(
        secondary=formules_garanties_association,
        back_populates="formules",
    )

# Contrats Table
class Contrat(Base):
    __tablename__ = "contrats"

    id_contrat: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_adherent_principal: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("adherents.id_adherent", name="fk_contrat_adherent_id"),
    )
    numero_contrat: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    date_debut_contrat: Mapped[datetime.date] = mapped_column(Date)
    date_fin_contrat: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    type_contrat: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    statut_contrat: Mapped[str] = mapped_column(
        String(50), server_default="Actif", default="Actif"
    )
    id_formule: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("formules.id_formule", name="fk_contrat_formule_id"),
        nullable=True,
    )

    adherent_principal: Mapped["Adherent"] = relationship(
        back_populates="contrats_adherent_principal"
    )
    formule: Mapped[Optional["Formule"]] = relationship(back_populates="contrats")
    sinistres_artex: Mapped[List["SinistreArtex"]] = relationship(back_populates="contrat")

# SinistreArtex Table
class SinistreArtex(Base):
    __tablename__ = "sinistres_artex"

    id_sinistre_artex: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_contrat: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("contrats.id_contrat", name="fk_sinistre_artex_contrat_id"),
    )
    id_adherent: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("adherents.id_adherent", name="fk_sinistre_artex_adherent_id"),
    )
    type_sinistre: Mapped[str] = mapped_column(
        String(255), comment="Type of claim as categorized by Artex or user"
    )
    description_sinistre: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    date_declaration_agent: Mapped[datetime.date] = mapped_column(
        Date, server_default=func.current_date()
    )
    statut_sinistre_artex: Mapped[str] = mapped_column(
        String(100),
        server_default="Information enregistrée par agent",
        default="Information enregistrée par agent",
    )
    date_survenance: Mapped[Optional[datetime.date]] = mapped_column(
        Date, nullable=True, comment="Date of incident, if provided by user"
    )

    contrat: Mapped["Contrat"] = relationship(back_populates="sinistres_artex")
    adherent: Mapped["Adherent"] = relationship(back_populates="sinistres_artex")

# Ensure metadata is available for Alembic
# Base.metadata.create_all(engine) can be used in sync contexts if needed
