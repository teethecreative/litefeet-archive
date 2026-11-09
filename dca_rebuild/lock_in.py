"""Illustrative practice decks and scoring for the Lock In public guide."""

DECKS = {
    "performance": dict(name="Performance", dancer="DC", arena="The Lite House",
                        roster=("DC", "Airman", "Aquaman", "Baby Doll", "C Boogie",
                                "E Nauti", "J Dot", "Leaf Mojo", "Lock In Lance", "Maze",
                                "Ms. Flexy", "Nae Davis", "Nem Lite", "Relly Rellz", "Soundcloud",
                                "Wonder Woman", "Action Kid", "A Gutta", "Boog Star", "C Eazy",
                                "Chubz Lite", "Dat Smooth", "Dill Star", "Doofy", "D Sparkz"),
                        song="Pure Imagination", setup="Tone Whop",
                        moves=("Knee Drop", "Needle & Thread", "Hoodie of Death", "Coin Drop"),
                        favored="Hoodie of Death",
                        note="DC submitted Performance as the highest stat, Hoodie of Death as a signature move, and a TKO counter as a possible ability."),
    "spank": dict(name="Spank", dancer="K Cosmic", arena="Slattery Park",
                     roster=("K Cosmic", "Fro Man", "Goya", "Hoodstar", "J Rite",
                             "Kid 50", "Kid Patt", "Larry Smooth", "Mike Gz", "Oyey",
                             "Ramz Lite", "Smooth Chick", "Spot Lite", "Star Live", "Tye Smooth",
                             "Live Motion", "Noah", "Red Ink", "All American Pop", "Cheddar Bob",
                             "Birdman", "Ducksauce", "Dot Lite", "Falcon", "Future"),
                     song="Lonely Nights", setup="Rev Up",
                     moves=("Baggage Claim", "False Alarm", "Stutter Step", "Swiss Drop"),
                     favored="False Alarm",
                     note="K Cosmic chose Spank as the highest stat, named Baggage Claim and False Alarm as signatures, and picked Slattery Park for an arena advantage. False Alarm resets a fake-out and flows back into freestyle."),
}


# Restriction categories are enforced by card ID. The source rulebook does not
# assign specific cards to 2/1/0 restrictions yet; admin configuration may do so
# when an authoritative restriction list is approved. Default: 3 copies.
CARD_RESTRICTIONS = {}


# Demonstration decks follow the card categories in the original rulebook.
# These are examples of a mixed 25-card build, NOT fixed category quotas.
# Keep the earlier 25-person research rosters in DECKS for provenance; those
# source lists are not themselves valid mixed playing decks.
SAMPLE_DECKS = {
    "performance": (
        ("Dancer", ("Airman", "Aquaman", "Baby Doll", "C Boogie", "E Nauti", "J Dot")),
        ("Arena", ("COL 135th", "The Lite House")),
        ("Song", ("Pure Imagination", "Lonely Nights", "Trap So Hard", "Dirty Martini", "Trap Bump'N")),
        ("Move", ("Rev Up", "Tone Whop", "Butterfly", "Stutter Step", "Knee Drop",
                  "Coin Drop", "Needle & Thread")),
        ("Trick", ("Shoe Trick", "Hat Trick")),
        ("Upgrade", ("Fake Out", "Chant")),
        ("Frib", ("No Hype",)),
    ),
    "spank": (
        ("Dancer", ("Fro Man", "Goya", "Hoodstar", "J Rite", "Kid 50", "Kid Patt")),
        ("Arena", ("COL Cypress", "Union Square")),
        ("Song", ("Trap So Hard", "Lonely Nights", "Pure Imagination", "JELLYFISH JAM", "MR MEESEEKS")),
        ("Move", ("Tone Whop", "Around The World", "Gangsta Lean", "Swiss Drop",
                  "Kiss Of Death", "No Gwop", "Slatter Gwop")),
        ("Trick", ("Shoe Clap", "Shirt Trick")),
        ("Upgrade", ("Fake Out", "Tag In")),
        ("Frib", ("Slippery Floors",)),
    ),
}


