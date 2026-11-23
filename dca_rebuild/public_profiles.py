"""Read-only starter profiles assembled from records already public in the Vault.

Never infer a biography, merge spelling variants, publish private nomination
reasons, or treat an announced matchup as proof that a battle took place.
Profiles are derived on request; no database migration or user-owned record is
created by visiting a name.
"""
from collections import defaultdict
from functools import lru_cache
import hashlib
import re

from flask import g

from dca_rebuild.archive_2023 import load_archive_2023
from dca_rebuild.archive_catalog import all_records
from dca_rebuild.models import LFARecord
from dca_rebuild.public_urls import person_href, person_slug, slugify


def identity_key(value):
    """Match only the same visible name, ignoring case and extra whitespace."""
    return " ".join(str(value or "").split()).casefold()


def is_person_or_team_category(category):
    """Only people/crews get people profiles; awards for songs or events do not."""
    text = identity_key(category)
    return not (
        text.startswith("best event")
        or "event of the year" in text
        or "song of the year" in text
        or "battle moment" in text
    )


def is_team_award_category(category):
    """Recognize team awards without classifying individual team members as teams."""
    name = identity_key(category)
    return bool(re.search(r"\b(?:team|teams|crew|crews)\b", name)
                and not re.search(r"\b(?:member|individual|solo)\b", name))


def matchup_participants(value):
    """Extract only explicitly separated sides of an announced matchup.

    Do not infer participants from free-form descriptions or fuzzy substrings.
    """
    sides = re.split(r"\s+(?:vs\.?|versus)\s+", str(value or ""), flags=re.I)
    if len(sides) < 2:
        return ()
    return tuple(
        part.strip(" .,!?:;")
        for side in sides
        for part in re.split(r"\s+&\s+|\s+\+\s+", side)
        if part.strip(" .,!?:;")
    )


