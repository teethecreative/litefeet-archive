# DCA category display metadata.
#
# Descriptions are editable 2026 ballot copy.
# Historical winner information is kept separate from descriptions.

CATEGORY_META = {
    "Best Trickster": {
        "description": "Recognizes standout trick execution, creativity, and style.",
        "winner": "Kid Smoove",
        "affiliation": "Bombsquad",
        "location": "Harlem, New York",
    },

    "Best Hat Trick": {
        "description": "Recognizes standout creativity and execution using hat tricks.",
    },

    "Best Shoe Trick": {
        "description": "Recognizes standout creativity and execution using shoe tricks.",
    },

    "Best Footwork": {
        "description": "Recognizes standout LiteFeet footwork.",
    },

    "Best Battle Moment": {
        "description": "Recognizes a memorable moment from a LiteFeet battle.",
    },

    "Best Tag Team": {
        "description": "Recognizes a standout tag-team performance.",
    },

    "Best Collab": {
        "description": "Recognizes a standout collaborative LiteFeet performance or project.",
    },

    "Best Entertainer": {
        "description": "Recognizes a dancer whose performance and presence consistently entertain.",
    },

    "Best Ankle Bender": {
        "description": "Recognizes standout ankle-breaking and ankle-bending technique.",
    },

    "Life of the Party": {
        "description": "Recognizes someone whose energy brings the party to life.",
    },

    'Best "Lite" Feet Energy': {
        "description": "Recognizes standout energy and presence within LiteFeet.",
    },

    "Best Team Video": {
        "description": "Recognizes a standout LiteFeet team video.",
    },

    "Most Passionate": {
        "description": "Recognizes someone who consistently demonstrates passion for LiteFeet.",
    },

    "Most Versatile": {
        "description": "Recognizes a dancer who demonstrates range across styles, techniques, or settings.",
    },

    "Most Involved": {
        "description": "Recognizes consistent involvement in the LiteFeet community.",
    },

    "Most Fearless (Risk Taker)": {
        "description": "Recognizes someone willing to take risks and push their performance.",
    },

    "Most Improved Dancer": {
        "description": "Recognizes notable growth and improvement as a dancer.",
    },

    "Most Improved Producer": {
        "description": "Recognizes notable growth and improvement as a LiteFeet producer.",
    },

    "Most Consistent Producer": {
        "description": "Recognizes consistent work and output from a LiteFeet producer.",
    },

    "Most Consistent Dancer": {
        "description": "Recognizes consistent dancing, activity, and performance.",
    },

    "Battle Song of the Year": {
        "description": "Recognizes a standout song used within LiteFeet battles.",
    },

    "Content Song of the Year": {
        "description": "Recognizes a standout song used for LiteFeet content.",
    },

    "Best Content Creator": {
        "description": "Recognizes standout LiteFeet-focused content creation.",
    },

    "Best Combo Dancer": {
        "description": "Recognizes standout combinations and transitions within LiteFeet.",
    },

    "Best Producer Collab": {
        "description": "Recognizes a standout collaboration between producers.",
    },

    "Best Balance": {
        "description": "Recognizes standout balance and control within LiteFeet movement.",
    },

    "Best Out of NY Dancer": {
        "description": "Recognizes a standout LiteFeet dancer based outside New York.",
    },

    "Most Underrated": {
        "description": "Recognizes someone whose work deserves greater recognition.",
    },

    "Best Musicality": {
        "description": "Recognizes standout interpretation and connection to the music.",
    },

    "Best Event of 2023": {
        "description": "Recognizes a standout LiteFeet event.",
    },

    # ---------------------------------------------------------
    # Additional community suggestions from the 2023 process
    # ---------------------------------------------------------

    "Most Battles": {
        "description": "Recognizes exceptional participation in LiteFeet battles.",
        "suggested": True,
    },

    "Dancehall": {
        "description": "Community-suggested category from the original DCA process.",
        "suggested": True,
    },

    "Most Overrated": {
        "description": "Community-suggested category from the original DCA process.",
        "suggested": True,
    },

    "Most TKOs": {
        "description": "Recognizes standout TKO results in LiteFeet battles.",
        "suggested": True,
    },

    "Most Battle Wins": {
        "description": "Recognizes standout battle wins during the award period.",
        "suggested": True,
    },

    "Most Resilient": {
        "description": "Recognizes resilience and persistence within the LiteFeet community.",
        "suggested": True,
    },

    "Best Lite Feet Flipper": {
        "description": "Recognizes standout flipping within LiteFeet.",
        "suggested": True,
    },

    "Best Harlem Lite Feet Team": {
        "description": "Recognizes a standout Harlem LiteFeet team.",
        "suggested": True,
    },

    "Most Anticipated Battle": {
        "description": "Recognizes a battle the community most wanted to see.",
        "suggested": True,
    },

    "Litefeeter of the Year": {
        "description": "Recognizes an overall standout LiteFeeter for the award period.",
        "suggested": True,
    },

    "Best Chant": {
        "description": "Recognizes a standout chant associated with LiteFeet culture.",
        "suggested": True,
    },

    "Most Spanky": {
        "description": "Recognizes standout use and expression of Spanky within LiteFeet.",
        "suggested": True,
    },

    "King/Queen of Lite Award": {
        "description": "Community-suggested category from the original DCA process.",
        "suggested": True,
    },

    "Track Killer Award": {
        "description": "Recognizes a dancer known for consistently attacking and bringing tracks to life.",
        "suggested": True,
    },

    "Best Nomad": {
        "description": "Community-suggested category from the original DCA process.",
        "suggested": True,
    },

    "Shy Dancer": {
        "description": "Community-suggested category from the original DCA process.",
        "suggested": True,
    },
}