def public_sample_decks():
    result = []
    for index, (key, categories) in enumerate(SAMPLE_DECKS.items(), start=1):
        # Different sample sizes help players see how a mixed deck grows.
        # The 10 additional cards are existing names from the planning source,
        # not new invented cards or a mandated type distribution.
        if index == 2:
            categories = tuple(
                (kind, tuple(cards) + {
                    "Dancer": ("Live Motion", "Noah", "Red Ink"),
                    "Arena": ("Slattery Park", "FNL"),
                    "Move": ("Butterfly", "Knee Drop", "Needle & Thread"),
                    "Trick": ("Hat Trick",),
                    "Frib": ("No Hype",),
                }.get(kind, ())) for kind, cards in categories
            )
        total = sum(len(cards) for _, cards in categories)
        if not 25 <= total <= 50:
            raise ValueError("Sample deck must contain 25–50 total cards")
        # Existing demo decks must remain usable under the current opener rule.
        readiness = sample_deck_readiness(categories)
        if not readiness["playable"]:
            raise ValueError(f"Sample deck {index} lacks a required card or opening/main move")
        result.append(dict(key=key, name=f"Sample deck {index}",
                           total=total, readiness=readiness,
                           categories=[dict(type=kind, count=len(cards), cards=cards)
                                       for kind, cards in categories]))
    return result


# Search catalog combines the documented card examples and the existing
# submitted dancer rosters. Unreviewed public requests are never added here.
RULEBOOK_CARDS = {
    "Arena": ("80 Grounds", "BC Circle", "COL 135th", "COL Cypress", "COL Teen Night",
              "D Cole", "Devoe", "FNL", "L Pac", "Millbank", "Mindlezz Thoughtz",
              "NYC Subway", "Rucker Park / Kingdom", "Slattery Park", "Terror Dome",
              "Times Square", "The Lite House", "Union Square", "Wild Out Saturdays"),
    "Move": ("Rev Up", "Bad One", "Tone Whop", "Butterfly", "Tweak",
             "Around The World", "Gangsta Lean", "Stutter Step", "Knee Drop",
             "Swiss Drop", "Coin Drop", "Kiss Of Death", "Needle & Thread",
             "Villain Swoop", "Streetfighter Walk", "No Gwop", "Slatter Gwop"),
    "Trick": ("Shoe Trick", "Shoe Clap", "Shoe Foot Clap", "Hat Trick",
              "Shirt Trick", "Animation", "Connects"),
    "Upgrade": ("Fake Out", "Tag In", "Chant"),
    "Frib": ("Restart Round", "Slippery Floors", "Team Beef Chant", "No Hype",
              "Tweak Out", "Talking Shit"),
}


# Source-grounded move taxonomy. The original rulebook (Move Cards, p. 4)
# distinguishes opening setup from Ankles/Footwork and Combos.
# Latest game direction: only Rev Up OR Tone Wop may open a standard round.
# "Bad One" is in the older rulebook's setup list, but its status under the
# updated opening rule needs review: preserve the catalog entry without making
# it a legal opening or a main move. Trick and Frib are separate card TYPES.
MOVE_FAMILIES = {
    "rev up": "Rev Ups",
    "tone whop": "Wops",
    "tone wop": "Wops",
    "bad one": "Legacy setup — review",
    "butterfly": "Footwork",
    "tweak": "Footwork",
    "around the world": "Footwork",
    "gangsta lean": "Footwork",
    "stutter step": "Footwork",
    "knee drop": "Combo",
    "swiss drop": "Combo",
    "coin drop": "Combo",
    "kiss of death": "Combo",
    "needle & thread": "Combo",
    "villain swoop": "Combo",
    "streetfighter walk": "Combo",
    "no gwop": "Combo",
    "slatter gwop": "Combo",
}

OPENING_FAMILIES = frozenset(("Rev Ups", "Wops"))
MAIN_MOVE_FAMILIES = frozenset(("Footwork", "Combo"))


