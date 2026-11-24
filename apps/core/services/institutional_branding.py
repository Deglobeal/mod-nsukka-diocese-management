"""Single source for official M.O.D. Nsukka Diocese document identity."""

from copy import deepcopy


INSTITUTIONAL_BRANDING = {
    "diocese": "CATHOLIC DIOCESE OF NSUKKA",
    "movement": "MAN OF ORDER & DISCIPLINE MOVEMENT, NIGERIA (MOD).",
    "council": "DIOCESAN M.O.D. COUNCIL (D.M.C.)",
    "command": "036 COMMAND NSUKKA",
    "registration": "GOVT. REG. NO. MOI/YO/06/17",
    "email": "036nsukkadmcmd@gmail.com",
    "telegram": "@Modnsukkadmcmd036",
    "telegram_url": "https://t.me/Modnsukkadmcmd036",
    "headquarters": (
        "St. Theresa's Cathedral,",
        "P.O. Box 32, Nsukka,",
        "Enugu State, Nigeria.",
    ),
    "assets": {
        # Replacement point: the repository currently has only a JPEG with a
        # checkerboard baked into the pixels. Replace this path when the
        # approved transparent M.O.D. artwork is supplied.
        "mod_logo": "static/images/branding/mainmodlogo.jpg",
        "approved_mod_logo_replacement_point": "static/images/branding/mod-logo.png",
        "nigeria_coat": "static/images/branding/nigeria-coat-of-arms.png",
    },
    "colors": {
        "green": "#173D32",
        "gold": "#A47B35",
        "ivory": "#F4F1E9",
        "white": "#FFFFFF",
        "black": "#000000",
    },
}


def institutional_branding_context():
    """Return a template-safe copy of the shared branding values."""
    return {"institutional": deepcopy(INSTITUTIONAL_BRANDING)}
