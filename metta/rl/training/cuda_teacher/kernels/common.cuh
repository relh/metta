#pragma once

#include <cstdint>
#include <climits>

// ---------------------------------------------------------------------------
// Grid dimensions
// ---------------------------------------------------------------------------
#define MAP_W 128
#define MAP_H 128
#define MAX_SPECIAL_CELLS 32
#define MAX_EXPLORE 16
#define ASTAR_MAX_OPEN 101
#define ASTAR_MAX_VISITED 512
#define BFS_MAX_STACK 256

// ---------------------------------------------------------------------------
// Constants matching Nim thinky
// ---------------------------------------------------------------------------
#define MAX_ENERGY 100
#define MAX_RESOURCE_INVENTORY 100
#define PUT_CARBON_AMOUNT 10
#define PUT_OXYGEN_AMOUNT 10
#define PUT_GERMANIUM_AMOUNT 1
#define PUT_SILICON_AMOUNT 25

// ---------------------------------------------------------------------------
// Data structures
// ---------------------------------------------------------------------------

struct CellCompact {
    int8_t tag;       // tag value, -1 = no tag / unknown
    uint8_t flags;    // bit 0: has_data, bit 1: group_present
                      // bit 2: reserved for A* visited
                      // bit 3: reserved for BFS visited
                      // bit 4: written_this_step
};

struct SpecialCell {
    int16_t mx, my;             // map coordinates
    int8_t vibe;                // -1 if absent
    // Inventory (for chests)
    uint8_t inv_carbon, inv_oxygen, inv_germanium, inv_silicon, inv_heart;
    uint8_t inv_carbon_p1, inv_carbon_p2;
    uint8_t inv_oxygen_p1, inv_oxygen_p2;
    uint8_t inv_germanium_p1, inv_germanium_p2;
    uint8_t inv_silicon_p1, inv_silicon_p2;
    uint8_t inv_heart_p1, inv_heart_p2;
    // Hub protocol
    uint8_t proto_input_carbon, proto_input_oxygen;
    uint8_t proto_input_germanium, proto_input_silicon;
    uint8_t proto_output_heart;
};

struct AgentState {
    // Position (world coordinates)
    int16_t pos_x, pos_y;

    // Compact map
    CellCompact map[MAP_H][MAP_W];

    // Special cells (chests, hubs, extractors)
    SpecialCell specials[MAX_SPECIAL_CELLS];
    int8_t num_specials;

    // Seen bitfield (64*64 / 32 = 128 uint32s = 512 bytes)
    uint32_t seen[MAP_H * MAP_W / 32];

    // Resource targets
    int16_t carbon_target, oxygen_target;
    int16_t germanium_target, silicon_target;

    // Exploration
    int16_t explore_locs[MAX_EXPLORE][2];  // map coords
    int8_t num_explore_locs;

    // Stuck prevention (2 most recent observed lastActions)
    int8_t last_action_0;  // most recent
    int8_t last_action_1;  // second most recent

    // Discovery flags
    uint8_t seen_hub;
    uint8_t seen_chest;

    // Remembered locations (map coords)
    int16_t hub_mx, hub_my;
    int16_t chest_mx, chest_my;

    // RNG (xorshift32)
    uint32_t rng_state;

    // Per-agent randomized direction order (indices into dx/dy arrays)
    uint8_t offsets4_order[4];

    // First step flag
    uint8_t first_step;
};

// ---------------------------------------------------------------------------
// EnvConfig — lives in __constant__ memory
// ---------------------------------------------------------------------------

struct EnvConfig {
    // Action IDs
    int16_t act_noop, act_move_north, act_move_south, act_move_west, act_move_east;
    int16_t act_vibe_carbon_a, act_vibe_carbon_b;
    int16_t act_vibe_oxygen_a, act_vibe_oxygen_b;
    int16_t act_vibe_germanium_a, act_vibe_germanium_b;
    int16_t act_vibe_silicon_a, act_vibe_silicon_b;
    int16_t act_vibe_heart_a, act_vibe_heart_b;
    int16_t act_vibe_junction;

    // Feature IDs
    int16_t feat_tag, feat_group, feat_vibe, feat_last_action;
    int16_t feat_inv_energy, feat_inv_carbon, feat_inv_oxygen;
    int16_t feat_inv_germanium, feat_inv_silicon, feat_inv_heart;
    int16_t feat_inv_decoder, feat_inv_modulator, feat_inv_resonator, feat_inv_scrambler;
    // Power features
    int16_t feat_inv_carbon_p1, feat_inv_carbon_p2;
    int16_t feat_inv_oxygen_p1, feat_inv_oxygen_p2;
    int16_t feat_inv_germanium_p1, feat_inv_germanium_p2;
    int16_t feat_inv_silicon_p1, feat_inv_silicon_p2;
    int16_t feat_inv_heart_p1, feat_inv_heart_p2;
    // Hub protocol
    int16_t feat_proto_input_carbon, feat_proto_input_oxygen;
    int16_t feat_proto_input_germanium, feat_proto_input_silicon;
    int16_t feat_proto_output_heart;
    // Position features
    int16_t feat_lp_east, feat_lp_west, feat_lp_north, feat_lp_south;

    // Tag IDs
    int16_t tag_agent, tag_wall, tag_hub, tag_chest, tag_junction;
    int16_t tag_carbon_ext, tag_oxygen_ext, tag_germanium_ext, tag_silicon_ext;

