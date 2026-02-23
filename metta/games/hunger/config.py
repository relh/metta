"""Shared constants for the Hunger game."""


class HungerConfig:
    RESOURCES = ["hp", "scrambler", "scout", "egg", "kid", "energy", "solar"]
    GEAR = ["scrambler", "scout"]
    PLANT_DENSITY = 0.016
    MAP_WIDTH = 88
    MAP_HEIGHT = 88

    @classmethod
    def estimate_num_plants(cls, num_agents: int) -> int:
        """Estimate total plants from map params. Used for food balance math."""
        from_buildings = int(cls.MAP_WIDTH * cls.MAP_HEIGHT * cls.PLANT_DENSITY)
        from_hub = num_agents  # roughly 1 hub plant per agent spawn
        return from_buildings + from_hub
