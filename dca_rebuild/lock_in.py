"""Illustrative practice decks and scoring for the Lock In public guide."""

DECKS = {
    "performance": dict(name="Performance", dancer="DC", arena="BC Circle",
                        song="Pure Imagination", setup="Tone Whop",
                        moves=("Knee Drop", "Butterfly", "Swiss Drop", "Coin Drop"),
                        trick="Shoe Clap", favored="Knee Drop",
                        note="DC submitted Performance as the highest stat, Hoodie of Death as a signature move, and a TKO counter as a possible ability."),
    "footwork": dict(name="Footwork", dancer="Practice dancer", arena="NYC Subway",
                     song="Lonely Nights", setup="Rev Up",
                     moves=("Stutter Step", "Around The World", "Butterfly", "Gangsta Lean"),
                     trick="Shoe Foot Clap", favored="Stutter Step",
                     note="An unnamed practice dancer built around the ankles and footwork moves in Tee’s rulebook."),
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
