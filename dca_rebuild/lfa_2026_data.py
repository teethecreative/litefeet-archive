"""2026 LiteFeet Awards category/winner data confirmed by The LiteFeet Vault owner.

These are LiteFeet Awards (LFA), not Dancer's Choice Awards (DCA).
Category names are grounded in the 2026 LFA nomination flyers; final
winners were supplied by the Vault administrator on November 23, 2026.
"""

LFA_2026_WINNERS = (
    ("Kid of the Year", "XO Wavy"),
    ("Rookie of the Year", "A Handro"),
    ("Producer of the Year", "Speights Raw Kid"),
    ("Shaker of the Year", "D Ski"),
    ("Lady of Lite", "Ty Shotz"),
    ("Best Team", "Team Demon"),
    ("I Am the Lite", "Jay Bull"),
)

# Nominee names transcribed from the six published 2026 LiteFeet Awards
# Instagram nomination flyers supplied by the Vault administrator on Nov 23.
# Preserve flyer spellings; do not silently merge aliases with winner records.
# The Shaker of the Year nominee flyer was not among the six source screenshots.
# Missing categories must remain unknown rather than inferred from the winner.
LFA_2026_NOMINEES = {
    "Kid of the Year": (
        "Cito", "XO Wavy", "Lexii", "Taylah Gang", "Ash Rocket",
    ),
    "Rookie of the Year": (
        "Playdo", "A Haundro", "Red Robin", "Y Axis", "King Kai",
    ),
    "Producer of the Year": (
        "Lil Live", "Phresh Tune", "Speights Raw Kid", "Sound Wave", "Kid Smoove",
    ),
    "Lady of Lite": (
        "Tiny Rillz", "Lady Live", "Ty Shotz", "Lexii", "Jada Chanell",
    ),
    "Best Team": (
        "Team Demon", "2 Real Boyz", "2 Crafty", "2 Live Krew", "Bomb Squad",
    ),
    "I Am the Lite": (
        "Noah Lot", "Kid Smoove", "Tah Swag", "Jay Bull", "XO Wavy",
    ),
}

LFA_2026_SOURCE = (
    "2026 category names: 5th Annual LiteFeet Awards nomination flyers "
    "posted by @litefeetawards with @litefeet_liberals, provided to "
    "The LiteFeet Vault. Winner names confirmed directly by the Vault "
    "administrator on 2026-11-23; external winner-announcement links "
    "have not yet been attached."
)
