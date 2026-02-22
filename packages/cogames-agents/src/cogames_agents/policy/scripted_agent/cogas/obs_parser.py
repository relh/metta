"""Observation parser for Cogas policy.

Converts raw observation tokens into StateSnapshot and visible entities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .context import StateSnapshot
from .entity_map import Entity

if TYPE_CHECKING:
    from mettagrid.policy.policy_env_interface import PolicyEnvInterface
    from mettagrid.simulator.interface import AgentObservation, ObservationToken

# GLOBAL_LOCATION marker (0xFE) indicates global observations (not tied to grid position)
_GLOBAL_LOCATION_BYTE = 0xFE


def _is_global_token(tok: ObservationToken) -> bool:
    """Check if token is a global observation (not tied to grid position).

    Backwards-compatible: uses is_global property if available (daveey-inv-fix),
    otherwise checks raw location byte directly (main).
    """
    # Use getattr to avoid type error - is_global exists on daveey-inv-fix but not main
    is_global = getattr(tok, "is_global", None)
    if is_global is not None:
        return is_global
    # Fallback: check raw location byte for GLOBAL_LOCATION marker
    return tok.raw_token[0] == _GLOBAL_LOCATION_BYTE


class ObsParser:
    """Parses observation tokens into state snapshot and visible entities."""

    def __init__(self, policy_env_info: PolicyEnvInterface) -> None:
        self._obs_hr = policy_env_info.obs_height // 2
        self._obs_wr = policy_env_info.obs_width // 2
        self._tag_names = policy_env_info.tag_id_to_name

        # Derive vibe names from action names
        self._vibe_names: list[str] = []
        for action_name in [*policy_env_info.action_names, *policy_env_info.vibe_action_names]:
            if action_name.startswith("change_vibe_"):
                self._vibe_names.append(action_name[len("change_vibe_") :])

    def parse(
        self,
        obs: AgentObservation,
        step: int,
        spawn_pos: tuple[int, int],
    ) -> tuple[StateSnapshot, dict[tuple[int, int], Entity]]:
        """Parse observation into state snapshot and visible entities.

        Args:
            obs: Raw observation
            step: Current tick
            spawn_pos: Agent's spawn position for offset calculation

        Returns:
            (state_snapshot, visible_entities_dict)
        """
        state = StateSnapshot()

        # Read center cell for inventory/vibe and local position
        inv: dict[str, int] = {}
        vibe_id = 0
        # Local position tokens: lp:east/west for col offset, lp:north/south for row offset
        # On daveey-inv-fix: these are GLOBAL tokens (at GLOBAL_LOCATION = 0xFE)
        # On main: these appear at the center cell position
        lp_col_offset = 0  # east is positive, west is negative
        lp_row_offset = 0  # south is positive, north is negative
        has_position = False

        center_r, center_c = self._obs_hr, self._obs_wr

        for tok in obs.tokens:
            feature_name = tok.feature.name

            # Global tokens include local position and team hub inventory
            if _is_global_token(tok):
                if feature_name == "lp:east":
                    lp_col_offset = tok.value
                    has_position = True
                elif feature_name == "lp:west":
                    lp_col_offset = -tok.value
                    has_position = True
                elif feature_name == "lp:south":
                    lp_row_offset = tok.value
                    has_position = True
                elif feature_name == "lp:north":
                    lp_row_offset = -tok.value
                    has_position = True
                elif feature_name.startswith("inv:"):
                    resource_name = feature_name[4:]
                    if ":p" in resource_name:
                        base_name, power_str = resource_name.rsplit(":p", 1)
                        power = int(power_str)
                        current = inv.get(base_name, 0)
                        inv[base_name] = current + tok.value * (256**power)
                    else:
                        current = inv.get(resource_name, 0)
                        inv[resource_name] = current + tok.value
                elif feature_name.startswith("team:"):
                    resource_name = feature_name[5:]
                    key = f"team:{resource_name}"
                    if ":p" in resource_name:
                        base_name, power_str = resource_name.rsplit(":p", 1)
                        power = int(power_str)
                        key = f"team:{base_name}"
                        current = inv.get(key, 0)
                        inv[key] = current + tok.value * (256**power)
                    else:
                        current = inv.get(key, 0)
                        inv[key] = current + tok.value
                continue

            # Center cell tokens for inventory/vibe and local position (main compatibility)
            if tok.row() == center_r and tok.col() == center_c:
                # Local position tokens at center cell (main branch)
                if feature_name == "lp:east":
                    lp_col_offset = tok.value
                    has_position = True
                elif feature_name == "lp:west":
                    lp_col_offset = -tok.value
                    has_position = True
                elif feature_name == "lp:south":
                    lp_row_offset = tok.value
                    has_position = True
                elif feature_name == "lp:north":
                    lp_row_offset = -tok.value
                    has_position = True
                elif feature_name.startswith("inv:"):
                    resource_name = feature_name[4:]
                    # Handle multi-token encoding
                    if ":p" in resource_name:
                        base_name, power_str = resource_name.rsplit(":p", 1)
                        power = int(power_str)
                        current = inv.get(base_name, 0)
                        inv[base_name] = current + tok.value * (256**power)
                    else:
                        current = inv.get(resource_name, 0)
                        inv[resource_name] = current + tok.value
                elif feature_name == "vibe":
                    vibe_id = tok.value

        # Build state - lp: tokens give offset from spawn
        if has_position:
            state.position = (spawn_pos[0] + lp_row_offset, spawn_pos[1] + lp_col_offset)
        else:
            state.position = spawn_pos

        state.hp = inv.get("hp", 100)
        state.energy = inv.get("energy", 100)
        state.carbon = inv.get("carbon", 0)
        state.oxygen = inv.get("oxygen", 0)
        state.germanium = inv.get("germanium", 0)
        state.silicon = inv.get("silicon", 0)
        state.heart = inv.get("heart", 0)
        state.influence = inv.get("influence", 0)
        state.miner_gear = inv.get("miner", 0) > 0
        state.scout_gear = inv.get("scout", 0) > 0
        state.aligner_gear = inv.get("aligner", 0) > 0
        state.scrambler_gear = inv.get("scrambler", 0) > 0
        state.vibe = self._get_vibe_name(vibe_id)

        state.team_carbon = inv.get("team:carbon", 0)
        state.team_oxygen = inv.get("team:oxygen", 0)
        state.team_germanium = inv.get("team:germanium", 0)
        state.team_silicon = inv.get("team:silicon", 0)
        state.team_heart = inv.get("team:heart", 0)
        state.team_influence = inv.get("team:influence", 0)

        # Parse visible entities
        visible_entities: dict[tuple[int, int], Entity] = {}
        position_features: dict[tuple[int, int], dict] = {}

        for tok in obs.tokens:
            # Skip global tokens (already processed above for local position and team hub inventory)
            if _is_global_token(tok):
                continue

            obs_r, obs_c = tok.row(), tok.col()
            # Skip tokens without valid spatial location (shouldn't happen after is_global check)
            if obs_r is None or obs_c is None:
                continue
            # Skip center cell
            if obs_r == center_r and obs_c == center_c:
                continue

            world_r = obs_r - self._obs_hr + state.position[0]
            world_c = obs_c - self._obs_wr + state.position[1]
            world_pos = (world_r, world_c)

            if world_pos not in position_features:
                position_features[world_pos] = {"tags": [], "props": {}}

            feature_name = tok.feature.name
            if feature_name == "tag":
                position_features[world_pos]["tags"].append(tok.value)
            elif feature_name in ("cooldown_remaining", "clipped", "remaining_uses"):
                position_features[world_pos]["props"][feature_name] = tok.value
            elif feature_name.startswith("inv:"):
                inv_dict = position_features[world_pos].setdefault("inventory", {})
                suffix = feature_name[4:]
                if ":p" in suffix:
                    base_name, power_str = suffix.rsplit(":p", 1)
                    power = int(power_str)
                    current = inv_dict.get(base_name, 0)
                    inv_dict[base_name] = current + tok.value * (256**power)
                else:
                    current = inv_dict.get(suffix, 0)
                    inv_dict[suffix] = current + tok.value

        # Convert to entities
        for world_pos, features in position_features.items():
            tags = features.get("tags", [])
            if not tags:
                continue

            obj_name = self._resolve_object_name(tags)
            if obj_name == "unknown":
                continue

            props = dict(features.get("props", {}))
            inv_data = features.get("inventory")

            resolved_tags = [self._tag_names.get(tid, "") for tid in tags]
            alignment = self._derive_alignment(obj_name, props.get("clipped", 0), resolved_tags)
            if alignment:
                props["alignment"] = alignment

            # Remaining uses
            if "remaining_uses" not in props:
                props["remaining_uses"] = 999

            # Inventory amount for extractors
            if inv_data:
                props["inventory_amount"] = sum(inv_data.values())
                props["has_inventory"] = True
            else:
                props.setdefault("inventory_amount", -1)

            visible_entities[world_pos] = Entity(
                type=obj_name,
                properties=props,
                last_seen=step,
            )

        return state, visible_entities

    def _resolve_object_name(self, tag_ids: list[int]) -> str:
        """Resolve tag IDs to an object name."""
        resolved = [self._tag_names.get(tid, "") for tid in tag_ids]

        # Priority: type:* tags
        for tag in resolved:
            if tag.startswith("type:"):
                return tag[5:]

        for tag in resolved:
            if tag and not tag.startswith("team:"):
                return tag

        return "unknown"

    def _get_vibe_name(self, vibe_id: int) -> str:
        if 0 <= vibe_id < len(self._vibe_names):
            return self._vibe_names[vibe_id]
        return "default"

    def _derive_alignment(self, obj_name: str, clipped: int, tags: list[str]) -> str | None:
        for tag in tags:
            if tag == "team:cogs":
                return "cogs"
            if tag == "team:clips":
                return "clips"
        if "c:" in obj_name:
            return "cogs"
        if "clips" in obj_name or clipped > 0:
            return "clips"
        return None

    @property
    def obs_half_height(self) -> int:
        return self._obs_hr

    @property
    def obs_half_width(self) -> int:
        return self._obs_wr
