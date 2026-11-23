"""Presentation-only nominee fields; preserves the nomination schema and category names."""
import re

EXACT = {
    "Best Tag Team": "duo",
    "Best Producer Collab": "duo",
    "Best Collab": "duo",
    "Best Team Video": "video",
    "Best Battle Moment": "moment",
    "Best Event of the Year": "event",
    "Content Song of the Year": "song",
    "Battle Song of the Year": "song",
    "Event Organizer of the Year": "organization",
    "Best Event Flyer": "video",
    "LiteFeet Anthem of the Year": "song",
    "Best LiteFeet Remix of the Year": "song",
    "Best LiteFeet Tape of the Year": "song",
    "Best Producer Collab Tape of the Year": "song",
}
FIELDS = {
    "dancer": ("Dancer's Name", "Enter dancer's name", "Team / Crew", "Team or crew"),
    "producer": ("Producer's Name", "Enter producer's name", "Affiliation", "Producer collective or team"),
    "team": ("Team or Crew Name", "Enter team or crew name", "Members (optional)", "Names of members"),
    "duo": ("Names of Both People", "Enter both names", "Collaboration / Team", "Team or project name"),
    "organization": ("Organization Name", "Enter organization name", "Contact / Organizer", "Organizer or contact name"),
    "song": ("Song Title", "Enter song title", "Artist / Producer", "Artist or producer name"),
    "event": ("Event Name", "Enter event name", "Organizer / Host", "Event organizer"),
    "video": ("Title or Creator", "Enter title or creator", "Credits / Team", "Creator or team"),
    "moment": ("Battle or Moment", "Enter battle or moment", "Participants", "Names involved"),
    "general": ("Who or What Are You Nominating?", "Enter name or title", "Team / Credits", "Optional supporting names"),
}

def nomination_fields(category_name):
    """Explicit exceptions first, conservative title-based type mapping second."""
    name = (category_name or "").strip()
    norm = name.casefold()
    kind = EXACT.get(name)
    if not kind:
        if any(term in norm for term in ("song", "anthem", "remix", "mixtape", "tape of", "track of")):
            kind = "song"
        elif any(term in norm for term in ("tag team", "collab", "duo", "chemistry")):
            kind = "duo"
        elif any(term in norm for term in ("team", "crew")):
            kind = "team"
        elif any(term in norm for term in ("event", "battle host", "promoter")):
            kind = "event" if "event" in norm and "organizer" not in norm else "organization"
        elif any(term in norm for term in ("platform", "organization", "community builder")):
            kind = "organization"
        elif any(term in norm for term in ("video", "content song", "flyer")):
            kind = "video"
        elif any(term in norm for term in ("battle moment", "moment of")):
            kind = "moment"
        elif "producer" in norm:
            kind = "producer"
        elif any(term in norm for term in ("dancer", "footwork", "shoe trick", "hat trick",
                                           "musicality", "combo", "tkos", "battler",
                                           "entertainer", "versatile", "passionate",
                                           "underrated", "improved", "involved")):
            kind = "dancer"
        else:
            kind = "general"
    label, placeholder, support_label, support_placeholder = FIELDS[kind]
    return dict(kind=kind, label=label, placeholder=placeholder,
                support_label=support_label, support_placeholder=support_placeholder)
