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


def practice_view(args):
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
    return dict(decks=DECKS, rounds=ROUNDS, round_key=key, battle=round_data,
                next_key=keys[(keys.index(key) + 1) % len(keys)], selected=moves, result=result, error=error)
