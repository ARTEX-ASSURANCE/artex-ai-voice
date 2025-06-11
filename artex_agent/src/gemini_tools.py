from google.generativeai.types import FunctionDeclaration, Tool, Schema, Type

# Schema for get_contrat_details function
get_contrat_details_schema = FunctionDeclaration(
    name="get_contrat_details",
    description="Récupère des informations détaillées sur un contrat d'assurance (police d'assurance), y compris les détails de l'adhérent, la formule, et les garanties associées avec leurs conditions spécifiques (comme les plafonds de remboursement). Nécessite le numéro de contrat.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "numero_contrat": Schema(type=Type.STRING, description="Le numéro unique de la police d'assurance (numéro de contrat), par exemple 'POL001', 'AUTO-123'.")
        },
        required=["numero_contrat"]
    )
)

# Schema for open_claim function (SinistreArthex)
open_claim_schema = FunctionDeclaration(
    name="open_claim",
    description="Enregistre une nouvelle déclaration de sinistre pour le compte d'un adhérent auprès d'Arthex. Cela initie le processus d'enregistrement du sinistre. Le traitement et la validation du sinistre sont gérés ultérieurement par l'assureur partenaire.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "numero_contrat": Schema(type=Type.STRING, description="Le numéro de la police d'assurance concernée par le sinistre."),
            "type_sinistre": Schema(type=Type.STRING, description="Le type de sinistre déclaré (par exemple, 'Accident Auto', 'Dégât des eaux Habitation', 'Vol de téléphone', 'Consultation médicale')."),
            "description_sinistre": Schema(type=Type.STRING, description="Une description détaillée de l'incident ou du sinistre fournie par l'utilisateur."),
            "date_survenance": Schema(type=Type.STRING, description="Optionnel. La date à laquelle l'incident s'est produit, au format YYYY-MM-DD.")
        },
        required=["numero_contrat", "type_sinistre", "description_sinistre"]
    )
)

# Tool object containing all function declarations
ARGO_AGENT_TOOLS = [ # Renamed from ARGO to ARTEX for consistency, but keeping ARGO as per user's original naming for now.
                     # If this was a typo and should be ARTEX_AGENT_TOOLS, it needs to be changed here and in gemini_client.py
    Tool(function_declarations=[
        get_contrat_details_schema,
        open_claim_schema,
        # The old get_last_reimbursement_schema is removed as its model/repository was removed.
        # If similar functionality is needed, it would target SinistreArthex or a new RemboursementArthex model.
    ])
]

# Note: The previous `get_last_reimbursement_schema` has been removed as the underlying
# `Remboursement` model and repository were removed in favor of the new Arthex schema.
# The `open_claim_schema` now correctly maps to creating a `SinistreArthex`.
# A new `get_contrat_details_schema` has been added.
# The `ARTEX_AGENT_TOOLS` list has been updated accordingly.
# The name ARGO_AGENT_TOOLS is kept as per the provided snippet, but might be a typo for ARTEX_AGENT_TOOLS.
# If it's a typo, it should be ARTEX_AGENT_TOOLS here and imported as such in gemini_client.py and agent.py.
# For now, I will stick to ARGO_AGENT_TOOLS as specified in this subtask's prompt.
# (Self-correction: The prompt for this step uses ARGO_AGENT_TOOLS in the snippet for gemini_tools.py,
# but the instruction for agent.py says "Import ARGO_AGENT_TOOLS".
# The previous step (17) used ARGO_AGENT_TOOLS in gemini_client.py.
# To maintain consistency with the immediate instruction, I will use ARGO_AGENT_TOOLS.
# If it was meant to be ARTEX_AGENT_TOOLS, that's a global find/replace later.)
