#pragma once

#include "common.cuh"

// ---------------------------------------------------------------------------
// getNearby: find closest cell with matching tag (Manhattan distance)
// Returns true if found, writes map coords into *out_mx, *out_my
// ---------------------------------------------------------------------------

__device__ bool get_nearby(
    const AgentState* s,
    int16_t tag_id,
    int16_t* out_mx, int16_t* out_my
) {
    int best_dist = 9999;
    bool found = false;
    int wx = s->pos_x;
    int wy = s->pos_y;

    for (int my = 0; my < MAP_H; my++) {
        for (int mx = 0; mx < MAP_W; mx++) {
            const CellCompact* cell = &s->map[my][mx];
            if (!(cell->flags & 1)) continue;  // no data
            if (cell->tag != tag_id) continue;

            int dist = manhattan(to_wx(mx), to_wy(my), wx, wy);
            if (dist < best_dist) {
                best_dist = dist;
                *out_mx = (int16_t)mx;
                *out_my = (int16_t)my;
                found = true;
            }
        }
    }
    return found;
}

// ---------------------------------------------------------------------------
// getNearbyExtractor: like getNearby but filters by:
//   1. agent count in 8-neighborhood <= 1 (avoid crowding)
// ---------------------------------------------------------------------------

__device__ bool get_nearby_extractor(
    const AgentState* s,
    int16_t tag_id,
    int16_t* out_mx, int16_t* out_my
) {
    int best_dist = 9999;
    bool found = false;
    int wx = s->pos_x;
    int wy = s->pos_y;

    for (int my = 0; my < MAP_H; my++) {
        for (int mx = 0; mx < MAP_W; mx++) {
            const CellCompact* cell = &s->map[my][mx];
            if (!(cell->flags & 1)) continue;
            if (cell->tag != tag_id) continue;

            // Check agent crowding in 8-neighborhood
            if (count_agents_nearby_8(s, mx, my) > 1) continue;

            int dist = manhattan(to_wx(mx), to_wy(my), wx, wy);
            if (dist < best_dist) {
                best_dist = dist;
                *out_mx = (int16_t)mx;
                *out_my = (int16_t)my;
                found = true;
            }
        }
    }
    return found;
}

// ---------------------------------------------------------------------------
// Get inventory from a special cell (for chest resource checking)
// Returns the reconstructed inventory value, or 0 if not found
// ---------------------------------------------------------------------------

__device__ int get_special_inventory(
    const AgentState* s,
    int mx, int my,
    int16_t resource_feat_id
) {
    const SpecialCell* sc = find_special(s, mx, my);
    if (!sc) return 0;

    if (resource_feat_id == d_cfg.feat_inv_carbon)
        return reconstruct_inventory(sc->inv_carbon, sc->inv_carbon_p1, sc->inv_carbon_p2);
    if (resource_feat_id == d_cfg.feat_inv_oxygen)
        return reconstruct_inventory(sc->inv_oxygen, sc->inv_oxygen_p1, sc->inv_oxygen_p2);
    if (resource_feat_id == d_cfg.feat_inv_germanium)
        return reconstruct_inventory(sc->inv_germanium, sc->inv_germanium_p1, sc->inv_germanium_p2);
    if (resource_feat_id == d_cfg.feat_inv_silicon)
        return reconstruct_inventory(sc->inv_silicon, sc->inv_silicon_p1, sc->inv_silicon_p2);
    if (resource_feat_id == d_cfg.feat_inv_heart)
        return reconstruct_inventory(sc->inv_heart, sc->inv_heart_p1, sc->inv_heart_p2);

    return 0;
}

// ---------------------------------------------------------------------------
// Get the vibe of a special cell
// ---------------------------------------------------------------------------

__device__ int get_special_vibe(const AgentState* s, int mx, int my) {
    const SpecialCell* sc = find_special(s, mx, my);
    if (!sc) return -1;
    return sc->vibe;
}