def sample_deck_readiness(categories):
    """Validate the sample's opening and main move, without fixed type quotas."""
    cards = [(kind, name) for kind, names in categories for name in names]
    openers = [(kind, name) for kind, name in cards
               if kind == "Move" and MOVE_FAMILIES.get(name.casefold()) in OPENING_FAMILIES]
    mains = [(kind, name) for kind, name in cards
             if (kind == "Move" and MOVE_FAMILIES.get(name.casefold()) in MAIN_MOVE_FAMILIES)
             or kind == "Trick"]
    required = tuple(kind for kind in ("Dancer", "Arena", "Song")
                     if not any(card_type == kind for card_type, _ in cards))
    return dict(
        playable=not required and bool(openers) and bool(mains),
        missing_types=required, opening_count=len(openers), main_count=len(mains),
    )


def public_card_catalog(extra_songs=()):
    """Combine existing Archive names and song sources, without producer cards.

    Archive name-only entries remain historical references, not evidence of
    permission or approved dancer abilities. Unreviewed requests stay private.
    """
    from dca_rebuild.archive_catalog import all_records
    from dca_rebuild.music_batch_catalog import batch_catalog

    catalog = {}
    def add(kind, name, *, producer="", artist="", source="", reference=False):
        name = str(name or "").strip()
        if not name or kind == "Producer":
            return
        key = (kind, name.casefold())
        if key not in catalog:
            catalog[key] = dict(id=f"{kind}::{name}", type=kind, name=name,
                                move_family=MOVE_FAMILIES.get(name.casefold(), "") if kind == "Move" else "",
                                review_status="reference-only" if reference else "source-draft",
                                producer="", artist="", source="", reference=reference)
        entry = catalog[key]
        if producer and not entry["producer"]:
            entry["producer"] = producer
        if artist and not entry["artist"]:
            entry["artist"] = artist
        if source and not entry["source"]:
            entry["source"] = source
        entry["reference"] = entry["reference"] and reference
        if not reference and entry["review_status"] == "reference-only":
            entry["review_status"] = "source-draft"

    for sample in public_sample_decks():
        for group in sample["categories"]:
            for name in group["cards"]:
                add(group["type"], name)
    for existing in DECKS.values():
        for name in existing["roster"]:
            add("Dancer", name)
    for kind, names in RULEBOOK_CARDS.items():
        for name in names:
            add(kind, name)

    for row in all_records():
        if row.get("collection") == "people":
            # Producer-only, judge-only and team-only historical identities
            # are not automatically recast as dancer cards.
            details = dict(row.get("information") or [])
            role_labels = details.get("Original role labels (unverified)", "")
            roles = {part.strip().casefold() for part in role_labels.split(",")}
            if row.get("record_type") == "legacy_identity" and roles and "dancer" not in roles:
                continue
            for name in row["title"].split("/"):
                add("Dancer", name, source=row.get("source_label", ""),
                    reference=True)

    for row in batch_catalog():
        if row.get("kind") != "track":
            continue
        add("Song", row["title"], producer=row.get("producer_credit") or "",
            artist=row.get("artist_or_creator") or "", source=row.get("url") or "")

    for row in extra_songs:
        add("Song", row.get("title"), producer=row.get("producer_credit") or "",
            artist=row.get("artist") or "", source=row.get("source") or "")

    return sorted(catalog.values(), key=lambda row: (
        row["type"].casefold(), row["name"].casefold(), row["id"].casefold()))


def published_music_cards(engine):
    """Read existing published music releases without rewriting any database."""
    if engine is None:
        return ()
    from sqlalchemy import inspect, text
    schema = inspect(engine)
    if not schema.has_table("media_items"):
        return ()
    cols = {item["name"] for item in schema.get_columns("media_items")}
    if not {"title", "media_type", "status"}.issubset(cols):
        return ()
    artist_col = next((col for col in ("artist", "artist_name", "artist_credit")
                       if col in cols), None)
    producer_col = next((col for col in ("producer_name", "producer", "producer_credit")
                         if col in cols), None)
    selected = ["title"] + [col for col in (artist_col, producer_col) if col]
    sql = "SELECT " + ", ".join(selected) + (
        " FROM media_items WHERE media_type = 'music_release' AND status = 'Published'")
    with engine.connect() as connection:
        return tuple(dict(title=row["title"],
                          artist=row.get(artist_col) if artist_col else "",
                          producer_credit=row.get(producer_col) if producer_col else "")
                     for row in connection.execute(text(sql)).mappings())


