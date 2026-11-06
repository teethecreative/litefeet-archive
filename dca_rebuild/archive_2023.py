"""Read-only 2023 archive. Historical labels are never normalized or merged."""
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path


@dataclass(frozen=True)
class ArchiveNominee:
    name: str
    is_winner: bool


@dataclass(frozen=True)
class ArchiveCategory:
    id: str
    name: str
    nominees: tuple[ArchiveNominee, ...]

    @property
    def winners(self):
        return tuple(n for n in self.nominees if n.is_winner)

    @property
    def other_nominees(self):
        return tuple(n for n in self.nominees if not n.is_winner)


@lru_cache(maxsize=1)
def load_archive_2023():
    # The private source metadata stays in this non-static data file. Only
    # explicit nominee/category fields are passed to the public template.
    path = Path(__file__).parent / 'data' / 'dca_2023_archive.json'
    records = json.loads(path.read_text(encoding='utf-8'))['categories']
    categories = tuple(ArchiveCategory(
        id=c['id'], name=c['name'],
        nominees=tuple(ArchiveNominee(name=n['name'], is_winner=n['is_winner'])
                       for n in c['nominees'])) for c in records)
    if (len(categories) != 31
        or len({c.id for c in categories}) != 31
        or len({c.name for c in categories}) != 31
        or sum(len(c.nominees) for c in categories) != 152
        or sum(len(c.winners) for c in categories) != 32
        or sum(len(c.winners) > 1 for c in categories) != 1):
        raise ValueError('Invalid 2023 archive totals')
    for category in categories:
        if (not category.winners
            or len({n.name for n in category.nominees}) != len(category.nominees)
            or any(not isinstance(n.name, str) or not n.name.strip()
                   or type(n.is_winner) is not bool for n in category.nominees)):
            raise ValueError(f'Invalid nominees in {category.name}')
    team_video = next(c for c in categories if c.name == 'Best Team Video')
    if {n.name for n in team_video.winners} != {'2Crafty', 'Bombsquad'}:
        raise ValueError('Best Team Video must retain both recorded co-winners')
    return categories