def get_category_meta(name):
    return CATEGORY_META.get(
        name,
        {
            "description": "Dancer's Choice Awards category.",
        },
    )

# ============================================================
# OFFICIAL AUGUST 2023 DCA RESULTS
# Source: Dancer's Choice August 2023 Results certificates
# ============================================================

OFFICIAL_2023_WINNERS = {
    "Best Trickster": [
        {"name": "Kid Smoove", "team": "Bombsquad", "location": "Harlem, New York"}
    ],
    "Best Hat Trick": [
        {"name": "Kid Smoove", "team": "Bombsquad", "location": "Harlem, New York"}
    ],
    "Best Shoe Trick": [
        {"name": "D Astro", "team": "2RealBoys + WAFFLE", "location": "The Bronx, New York"}
    ],
    "Best Footwork": [
        {"name": "Kid Smoove", "team": "Bombsquad", "location": "Harlem, New York"}
    ],
    "Best Battle Moment": [
        {"name": "Noahlot - Red Bull", "team": "Bombsquad", "location": "Harlem, New York"}
    ],
    "Best Tag Team": [
        {"name": "Tati B & Tah Swag", "team": "", "location": ""}
    ],
    "Best Collab": [
        {"name": "Tati B & Tah Swag", "team": "", "location": ""}
    ],
    "Best Entertainer": [
        {"name": "Tah Swag", "team": "Bombsquad", "location": "Harlem, New York"}
    ],
    "Best Ankle Bender": [
        {"name": "Iron Man", "team": "Live Zombies", "location": "The Bronx, New York"}
    ],
    "Life of the Party": [
        {"name": "K Shakes", "team": "Team Rocket", "location": "Brooklyn, New York"}
    ],
    'Best "Lite" Feet Energy': [
        {"name": "Jada Chanel", "team": "2Crafty", "location": "New York"}
    ],
    "Best Team Video": [
        {"name": "Bombsquad", "team": "", "location": "Harlem, New York"},
        {"name": "2Crafty", "team": "", "location": "New York"},
    ],
    "Most Passionate": [
        {"name": "Jada Chanel", "team": "2Cafty", "location": "New York"}
    ],
    "Most Versatile": [
        {"name": "Noahlot", "team": "Bombsquad", "location": "Harlem, New York"}
    ],
    "Most Involved": [
        {"name": "E Solo", "team": "Team Rocket", "location": "Brooklyn, New York"}
    ],
    "Most Fearless (Risk Taker)": [
        {"name": "Wild N Out", "team": "2 Crafty", "location": "New York"}
    ],
    "Most Improved Dancer": [
        {"name": "Jizzi Jazz", "team": "Bombsquad", "location": "Harlem, New York"}
    ],
    "Most Improved Producer": [
        {"name": "LadyMoSoFou", "team": "LyveTyme", "location": "New York"}
    ],
    "Most Consistent Producer": [
        {"name": "BsnYea", "team": "", "location": ""}
    ],
    "Most Consistent Dancer": [
        {"name": "Kid Smoove", "team": "Bombsquad", "location": "Harlem, New York"}
    ],
    "Battle Song of the Year": [
        {"name": "Tek 9 - LadyMoSoFou", "team": "", "location": ""}
    ],
    "Content Song of the Year": [
        {"name": "Tek 9 - LadyMoSoFou", "team": "", "location": ""}
    ],
    "Best Content Creator": [
        {"name": "Lucky Banks", "team": "Breakfast Club", "location": ""}
    ],
    "Best Combo Dancer": [
        {"name": "Fox Lite", "team": "Live Zombies", "location": "Harlem, New York"}
    ],
    "Best Balance": [
        {"name": "D Astro", "team": "2RealBoys + WAFFLE", "location": "The Bronx, New York"}
    ],
    "Best Musicality": [
        {"name": "K Shakes", "team": "Team Rocket", "location": "Brooklyn, New York"}
    ],
    "Best Out of NY Dancer": [
        {"name": "Jay Bull", "team": "LyveTyme", "location": "United Kingdom"}
    ],
    "Best Event of 2023": [
        {"name": "Litefeet Awards Weekend", "team": "", "location": ""}
    ],
}

# Apply official winners to the ballot metadata.
for category_name, winners in OFFICIAL_2023_WINNERS.items():
    if category_name in CATEGORY_META:
        CATEGORY_META[category_name]["winners"] = winners

        # Keep compatibility with the existing template until it is
        # switched fully to the multi-winner structure.
        CATEGORY_META[category_name]["winner"] = winners[0]["name"]
        CATEGORY_META[category_name]["affiliation"] = winners[0]["team"]
        CATEGORY_META[category_name]["location"] = winners[0]["location"]


# Official 2023 categories added after the original fixed nomination list.
OFFICIAL_2023_WINNERS.update({
    "Best Big Man": [
        {
            "name": "Sound Cloud",
            "team": "2LiveKrew",
            "location": "New York",
        }
    ],
    "Best Junior Dancer": [
        {
            "name": "Tah Swag",
            "team": "Bombsquad",
            "location": "Harlem, New York",
        }
    ],
    "Youngest in Charge": [
        {
            "name": "Tah Swag",
            "team": "Bombsquad",
            "location": "Harlem, New York",
        }
    ],
})

for category_name, winners in OFFICIAL_2023_WINNERS.items():
    if category_name not in CATEGORY_META:
        CATEGORY_META[category_name] = {
            "description": "Dancer's Choice Awards category."
        }

    CATEGORY_META[category_name]["winners"] = winners
    CATEGORY_META[category_name]["winner"] = winners[0]["name"]
    CATEGORY_META[category_name]["affiliation"] = winners[0]["team"]
    CATEGORY_META[category_name]["location"] = winners[0]["location"]

