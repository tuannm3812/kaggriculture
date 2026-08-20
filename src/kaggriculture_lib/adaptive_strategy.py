"""Pure, public-state opponent threat classification utilities."""

from dataclasses import dataclass, field
from enum import IntEnum


class ThreatLevel(IntEnum):
    """Monotonic opponent expansion-risk levels."""

    COMPACT = 0
    BUILDING = 1
    COMPOUNDING = 2


@dataclass(frozen=True)
class ThreatSnapshot:
    """The public opponent counts used to determine threat level."""

    quadrants: int
    hands: int
    placed_animals: int


@dataclass(frozen=True)
class ThreatTransition:
    """A classified snapshot together with episode-local changes."""

    level: ThreatLevel
    changed: bool
    reason: str
    day: int
    hour: int
    delta_quadrants: int = 0
    delta_hands: int = 0
    delta_animals: int = 0


@dataclass
class ThreatMemory:
    """Per-player, episode-local monotonic classifier state."""

    level_by_player: dict[int, ThreatLevel] = field(default_factory=dict)
    reason_by_player: dict[int, str] = field(default_factory=dict)
    previous_step_by_player: dict[int, int] = field(default_factory=dict)
    previous_snapshot_by_player: dict[int, ThreatSnapshot] = field(default_factory=dict)

    def update(
        self,
        player: int,
        step: int,
        day: int,
        hour: int,
        snapshot: ThreatSnapshot,
    ) -> ThreatTransition:
        """Classify a public snapshot without allowing in-episode de-escalation."""
        previous_step = self.previous_step_by_player.get(player, -1)
        reset = step == 0 or step < previous_step
        previous_snapshot = self.previous_snapshot_by_player.get(player)
        if reset:
            self.level_by_player[player] = ThreatLevel.COMPACT
            self.reason_by_player.pop(player, None)
            previous_snapshot = None

        self.previous_step_by_player[player] = step
        if previous_snapshot is None:
            delta_quadrants = delta_hands = delta_animals = 0
        else:
            delta_quadrants = snapshot.quadrants - previous_snapshot.quadrants
            delta_hands = snapshot.hands - previous_snapshot.hands
            delta_animals = snapshot.placed_animals - previous_snapshot.placed_animals
        self.previous_snapshot_by_player[player] = snapshot

        observed, reason = _classify(snapshot)
        previous = self.level_by_player.get(player, ThreatLevel.COMPACT)
        current = max(previous, observed)
        changed = current > previous
        stable_reason = reason if changed or player not in self.reason_by_player else self.reason_by_player[player]
        self.level_by_player[player] = current
        self.reason_by_player[player] = stable_reason
        return ThreatTransition(
            current,
            changed,
            stable_reason,
            day,
            hour,
            delta_quadrants,
            delta_hands,
            delta_animals,
        )


def parse_public_threat_snapshot(farm: dict) -> tuple[ThreatSnapshot, str | None]:
    """Return public counts, or a safe snapshot for malformed public state."""
    try:
        tiles = farm["tiles"]
        hands = farm["hands"]
        quadrants = farm["unlocked_quadrants"]
        if not all(isinstance(value, list) for value in (tiles, hands, quadrants)):
            raise TypeError("public state collections must be lists")

        placed_animals = 0
        for row in tiles:
            if not isinstance(row, list):
                raise TypeError("tile rows must be lists")
            for tile in row:
                if tile is not None and not isinstance(tile, dict):
                    raise TypeError("tiles must be mappings")
                if isinstance(tile, dict) and tile.get("animal") in {"COW", "SHEEP", "GOOSE"}:
                    placed_animals += 1
        return ThreatSnapshot(len(quadrants), len(hands), placed_animals), None
    except (KeyError, TypeError):
        return ThreatSnapshot(0, 0, 0), "malformed_public_state"


def _classify(snapshot: ThreatSnapshot) -> tuple[ThreatLevel, str]:
    """Apply the fixed public-count threshold priority order."""
    if snapshot.quadrants >= 3:
        return ThreatLevel.COMPOUNDING, "three_quadrants"
    if snapshot.quadrants >= 2 and snapshot.placed_animals >= 4:
        return ThreatLevel.COMPOUNDING, "two_quadrants_four_animals"
    if snapshot.quadrants >= 2 and snapshot.hands >= 8:
        return ThreatLevel.COMPOUNDING, "two_quadrants_eight_hands"
    if snapshot.placed_animals >= 6:
        return ThreatLevel.COMPOUNDING, "six_animals"
    if snapshot.quadrants >= 2:
        return ThreatLevel.BUILDING, "extra_quadrant"
    if snapshot.hands >= 6:
        return ThreatLevel.BUILDING, "six_hands"
    if snapshot.placed_animals >= 3:
        return ThreatLevel.BUILDING, "three_animals"
    return ThreatLevel.COMPACT, "compact"