class PublicProfileIndex:
    def __init__(self, records, archive_categories, current_categories, lfa_winners):
        self._profiles = {}
        self._names = {}
        self._archive = {}
        self._by_slug = {}
        aliases = defaultdict(set)
        published_people = [r for r in records if r.get("collection") == "people"]
        self._published_people = published_people

        # Published research identities have priority over newly assembled
        # starter pages. Slash-delimited aliases already belong to that record.
        for record in published_people:
            key = "archive:" + record["slug"]
            self._archive[record["slug"]] = key
            self._profiles[key] = self._new_profile(
                record["title"].split("/")[0].strip(), record=record)
            for alias in record["title"].split("/"):
                if identity_key(alias):
                    aliases[identity_key(alias)].add(key)
        self._aliases = aliases

        for category in archive_categories:
            if not is_person_or_team_category(category.name):
                continue
            for nominee in category.nominees:
                entry = self._get_or_create(nominee.name)
                if entry is None:
                    continue  # Historical identity ambiguity requires review.
                entry["is_team"] |= is_team_award_category(category.name)
                row = dict(
                    program="Dancer's Choice Awards", year=2023,
                    category=category.name,
                    href="/awards/dancers-choice/2023#dca23-" + category.id,
                )
                if nominee.is_winner:
                    self._append_once(entry["wins"], row)
                else:
                    self._append_once(entry["nominations"], row)

        for category in current_categories:
            if not is_person_or_team_category(category["name"]):
                continue
            for nominee in category["nominees"]:
                entry = self._get_or_create(nominee["name"])
                if entry is None:
                    continue
                entry["is_team"] |= is_team_award_category(category["name"])
                self._append_once(entry["nominations"], dict(
                    program="Dancer's Choice Awards", year=2026,
                    category=category["name"],
                    href=category.get("href") or "/awards/dancers-choice/2026",
                    provisional=True,
                ))

        # LFA nomination flyers are historical nomination records, never wins.
        # Keep their names as printed, including unreviewed spelling variations.
        from dca_rebuild.lfa_2026_data import LFA_2026_NOMINEES
        for category_name, names in LFA_2026_NOMINEES.items():
            for name in names:
                entry = self._get_or_create(name)
                if entry is None:
                    continue
                entry["is_team"] |= is_team_award_category(category_name)
                self._append_once(entry["nominations"], dict(
                    program="LiteFeet Awards", year=2026,
                    category=category_name,
                    href="/awards/litefeet-awards/2026",
                ))

        for winner in lfa_winners:
            entry = self._get_or_create(winner.person_name)
            if entry is None:
                continue
            entry["is_team"] |= is_team_award_category(winner.category_name)
            self._append_once(entry["wins"], dict(
                program="LiteFeet Awards", year=winner.year,
                category=winner.category_name,
                href=("/awards/litefeet-awards/" + str(winner.year)
                      if winner.year in (2023, 2024, 2025, 2026)
                      else "/awards/litefeet-awards"),
            ))

        # Give dynamic (award/nomination-only) names stable, collision-safe
        # routes, without stealing URLs from published people records.
        reserved = {person_slug(record) for record in published_people}
        for key, entry in sorted(self._profiles.items()):
            record = entry["archive_record"]
            if record:
                entry["href"] = person_href(record, published_people)
                continue
            slug = slugify(entry["name"])[:72].strip("-") or "archive-subject"
            if slug in reserved:
                suffix = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
                slug = slug[:62].rstrip("-") + "-" + suffix
            reserved.add(slug)
            entry["href"] = "/people/" + slug
            self._by_slug[slug] = entry

        # Link explicitly documented team members to existing exact-name profiles.
        # Missing roster/founding data stays empty; never infer it from awards.
        for entry in self._profiles.values():
            if not entry["is_team"]:
                continue
            for field in ("founders", "current_roster", "former_roster"):
                linked = []
                for item in entry["team_details"][field]:
                    member = {"name": item} if isinstance(item, str) else dict(item) if isinstance(item, dict) else {}
                    if not identity_key(member.get("name")):
                        continue
                    if not member.get("href"):
                        href = self.href(member["name"])
                        if href and href != entry["href"]:
                            member["href"] = href
                    linked.append(member)
                entry["team_details"][field] = linked

        # An explicit identity-only match: never bind a short nickname inside
        # an unrelated word, or a near-match spelling to another person.
        for event in records:
            if event.get("collection") != "events":
                continue
            for group in event.get("battles", []):
                for matchup in group.get("items", []):
                    for name in set(matchup_participants(matchup)):
                        entry = self.by_name(name)
                        if entry is not None:
                            self._append_battle(entry, event, matchup)
            for listing in event.get("lineup_participants", []):
                label = listing.get("name") or "Announced battle lineup"
                for name in listing.get("featuring") or []:
                    entry = self.by_name(name)
                    if entry is not None:
                        self._append_battle(entry, event, label)

        for entry in self._profiles.values():
            entry["wins"].sort(key=lambda row: (-row["year"], row["program"], row["category"]))
            entry["nominations"].sort(key=lambda row: (-row["year"], row["program"], row["category"]))
            entry["battles"].sort(key=lambda row: (row["date"] or "", row["event"]), reverse=True)

    @staticmethod
    def _new_profile(name, record=None):
        # Only explicitly supplied archive team details may populate history.
        details = (record or {}).get("team_details") or {}
        if not isinstance(details, dict):
            details = {}
        record_type = identity_key((record or {}).get("record_type"))
        is_team = bool(record_type in {"team", "crew"} or
                       re.match(r"^(?:team|crew)\b", name, flags=re.I))
        return dict(
            name=name, archive_record=record, wins=[], nominations=[],
            battles=[], href="", is_team=is_team,
            team_details={
                "founded": details.get("founded") or "",
                "founders": details.get("founders") or [],
                "current_roster": details.get("current_roster") or [],
                "former_roster": details.get("former_roster") or [],
            },
        )

    @staticmethod
    def _append_once(rows, row):
        if row not in rows:
            rows.append(row)

    def _get_or_create(self, name):
        normalized = identity_key(name)
        if not normalized:
            return None
        archived = self._aliases.get(normalized, set())
        if len(archived) > 1:
            return None
        key = next(iter(archived)) if archived else "name:" + normalized
        self._names[normalized] = key
        if key not in self._profiles:
            self._profiles[key] = self._new_profile(" ".join(str(name).split()))
        return self._profiles[key]

    def by_name(self, name):
        normalized = identity_key(name)
        if len(self._aliases.get(normalized, ())) > 1:
            return None
        key = self._names.get(normalized)
        if key is None and len(self._aliases.get(normalized, ())) == 1:
            key = next(iter(self._aliases[normalized]))
        return self._profiles.get(key)

    def href(self, name):
        entry = self.by_name(name)
        return entry["href"] if entry else None

    def by_slug(self, slug):
        return self._by_slug.get(slug)

    def for_archive_record(self, slug):
        return self._profiles.get(self._archive.get(slug))

    def _append_battle(self, entry, event, description):
        row = dict(
            event=event["title"], date=event.get("date") or "",
            date_label=event.get("date_label") or "Date unconfirmed",
            matchup=description,
            href="/archive/records/" + event["slug"],
            status="Announced listing — result not confirmed",
        )
        if not any(previous["href"] == row["href"] and
                   previous["matchup"] == row["matchup"]
                   for previous in entry["battles"]):
            entry["battles"].append(row)


def profile_index(session_factory):
    """Request-local published data view, shared by routes and page templates."""
    if not hasattr(g, "_vault_profile_index"):
        from dca_rebuild.share_awards import public_categories
        with session_factory() as db:
            # Only existing approved LFA winner records may imply an award win.
            winners = (db.query(LFARecord)
                       .filter_by(record_type="award_winner")
                       .order_by(LFARecord.year.desc(), LFARecord.id).all())
            # Materialize before closing the session; these are ordinary columns.
            winner_rows = [
                type("Winner", (), {
                    "year": item.year, "category_name": item.category_name,
                    "person_name": item.person_name,
                }) for item in winners
            ]
        g._vault_profile_index = PublicProfileIndex(
            all_records(), load_archive_2023(), public_categories(), winner_rows)
    return g._vault_profile_index
