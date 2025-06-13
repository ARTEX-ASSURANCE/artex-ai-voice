from typing import List, Optional, Sequence, Dict, Any
from sqlalchemy import select, update # Removed 'delete' as it's not actively used yet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload # For eager loading relationships
import datetime

# Assuming models are in this path, adjust if your structure is different
# e.g., from artex_agent.src.database_models import ...
from .database_models import Adherent, Contrat, Formule, Garantie, SinistreArtex, formules_garanties_association

class BaseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

class AdherentRepository(BaseRepository):
    async def create_adherent(self, adherent_data: Dict[str, Any]) -> Adherent:
        # Ensure date fields are in the correct format if they are strings
        if 'date_naissance' in adherent_data and isinstance(adherent_data['date_naissance'], str):
            adherent_data['date_naissance'] = datetime.date.fromisoformat(adherent_data['date_naissance'])
        if 'date_adhesion_mutuelle' in adherent_data and isinstance(adherent_data['date_adhesion_mutuelle'], str):
            adherent_data['date_adhesion_mutuelle'] = datetime.date.fromisoformat(adherent_data['date_adhesion_mutuelle'])

        adherent = Adherent(**adherent_data)
        self.session.add(adherent)
        await self.session.flush()
        await self.session.refresh(adherent)
        return adherent

    async def get_adherent_by_id(self, id_adherent: int) -> Optional[Adherent]:
        stmt = select(Adherent).where(Adherent.id_adherent == id_adherent)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_adherent_by_email(self, email: str) -> Optional[Adherent]:
        stmt = select(Adherent).where(Adherent.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_adherent_by_numero_securite_sociale(self, numero_ss: str) -> Optional[Adherent]:
        stmt = select(Adherent).where(Adherent.numero_securite_sociale == numero_ss)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_adherents(self, skip: int = 0, limit: int = 100) -> Sequence[Adherent]:
        stmt = select(Adherent).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_adherent(self, id_adherent: int, update_data: Dict[str, Any]) -> Optional[Adherent]:
        update_data.pop('id_adherent', None) # Cannot update PK

        # Ensure date fields are in the correct format
        if 'date_naissance' in update_data and isinstance(update_data['date_naissance'], str):
            update_data['date_naissance'] = datetime.date.fromisoformat(update_data['date_naissance'])
        if 'date_adhesion_mutuelle' in update_data and isinstance(update_data['date_adhesion_mutuelle'], str):
            update_data['date_adhesion_mutuelle'] = datetime.date.fromisoformat(update_data['date_adhesion_mutuelle'])

        stmt = update(Adherent).where(Adherent.id_adherent == id_adherent).values(**update_data).returning(Adherent)
        result = await self.session.execute(stmt)
        await self.session.flush() # Ensure changes are flushed

        # The .returning(Adherent) and scalar_one_or_none() should give the updated ORM object
        # but it's good practice to refresh if there are complex states or defaults managed by DB.
        updated_adherent_scalar = result.scalar_one_or_none()
        if updated_adherent_scalar:
             await self.session.refresh(updated_adherent_scalar)
        return updated_adherent_scalar

class ContratRepository(BaseRepository):
    async def create_contrat(self, contrat_data: Dict[str, Any]) -> Contrat:
        if 'date_debut_contrat' in contrat_data and isinstance(contrat_data['date_debut_contrat'], str):
            contrat_data['date_debut_contrat'] = datetime.date.fromisoformat(contrat_data['date_debut_contrat'])
        if 'date_fin_contrat' in contrat_data and isinstance(contrat_data['date_fin_contrat'], str):
            contrat_data['date_fin_contrat'] = datetime.date.fromisoformat(contrat_data['date_fin_contrat'])

        contrat = Contrat(**contrat_data)
        self.session.add(contrat)
        await self.session.flush()
        await self.session.refresh(contrat)
        return contrat

    async def get_contrat_by_numero_contrat(self, numero_contrat: str, load_full_details: bool = False) -> Optional[Contrat]:
        stmt = select(Contrat).where(Contrat.numero_contrat == numero_contrat)
        if load_full_details:
            stmt = stmt.options(
                selectinload(Contrat.adherent_principal),
                selectinload(Contrat.formule).options(
                    selectinload(Formule.garanties) # This loads Garantie objects related to the Formule
                )
            )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_contrat_details_for_function_call(self, numero_contrat: str) -> Optional[Dict[str, Any]]:
        contrat_obj = await self.get_contrat_by_numero_contrat(numero_contrat, load_full_details=True)
        if not contrat_obj:
            return None

        details = {
            "numero_contrat": contrat_obj.numero_contrat,
            "type_contrat": contrat_obj.type_contrat,
            "statut_contrat": contrat_obj.statut_contrat,
            "date_debut_contrat": contrat_obj.date_debut_contrat.isoformat() if contrat_obj.date_debut_contrat else None,
            "date_fin_contrat": contrat_obj.date_fin_contrat.isoformat() if contrat_obj.date_fin_contrat else None,
            "adherent_principal": None,
            "formule": None
        }

        if contrat_obj.adherent_principal:
            details["adherent_principal"] = {
                "nom": contrat_obj.adherent_principal.nom,
                "prenom": contrat_obj.adherent_principal.prenom,
                "email": contrat_obj.adherent_principal.email
            }

        if contrat_obj.formule:
            formule_details_dict = {
                "nom_formule": contrat_obj.formule.nom_formule,
                "description_formule": contrat_obj.formule.description_formule,
                "tarif_base_mensuel": float(contrat_obj.formule.tarif_base_mensuel) if contrat_obj.formule.tarif_base_mensuel is not None else None,
                "garanties_associees": []
            }

            # Query for attributes on the association table for this specific formula
            # This requires joining Garantie with the association table to get garantie libelle
            # and then accessing the association attributes.
            # The selectinload(Formule.garanties) already loads the Garantie objects.
            # To get the association attributes, we iterate through the loaded garanties
            # and access them via the association_proxy or by querying the association table directly if needed.
            # For simplicity, if association attributes are needed and not directly on Garantie via proxy,
            # a separate query on formules_garanties_association filtered by formule_id and garantie_id would be one way.
            # However, the current model setup with `secondary` table loads Garantie objects.
            # Let's assume for now that the details on Garantie object are sufficient or we make another query for association details.

            # This example fetches association details explicitly.
            assoc_stmt = select(
                formules_garanties_association.c.plafond_remboursement,
                formules_garanties_association.c.taux_remboursement_pourcentage,
                formules_garanties_association.c.franchise,
                formules_garanties_association.c.conditions_specifiques,
                Garantie.libelle.label("garantie_libelle"), # Get libelle from Garantie table
                Garantie.description.label("garantie_description")
            ).select_from(formules_garanties_association).join(
                Garantie, formules_garanties_association.c.id_garantie == Garantie.id_garantie
            ).where(formules_garanties_association.c.id_formule == contrat_obj.formule.id_formule)

            assoc_results = await self.session.execute(assoc_stmt)
            for row in assoc_results.mappings().all(): # Use .mappings() for dict-like rows
                formule_details_dict["garanties_associees"].append({
                    "libelle": row["garantie_libelle"],
                    "description": row["garantie_description"],
                    "plafond_remboursement": float(row["plafond_remboursement"]) if row["plafond_remboursement"] is not None else None,
                    "taux_remboursement_pourcentage": int(row["taux_remboursement_pourcentage"]) if row["taux_remboursement_pourcentage"] is not None else None,
                    "franchise": float(row["franchise"]) if row["franchise"] is not None else None,
                    "conditions_specifiques": row["conditions_specifiques"]
                })
            details["formule"] = formule_details_dict
        return details

    async def list_contrats_by_adherent_id(self, id_adherent: int, skip: int = 0, limit: int = 100) -> Sequence[Contrat]:
        stmt = select(Contrat).where(Contrat.id_adherent_principal == id_adherent).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

class FormuleRepository(BaseRepository):
    async def get_formule_by_id(self, id_formule: int, load_garanties: bool = False) -> Optional[Formule]:
        stmt = select(Formule).where(Formule.id_formule == id_formule)
        if load_garanties:
            # This will load Garantie objects. To get attributes from the association table,
            # you might need to iterate through formule.garanties and then access an association_proxy,
            # or query the association table directly as shown in get_contrat_details_for_function_call.
            stmt = stmt.options(selectinload(Formule.garanties))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_formules(self, skip: int = 0, limit: int = 100) -> Sequence[Formule]:
        stmt = select(Formule).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

class GarantieRepository(BaseRepository):
    async def get_garantie_by_id(self, id_garantie: int) -> Optional[Garantie]:
        stmt = select(Garantie).where(Garantie.id_garantie == id_garantie)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_garanties(self, skip: int = 0, limit: int = 100) -> Sequence[Garantie]:
        stmt = select(Garantie).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

class SinistreArtexRepository(BaseRepository): # Renamed class
    async def create_sinistre_artex(self, sinistre_data: Dict[str, Any]) -> SinistreArtex: # Renamed method and return type
        if 'date_declaration_agent' in sinistre_data and isinstance(sinistre_data['date_declaration_agent'], str):
            sinistre_data['date_declaration_agent'] = datetime.date.fromisoformat(sinistre_data['date_declaration_agent'])
        if 'date_survenance' in sinistre_data and isinstance(sinistre_data['date_survenance'], str):
            sinistre_data['date_survenance'] = datetime.date.fromisoformat(sinistre_data['date_survenance'])

        sinistre = SinistreArtex(**sinistre_data) # Updated model instantiation
        self.session.add(sinistre)
        await self.session.flush()
        await self.session.refresh(sinistre)
        return sinistre

    async def get_sinistre_artex_by_id(self, id_sinistre_artex: int) -> Optional[SinistreArtex]: # Renamed method, param, and return type
        stmt = select(SinistreArtex).where(SinistreArtex.id_sinistre_artex == id_sinistre_artex).options( # Updated model and field
            selectinload(SinistreArtex.contrat), # Updated model
            selectinload(SinistreArtex.adherent) # Updated model
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sinistres_by_adherent_id(self, id_adherent: int, skip: int = 0, limit: int = 100) -> Sequence[SinistreArtex]: # Updated return type
        stmt = select(SinistreArtex).where(SinistreArtex.id_adherent == id_adherent).offset(skip).limit(limit).order_by(SinistreArtex.date_declaration_agent.desc()) # Updated model
        result = await self.session.execute(stmt)
        return result.scalars().all()

    # Note: The old RemboursementRepository and UserPreferenceRepository have been removed as per plan.
    # If user preferences are needed with the new Adherent model, a method could be added to AdherentRepository
    # or a new specific repository if preferences become complex.
    # The 'get_last_reimbursement' and 'open_claim' logic is now conceptualized within
    # ContratRepository (for details) and SinistreArthexRepository (for creation).
    # The `get_last_reimbursement_for_policy` would need a new RemboursementArthex model and repository if it's part of the new schema.
    # For now, I'll assume the user's new schema does not have a direct "Remboursement" table like the old one,
    # and the `get_last_reimbursement` tool would need to be re-evaluated or adapted.
    # The provided schema does not contain a "Remboursement" table that matches the old structure.
    # I will keep the old `get_last_reimbursement_for_policy` logic commented out or remove if not applicable.
    # Based on the new models, a "remboursement" concept isn't directly present in the same way.
    # The `open_claim` tool maps to `SinistreArthexRepository.create_sinistre_arthex`.
    # The `get_contrat_details_for_function_call` in `ContratRepository` is a new specific method.
    # The `get_last_reimbursement` tool from `gemini_tools.py` will need a corresponding repository method
    # if that functionality is still desired with the new schema (perhaps querying `SinistreArthex` for indemnified amounts).
    # For this step, I will remove the old RemboursementRepository and its methods as the model was removed.
    # The UserPreferenceRepository is also removed as its model was commented out.
    # The `get_last_reimbursement` tool needs a target in the new repositories.
    # Let's assume for now that "get_last_reimbursement" might refer to the latest claim's indemnified amount or status.
    # This functionality will be adapted in the agent.py / gemini_tools.py later if needed.
    # The current task is to update repositories based on *new models*.
    # The `get_last_reimbursement_for_policy` method from the old RemboursementRepository is not directly applicable
    # to the new schema without a clear "Remboursement" table equivalent.
    # The `SinistreArthex` table has `montant_indemnise` which could be relevant.

    # If a UserPreference-like table is needed, it should be added back to database_models.py
    # and a corresponding repository created. For now, it's removed.
