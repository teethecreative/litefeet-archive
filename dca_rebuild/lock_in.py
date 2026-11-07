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


def practice_view(args):
    key = args.get("deck", "performance")
    if key not in DECKS:
        key = "performance"
    deck = DECKS[key]
    moves = args.getlist("move")
    result = error = None
    if args.get("play"):
        valid_hand = set(moves).issubset(deck["moves"]) and len(set(moves)) == len(moves)
        if not valid_hand or not 1 <= len(moves) <= 3:
            error = "Choose one to three different move cards from this deck."
        else:
            bonus = 2 if deck["favored"] in moves else 0
            score = 2 * len(moves) + bonus
            result = dict(score=score, base=2 * len(moves), bonus=bonus,
                          outcome="You win" if score > 6 else "Tie" if score == 6 else "Opponent wins")
    return dict(decks=DECKS, deck_key=key, deck=deck, selected=moves, result=result, error=error)