    // Vibe IDs
    int16_t vibe_default, vibe_junction;
    int16_t vibe_carbon_a, vibe_carbon_b;
    int16_t vibe_oxygen_a, vibe_oxygen_b;
    int16_t vibe_germanium_a, vibe_germanium_b;
    int16_t vibe_silicon_a, vibe_silicon_b;
    int16_t vibe_heart_a, vibe_heart_b;

    // Observation dimensions
    int16_t obs_half_w, obs_half_h;
    int16_t num_tokens, token_dim;

    // Inventory reconstruction base
    int16_t inventory_token_base;
};

__constant__ EnvConfig d_cfg;

// ---------------------------------------------------------------------------
// Utility functions
// ---------------------------------------------------------------------------

// World coords → map coords
__device__ __forceinline__ int to_mx(int wx) { return wx + MAP_W / 2; }
__device__ __forceinline__ int to_my(int wy) { return wy + MAP_H / 2; }
// Map coords → world coords
__device__ __forceinline__ int to_wx(int mx) { return mx - MAP_W / 2; }
__device__ __forceinline__ int to_wy(int my) { return my - MAP_H / 2; }

__device__ __forceinline__ bool in_map(int mx, int my) {
    return mx >= 0 && mx < MAP_W && my >= 0 && my < MAP_H;
}

__device__ __forceinline__ int manhattan(int x1, int y1, int x2, int y2) {
    int dx = x1 - x2; if (dx < 0) dx = -dx;
    int dy = y1 - y2; if (dy < 0) dy = -dy;
    return dx + dy;
}

// Seen bitfield
__device__ __forceinline__ bool is_seen(const AgentState* s, int mx, int my) {
    int bit = my * MAP_W + mx;
    return (s->seen[bit / 32] >> (bit % 32)) & 1;
}

__device__ __forceinline__ void set_seen(AgentState* s, int mx, int my) {
    int bit = my * MAP_W + mx;
    s->seen[bit / 32] |= (1u << (bit % 32));
}

// Walkability: walls and agent-occupied cells block
__device__ __forceinline__ bool is_walkable(const AgentState* s, int mx, int my) {
    if (!in_map(mx, my)) return false;
    const CellCompact* c = &s->map[my][mx];
    if (!(c->flags & 1)) return true;  // unknown cells are walkable
    if (c->tag == d_cfg.tag_wall) return false;
    if (c->flags & 2) return false;    // group_present → agent there
    return true;
}

// XorShift32 RNG
__device__ __forceinline__ uint32_t xorshift32(uint32_t* state) {
    uint32_t x = *state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

// Random int in [lo, hi] inclusive
__device__ __forceinline__ int rand_range(uint32_t* rng, int lo, int hi) {
    uint32_t r = xorshift32(rng);
    return lo + (int)(r % (uint32_t)(hi - lo + 1));
}

// Cardinal direction arrays for A* (E, W, N, S — matches Nim neighbors() order)
__device__ constexpr int DX[4] = {1, -1, 0, 0};
__device__ constexpr int DY[4] = {0, 0, -1, 1};

// Direction delta → move action
__device__ __forceinline__ int delta_to_action(int dx, int dy) {
    if (dx == 1)  return d_cfg.act_move_east;
    if (dx == -1) return d_cfg.act_move_west;
    if (dy == -1) return d_cfg.act_move_north;
    if (dy == 1)  return d_cfg.act_move_south;
    return d_cfg.act_noop;
}

// Special cell lookup
__device__ SpecialCell* find_special(AgentState* s, int mx, int my) {
    for (int i = 0; i < s->num_specials; i++) {
        if (s->specials[i].mx == mx && s->specials[i].my == my)
            return &s->specials[i];
    }
    return nullptr;
}

__device__ const SpecialCell* find_special(const AgentState* s, int mx, int my) {
    for (int i = 0; i < s->num_specials; i++) {
        if (s->specials[i].mx == mx && s->specials[i].my == my)
            return &s->specials[i];
    }
    return nullptr;
}

__device__ SpecialCell* upsert_special(AgentState* s, int mx, int my) {
    SpecialCell* existing = find_special(s, mx, my);
    if (existing) return existing;
    if (s->num_specials >= MAX_SPECIAL_CELLS) return nullptr;
    SpecialCell* sc = &s->specials[s->num_specials++];
    // Zero-init
    *sc = {};
    sc->mx = mx;
    sc->my = my;
    sc->vibe = -1;
    return sc;
}

// Count agents in 8-neighborhood (for getNearbyExtractor)
__device__ int count_agents_nearby_8(const AgentState* s, int cx, int cy) {
    int count = 0;
    for (int dy = -1; dy <= 1; dy++) {
        for (int dx = -1; dx <= 1; dx++) {
            int nx = cx + dx, ny = cy + dy;
            if (!in_map(nx, ny)) continue;
            if (s->map[ny][nx].flags & 2) count++;  // group_present
        }
    }
    return count;
}

// Reconstruct inventory with power features: value + p1*B + p2*B^2
__device__ __forceinline__ int reconstruct_inventory(int base, int p1, int p2) {
    int result = (base < 0) ? 0 : base;
    int B = d_cfg.inventory_token_base;
    if (B > 1) {
        if (p1 >= 0) result += p1 * B;
        if (p2 >= 0) result += p2 * B * B;
    }
    return result;
}
