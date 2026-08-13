"""Tests for ladder-match episode configuration helpers."""

from kaggriculture_lib.env_config import LADDER_MATCH_CONFIGURATION, tournament_configuration


def test_ladder_match_constants_match_measured_replays():
    assert LADDER_MATCH_CONFIGURATION["startingMoney"] == 3000
    assert LADDER_MATCH_CONFIGURATION["farmHandCostMult"] == 1
    assert LADDER_MATCH_CONFIGURATION["townShopSellInterval"] == 4
    assert LADDER_MATCH_CONFIGURATION["townCenterSellInterval"] == 24


def test_tournament_configuration_merges_episode_steps_and_seed():
    cfg = tournament_configuration(episode_steps=720, seed=42)
    assert cfg["episodeSteps"] == 720
    assert cfg["seed"] == 42
    assert cfg["startingMoney"] == 3000
    assert cfg["farmHandCostMult"] == 1
