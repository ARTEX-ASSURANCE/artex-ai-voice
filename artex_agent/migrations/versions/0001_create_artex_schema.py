"""create arthex schema

Revision ID: 0001_arthex_initial_schema
Revises:
Create Date: 2024-08-02 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
# from sqlalchemy.dialects import mysql # For mysql specific types if needed

# revision identifiers, used by Alembic.
revision: str = '0001_create_artex_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### Adherents table ###
    op.create_table('adherents',
        sa.Column('id_adherent', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('nom', sa.String(length=255), nullable=False),
        sa.Column('prenom', sa.String(length=255), nullable=False),
        sa.Column('date_naissance', sa.Date(), nullable=True),
        sa.Column('adresse', sa.String(length=255), nullable=True),
        sa.Column('code_postal', sa.String(length=10), nullable=True),
        sa.Column('ville', sa.String(length=100), nullable=True),
        sa.Column('telephone', sa.String(length=20), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('numero_securite_sociale', sa.String(length=15), nullable=True),
        sa.Column('date_adhesion_mutuelle', sa.Date(), server_default=sa.text('CURRENT_DATE'), nullable=True),
        # Removed date_creation and date_modification to match model
        sa.PrimaryKeyConstraint('id_adherent', name=op.f('pk_adherents')),
        sa.UniqueConstraint('email', name=op.f('uq_adherents_email')),
        sa.UniqueConstraint('numero_securite_sociale', name=op.f('uq_adherents_numero_securite_sociale'))
    )
    op.create_index(op.f('ix_adherents_email'), 'adherents', ['email'], unique=True)
    op.create_index(op.f('ix_adherents_numero_securite_sociale'), 'adherents', ['numero_securite_sociale'], unique=True)

    # ### Formules table ###
    op.create_table('formules',
        sa.Column('id_formule', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('nom_formule', sa.String(length=100), nullable=False),
        sa.Column('description_formule', sa.Text(), nullable=True),
        sa.Column('tarif_base_mensuel', sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.PrimaryKeyConstraint('id_formule', name=op.f('pk_formules')),
        sa.UniqueConstraint('nom_formule', name=op.f('uq_formules_nom_formule'))
    )

    # ### Garanties table ###
    op.create_table('garanties',
        sa.Column('id_garantie', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('libelle', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id_garantie', name=op.f('pk_garanties'))
    )

    # ### Formules_Garanties association table ###
    op.create_table('formules_garanties',
        sa.Column('id_formule', sa.Integer(), nullable=False),
        sa.Column('id_garantie', sa.Integer(), nullable=False),
        sa.Column('plafond_remboursement', sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column('taux_remboursement_pourcentage', sa.SmallInteger(), nullable=True), # Representing TINYINT
        sa.Column('franchise', sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column('conditions_specifiques', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['id_formule'], ['formules.id_formule'], name=op.f('fk_formules_garanties_id_formule_formules')),
        sa.ForeignKeyConstraint(['id_garantie'], ['garanties.id_garantie'], name=op.f('fk_formules_garanties_id_garantie_garanties')),
        sa.PrimaryKeyConstraint('id_formule', 'id_garantie', name=op.f('pk_formules_garanties'))
    )

    # ### Contrats table ###
    op.create_table('contrats',
        sa.Column('id_contrat', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('id_adherent_principal', sa.Integer(), nullable=False),
        sa.Column('numero_contrat', sa.String(length=50), nullable=False),
        sa.Column('date_debut_contrat', sa.Date(), nullable=False),
        sa.Column('date_fin_contrat', sa.Date(), nullable=True),
        sa.Column('type_contrat', sa.String(length=100), nullable=True),
        sa.Column('statut_contrat', sa.String(length=50), server_default='Actif', nullable=True),
        sa.Column('id_formule', sa.Integer(), nullable=True),
        # Removed date_creation and date_modification to match model
        sa.ForeignKeyConstraint(['id_adherent_principal'], ['adherents.id_adherent'], name=op.f('fk_contrats_id_adherent_principal_adherents')),
        sa.ForeignKeyConstraint(['id_formule'], ['formules.id_formule'], name=op.f('fk_contrats_id_formule_formules')),
        sa.PrimaryKeyConstraint('id_contrat', name=op.f('pk_contrats')),
        sa.UniqueConstraint('numero_contrat', name=op.f('uq_contrats_numero_contrat'))
    )
    op.create_index(op.f('ix_contrats_numero_contrat'), 'contrats', ['numero_contrat'], unique=True)

    # ### SinistresArtex table ###
    op.create_table('sinistres_artex',  # Renamed table
        sa.Column('id_sinistre_artex', sa.Integer(), autoincrement=True, nullable=False),  # Renamed PK column
        sa.Column('id_contrat', sa.Integer(), nullable=False),
        sa.Column('id_adherent', sa.Integer(), nullable=False),
        sa.Column('type_sinistre', sa.String(length=255), nullable=False),
        sa.Column('description_sinistre', sa.Text(), nullable=True),
        sa.Column('date_declaration_agent', sa.Date(), server_default=sa.text('CURRENT_DATE'), nullable=False),
        sa.Column('statut_sinistre_artex', sa.String(length=100), server_default='Information enregistrée par agent', nullable=False), # Renamed column
        sa.Column('date_survenance', sa.Date(), nullable=True),
        # Removed date_creation and date_modification to match model
        sa.ForeignKeyConstraint(['id_contrat'], ['contrats.id_contrat'], name=op.f('fk_sinistres_artex_id_contrat_contrats')),
        sa.ForeignKeyConstraint(['id_adherent'], ['adherents.id_adherent'], name=op.f('fk_sinistres_artex_id_adherent_adherents')),
        sa.PrimaryKeyConstraint('id_sinistre_artex', name=op.f('pk_sinistres_artex'))  # Updated PK constraint name
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('sinistres_artex')  # Renamed table
    op.drop_index(op.f('ix_contrats_numero_contrat'), table_name='contrats')
    op.drop_table('contrats')
    op.drop_table('formules_garanties')
    op.drop_table('garanties')
    op.drop_table('formules')
    op.drop_index(op.f('ix_adherents_numero_securite_sociale'), table_name='adherents')
    op.drop_index(op.f('ix_adherents_email'), table_name='adherents')
    op.drop_table('adherents')
    # ### end Alembic commands ###
