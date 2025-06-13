from google.generativeai.types import Tool # Keep Tool import

# Schema for get_contrat_details function (Dictionary Format)
get_contrat_details_schema = {
    "name": "get_contrat_details",
    "description": "Récupère des informations détaillées sur un contrat d'assurance (police d'assurance), y compris les détails de l'adhérent, la formule, et les garanties associées avec leurs conditions spécifiques (comme les plafonds de remboursement). Nécessite le numéro de contrat.",
    "parameters": {
        "type": "object", # Changed from Type.OBJECT
        "properties": {
            "numero_contrat": {
                "type": "string", # Changed from Type.STRING
                "description": "Le numéro unique de la police d'assurance (numéro de contrat), par exemple 'POL001', 'AUTO-123'."
            }
        },
        "required": ["numero_contrat"]
    }
}

# Schema for open_claim function (SinistreArthex) (Dictionary Format)
open_claim_schema = {
    "name": "open_claim",
    "description": "Enregistre une nouvelle déclaration de sinistre pour le compte d'un adhérent auprès d'Arthex. Cela initie le processus d'enregistrement du sinistre. Le traitement et la validation du sinistre sont gérés ultérieurement par l'assureur partenaire.",
    "parameters": {
        "type": "object", # Changed from Type.OBJECT
        "properties": {
            "numero_contrat": {
                "type": "string", # Changed from Type.STRING
                "description": "Le numéro de la police d'assurance concernée par le sinistre."
            },
            "type_sinistre": {
                "type": "string", # Changed from Type.STRING
                "description": "Le type de sinistre déclaré (par exemple, 'Accident Auto', 'Dégât des eaux Habitation', 'Vol de téléphone', 'Consultation médicale')."
            },
            "description_sinistre": {
                "type": "string", # Changed from Type.STRING
                "description": "Une description détaillée de l'incident ou du sinistre fournie par l'utilisateur."
            },
            "date_survenance": {
                "type": "string", # Changed from Type.STRING, validation happens in _execute_function_call
                "description": "Optionnel. La date à laquelle l'incident s'est produit, au format YYYY-MM-DD."
            }
        },
        "required": ["numero_contrat", "type_sinistre", "description_sinistre"]
    }
}

# Tool object containing all function declarations (now dictionaries)
# Defines the agent tools using the standardized name ARTEX_AGENT_TOOLS.
ARTEX_AGENT_TOOLS = [
    Tool(function_declarations=[
        get_contrat_details_schema,
        open_claim_schema,
        # The old get_last_reimbursement_schema is removed as its model/repository was removed.
        # If similar functionality is needed, it would target SinistreArthex or a new RemboursementArthex model.
    ])
]

# Note: Schemas are now defined as dictionaries directly.
# The `open_claim_schema` correctly maps to creating a `SinistreArthex`.
# A `get_contrat_details_schema` is also included.
# The `ARTEX_AGENT_TOOLS` list has been updated accordingly.
# The previous FunctionDeclaration, Schema, Type imports are removed as they are no longer needed.
# Only the `Tool` import is retained.
