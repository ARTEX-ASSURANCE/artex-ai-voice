"""create artex schema

Revision ID: 0001_create_artex_schema
Revises: 
Create Date: 2025-06-13 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0001_create_artex_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'adherents',
        sa.Column('id_adherent', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('nom', sa.String(255), nullable=False),
        sa.Column('prenom', sa.String(255), nullable=False),
        sa.Column('date_naissance', sa.Date(), nullable=True),
        sa.Column('adresse', sa.String(255), nullable=True),
        sa.Column('code_postal', sa.String(10), nullable=True),
        sa.Column('ville', sa.String(100), nullable=True),
        sa.Column('telephone', sa.String(20), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('numero_securite_sociale', sa.String(15), nullable=True),
        sa.Column('date_adhesion_mutuelle', sa.Date(), nullable=True),
        sa.UniqueConstraint('email', name='uq_adherents_email'),
        sa.UniqueConstraint('numero_securite_sociale', name='uq_adherents_numero_securite_sociale'),
        sa.PrimaryKeyConstraint('id_adherent', name='pk_adherents'),
    )

    op.create_table(
        'garanties',
        sa.Column('id_garantie', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('libelle', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id_garantie', name='pk_garanties'),
    )

    op.create_table(
        'formules',
        sa.Column('id_formule', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('nom_formule', sa.String(100), nullable=False, unique=True),
        sa.Column('description_formule', sa.Text(), nullable=True),
        sa.Column('tarif_base_mensuel', sa.DECIMAL(10, 2), nullable=False),
        sa.PrimaryKeyConstraint('id_formule', name='pk_formules'),
    )

    # association table
    op.create_table(
        'formules_garanties',
        sa.Column('id_formule', sa.Integer(), sa.ForeignKey('formules.id_formule', name='fk_formules_garanties_formule_id'), primary_key=True),
        sa.Column('id_garantie', sa.Integer(), sa.ForeignKey('garanties.id_garantie', name='fk_formules_garanties_garantie_id'), primary_key=True),
        sa.Column('plafond_remboursement', sa.DECIMAL(10, 2), nullable=True),
        sa.Column('taux_remboursement_pourcentage', sa.SmallInteger(), nullable=True),
        sa.Column('franchise', sa.DECIMAL(10, 2), nullable=True),
        sa.Column('conditions_specifiques', sa.Text(), nullable=True),
    )

    op.create_table(
        'contrats',
        sa.Column('id_contrat', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('id_adherent_principal', sa.Integer(), sa.ForeignKey('adherents.id_adherent', name='fk_contrat_adherent_id')),
        sa.Column('numero_contrat', sa.String(50), nullable=False, unique=True),
        sa.Column('date_debut_contrat', sa.Date(), nullable=False),
        sa.Column('date_fin_contrat', sa.Date(), nullable=True),
        sa.Column('type_contrat', sa.String(100), nullable=True),
        sa.Column('statut_contrat', sa.String(50), nullable=False, server_default=sa.text("'Actif'")),
        sa.Column('id_formule', sa.Integer(), sa.ForeignKey('formules.id_formule', name='fk_contrat_formule_id'), nullable=True),
        sa.PrimaryKeyConstraint('id_contrat', name='pk_contrats'),
        sa.UniqueConstraint('numero_contrat', name='uq_contrats_numero_contrat'),
    )

    op.create_table(
        'sinistres_artex',
        sa.Column('id_sinistre_artex', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('id_contrat', sa.Integer(), sa.ForeignKey('contrats.id_contrat', name='fk_sinistre_artex_contrat_id')),
        sa.Column('id_adherent', sa.Integer(), sa.ForeignKey('adherents.id_adherent', name='fk_sinistre_artex_adherent_id')),
        sa.Column('type_sinistre', sa.String(255), nullable=False),
        sa.Column('description_sinistre', sa.Text(), nullable=True),
        sa.Column('date_declaration_agent', sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column('statut_sinistre_artex', sa.String(100), nullable=False, server_default=sa.text("'Information enregistrée par agent'")),
        sa.Column('date_survenance', sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint('id_sinistre_artex', name='pk_sinistres_artex'),
    )


def downgrade():
    op.drop_table('sinistres_artex')
    op.drop_table('contrats')
    op.drop_table('formules_garanties')
    op.drop_table('formules')
    op.drop_table('garanties')
    op.drop_table('adherents')
