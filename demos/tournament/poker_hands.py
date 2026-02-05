"""Poker hand ranking utilities for tournament scoring exploration."""

from collections import Counter
from dataclasses import dataclass
from enum import IntEnum
from typing import Self


class Suit(IntEnum):
    CLUBS = 0
    DIAMONDS = 1
    HEARTS = 2
    SPADES = 3

    @classmethod
    def from_char(cls, c: str) -> Self:
        return {"c": cls.CLUBS, "d": cls.DIAMONDS, "h": cls.HEARTS, "s": cls.SPADES}[c.lower()]

    def __str__(self) -> str:
        return ["♣", "♦", "♥", "♠"][self.value]


class Rank(IntEnum):
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14

    @classmethod
    def from_char(cls, c: str) -> Self:
        if c.isdigit():
            return cls(int(c))
        return {
            "t": cls.TEN,
            "j": cls.JACK,
            "q": cls.QUEEN,
            "k": cls.KING,
            "a": cls.ACE,
        }[c.lower()]

    def __str__(self) -> str:
        if self.value <= 10:
            return str(self.value)
        return {11: "J", 12: "Q", 13: "K", 14: "A"}[self.value]


@dataclass(frozen=True, order=True)
class Card:
    rank: Rank
    suit: Suit

    @classmethod
    def from_str(cls, s: str) -> Self:
        """Parse a card from a string like '2c', 'Th', 'As'."""
        return cls(rank=Rank.from_char(s[0]), suit=Suit.from_char(s[1]))

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"


class HandRank(IntEnum):
    HIGH_CARD = 0
    ONE_PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8
    ROYAL_FLUSH = 9


@dataclass(frozen=True, order=True)
class HandValue:
    """Represents the value of a poker hand for comparison.

    Hands are compared first by rank (e.g., flush beats straight),
    then by tiebreakers (kickers in descending order of importance).
    """

    rank: HandRank
    tiebreakers: tuple[int, ...]

    def __str__(self) -> str:
        return f"{self.rank.name} {self.tiebreakers}"


def evaluate_hand(cards: list[Card]) -> HandValue:
    """Evaluate a 5-card poker hand and return its value."""
    if len(cards) != 5:
        raise ValueError(f"Expected 5 cards, got {len(cards)}")

    ranks = sorted([c.rank.value for c in cards], reverse=True)
    suits = [c.suit for c in cards]
    rank_counts = Counter(ranks)

    is_flush = len(set(suits)) == 1
    is_straight = _is_straight(ranks)

    # Check for wheel (A-2-3-4-5)
    is_wheel = set(ranks) == {14, 2, 3, 4, 5}

    # Straight flush / Royal flush
    if is_flush and (is_straight or is_wheel):
        if is_wheel:
            return HandValue(HandRank.STRAIGHT_FLUSH, (5,))  # 5-high straight flush
        if ranks[0] == 14:  # Ace
            return HandValue(HandRank.ROYAL_FLUSH, (14,))
        return HandValue(HandRank.STRAIGHT_FLUSH, (ranks[0],))

    # Four of a kind
    if 4 in rank_counts.values():
        quad = _get_rank_with_count(rank_counts, 4)
        kicker = _get_rank_with_count(rank_counts, 1)
        return HandValue(HandRank.FOUR_OF_A_KIND, (quad, kicker))

    # Full house
    if 3 in rank_counts.values() and 2 in rank_counts.values():
        trips = _get_rank_with_count(rank_counts, 3)
        pair = _get_rank_with_count(rank_counts, 2)
        return HandValue(HandRank.FULL_HOUSE, (trips, pair))

    # Flush
    if is_flush:
        return HandValue(HandRank.FLUSH, tuple(ranks))

    # Straight
    if is_straight:
        return HandValue(HandRank.STRAIGHT, (ranks[0],))
    if is_wheel:
        return HandValue(HandRank.STRAIGHT, (5,))  # 5-high straight

    # Three of a kind
    if 3 in rank_counts.values():
        trips = _get_rank_with_count(rank_counts, 3)
        kickers = sorted(
            [r for r in ranks if rank_counts[r] == 1],
            reverse=True,
        )
        return HandValue(HandRank.THREE_OF_A_KIND, (trips, *kickers))

    # Two pair
    if list(rank_counts.values()).count(2) == 2:
        pairs = sorted(
            [r for r, c in rank_counts.items() if c == 2],
            reverse=True,
        )
        kicker = _get_rank_with_count(rank_counts, 1)
        return HandValue(HandRank.TWO_PAIR, (pairs[0], pairs[1], kicker))

    # One pair
    if 2 in rank_counts.values():
        pair = _get_rank_with_count(rank_counts, 2)
        kickers = sorted(
            [r for r in ranks if rank_counts[r] == 1],
            reverse=True,
        )
        return HandValue(HandRank.ONE_PAIR, (pair, *kickers))

    # High card
    return HandValue(HandRank.HIGH_CARD, tuple(ranks))