# Conditions and BP values below are practice scenarios, based on submitted card ideas.
ROUNDS = {
    key: dict(dancer=deck["dancer"], scene=f'{deck["arena"]} · {deck["song"]} by Reel Hectic',
              moves=deck["moves"], combo=(deck["favored"],), bonus=2, reduce=0, opponent=6,
              cue=f'You’ve played {deck["setup"]}. Build a three-move finish.')
    for key, deck in DECKS.items() if key not in ("performance", "spank")
}
ROUNDS.update({
    "greklite": dict(dancer="Greklite", scene="NYC Subway · Ultra macaco",
                     moves=("Rev Up", "Ultra macaco", "Connects", "Evil Kenivel"),
                     combo=("Ultra macaco",), bonus=0, reduce=3, opponent=8,
                     cue="Your opponent’s finish depends on a shoe trick. Use Ultra macaco to block the trick."),
    "e-solo": dict(dancer="E solo", scene="COL Cypress · Team Rocket glide",
                   moves=("Bad One", "Glide", "Hat Roll", "Shoe Clap"),
                   combo=("Glide",), bonus=3, reduce=0, opponent=8,
                   cue="Three Team Rocket cards are on the field. Glide earns one extra BP from each."),
    "future": dict(dancer="Future", scene="Dark Wars · Shoe-trick counterattack",
                   moves=("Knee Drop", "Shoe Trick", "Shirt Trick", "No Gwop"),
                   combo=("Knee Drop", "Shoe Trick"), bonus=0, reduce=4, opponent=9,
                   cue="Your opponent has a three-point lead over a full move set. Pair Knee Drop with a Shoe Trick to take points off their finish."),
    "iceman": dict(dancer="ICEMAN", scene="Union Square · Flow state",
                   moves=("Bionicle", "Animation", "Hat Trick", "Knee Drop"),
                   combo=("Bionicle", "Hat Trick"), bonus=3, reduce=0, opponent=8,
                   cue="Use Bionicle and a Hat Trick in the same set to trigger the practice version of Flow state."),
    "ginger-spice": dict(dancer="Ginger Spice", scene="COL Cypress · Kitana Spice",
                         moves=("Shoulder Work", "Splits", "Animation", "Tone Whop"),
                         combo=("Shoulder Work", "Splits"), bonus=4, reduce=0, opponent=9,
                         cue="Bring shoulder control and flexibility into one set. Pair Shoulder Work with Splits to trigger Kitana Spice."),
    "unkdes": dict(dancer="UnkDes", scene="Ankles and tricks drill",
                   moves=("Stutter Step", "Butterfly", "Hat Trick", "Shoe Trick"),
                   combo=("Stutter Step", "Shoe Trick"), bonus=2, reduce=0, opponent=7,
                   cue="Build from footwork into a shoe trick. This practice pairing draws on UnkDes’s choice of Ankles, Shoe Trick, and Hat Trick."),
})


def practice_view(args, extra_songs=()):
    key = args.get("round", "greklite")
    if key not in ROUNDS:
        key = "greklite"
    round_data = ROUNDS[key]
    moves = args.getlist("move")
    result = error = None
    if args.get("play"):
        valid_hand = set(moves).issubset(round_data["moves"]) and len(set(moves)) == len(moves)
        if not valid_hand or not 1 <= len(moves) <= 3:
            error = "Choose one to three different move cards from this hand."
        else:
            activated = set(round_data["combo"]).issubset(moves)
            bonus = round_data["bonus"] if activated else 0
            reduction = round_data["reduce"] if activated else 0
            base = 2 * len(moves)
            score = base + bonus
            opponent = round_data["opponent"] - reduction
            result = dict(score=score, base=base, bonus=bonus, reduction=reduction, opponent=opponent,
                          outcome="You win" if score > opponent else "Tie" if score == opponent else "Opponent wins")
    keys = list(ROUNDS)
    return dict(decks=DECKS, sample_decks=public_sample_decks(), card_catalog=public_card_catalog(extra_songs), card_restrictions=CARD_RESTRICTIONS, rounds=ROUNDS, round_key=key, battle=round_data,
                next_key=keys[(keys.index(key) + 1) % len(keys)], selected=moves, result=result, error=error)