def _is_straight(ranks: list[Rank]) -> bool:
    """Check if sorted ranks form a straight (excluding wheel)."""
    for i in range(len(ranks) - 1):
        if ranks[i] - ranks[i + 1] != 1:
            return False
    return True


def _get_rank_with_count(rank_counts: Counter, count: int) -> int:
    """Get the rank that appears exactly `count` times."""
    for rank, c in rank_counts.items():
        if c == count:
            return rank
    raise ValueError(f"No rank with count {count}")


def hand_to_numeric_score(hand_value: HandValue) -> float:
    """Convert a HandValue to a numeric score for comparison.

    Higher scores are better. The score preserves the full ordering
    of poker hands including tiebreakers.
    """
    # Hand rank is most important, then tiebreakers
    base = hand_value.rank.value * 10**10
    for i, tb in enumerate(hand_value.tiebreakers):
        base += tb * (10 ** (8 - i * 2))
    return float(base)


def parse_hand(hand_str: str) -> list[Card]:
    """Parse a hand from a string like '2c 3d 4h 5s 6c' or '2c3d4h5s6c'."""
    hand_str = hand_str.strip()
    if " " in hand_str:
        card_strs = hand_str.split()
    else:
        card_strs = [hand_str[i : i + 2] for i in range(0, len(hand_str), 2)]
    return [Card.from_str(s) for s in card_strs]


def rank_hands(hands: list[list[Card]]) -> list[tuple[int, list[Card], HandValue]]:
    """Rank multiple hands, returning (rank, hand, value) tuples.

    Rank 1 is the best hand. Ties get the same rank.
    """
    evaluated = [(hand, evaluate_hand(hand)) for hand in hands]
    evaluated.sort(key=lambda x: x[1], reverse=True)

    results = []
    current_rank = 1
    prev_value = None

    for i, (hand, value) in enumerate(evaluated):
        if prev_value is not None and value < prev_value:
            current_rank = i + 1
        results.append((current_rank, hand, value))
        prev_value = value

    return results


def main():
    """Demo the hand ranking system."""
    test_hands = [
        "As Ks Qs Js Ts",  # Royal flush
        "9h 8h 7h 6h 5h",  # Straight flush
        "Ah 2h 3h 4h 5h",  # Steel wheel (A-5 straight flush)
        "Kc Kd Kh Ks 2c",  # Four of a kind
        "Qc Qd Qh 7s 7c",  # Full house
        "2d 5d 7d 9d Kd",  # Flush
        "9c 8d 7h 6s 5c",  # Straight
        "Ac 2d 3h 4s 5c",  # Wheel (A-5 straight)
        "Jc Jd Jh 3s 2c",  # Three of a kind
        "Tc Td 5h 5s 2c",  # Two pair
        "8c 8d Ah Ks Qc",  # One pair
        "Ac Kd Qh Js 9c",  # High card
    ]

    print("Poker Hand Rankings Demo")
    print("=" * 60)

    hands = [parse_hand(h) for h in test_hands]
    rankings = rank_hands(hands)

    for rank, hand, value in rankings:
        hand_str = " ".join(str(c) for c in sorted(hand, reverse=True))
        print(f"#{rank:2d}: {hand_str:20s} -> {value}")


if __name__ == "__main__":
    main()
