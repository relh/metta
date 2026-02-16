#pragma once

#include "common.cuh"

// ---------------------------------------------------------------------------
// Parsed self-features output struct
// ---------------------------------------------------------------------------

struct SelfFeatures {
    int inv_energy;
    int inv_carbon, inv_carbon_p1, inv_carbon_p2;
    int inv_oxygen, inv_oxygen_p1, inv_oxygen_p2;
    int inv_germanium, inv_germanium_p1, inv_germanium_p2;
    int inv_silicon, inv_silicon_p1, inv_silicon_p2;
    int inv_heart, inv_heart_p1, inv_heart_p2;
    int inv_decoder, inv_modulator, inv_resonator, inv_scrambler;
    int current_vibe;
    int last_action;
    int lp_east, lp_west, lp_north, lp_south;
};

__device__ void init_self_features(SelfFeatures* sf) {
    sf->inv_energy = -1;
    sf->inv_carbon = -1; sf->inv_carbon_p1 = -1; sf->inv_carbon_p2 = -1;
    sf->inv_oxygen = -1; sf->inv_oxygen_p1 = -1; sf->inv_oxygen_p2 = -1;
    sf->inv_germanium = -1; sf->inv_germanium_p1 = -1; sf->inv_germanium_p2 = -1;
    sf->inv_silicon = -1; sf->inv_silicon_p1 = -1; sf->inv_silicon_p2 = -1;
    sf->inv_heart = -1; sf->inv_heart_p1 = -1; sf->inv_heart_p2 = -1;
    sf->inv_decoder = -1; sf->inv_modulator = -1;
    sf->inv_resonator = -1; sf->inv_scrambler = -1;
    sf->current_vibe = -1;
    sf->last_action = -1;
    sf->lp_east = -1; sf->lp_west = -1;
    sf->lp_north = -1; sf->lp_south = -1;
}

// ---------------------------------------------------------------------------
// Check if a tag value denotes a special cell (hub, chest, extractor, junction)
// ---------------------------------------------------------------------------

__device__ __forceinline__ bool is_special_tag(int8_t tag) {
    return tag == d_cfg.tag_hub ||
           tag == d_cfg.tag_chest ||
           tag == d_cfg.tag_carbon_ext ||
           tag == d_cfg.tag_oxygen_ext ||
           tag == d_cfg.tag_germanium_ext ||
           tag == d_cfg.tag_silicon_ext ||
           tag == d_cfg.tag_junction;
}

// ---------------------------------------------------------------------------
// Update a special cell's feature from an observation token
// ---------------------------------------------------------------------------

__device__ void update_special_feature(AgentState* s, int mx, int my,
                                       int feat_id, int value) {
    SpecialCell* sc = find_special(s, mx, my);
    if (!sc) return;

    if (feat_id == d_cfg.feat_remaining_uses)    { sc->remaining_uses = (int8_t)value; return; }
    if (feat_id == d_cfg.feat_vibe)              { sc->vibe = (int8_t)value; return; }

    // Inventory base
    if (feat_id == d_cfg.feat_inv_carbon)        { sc->inv_carbon = value; return; }
    if (feat_id == d_cfg.feat_inv_oxygen)        { sc->inv_oxygen = value; return; }
    if (feat_id == d_cfg.feat_inv_germanium)     { sc->inv_germanium = value; return; }
    if (feat_id == d_cfg.feat_inv_silicon)        { sc->inv_silicon = value; return; }
    if (feat_id == d_cfg.feat_inv_heart)          { sc->inv_heart = value; return; }

    // Inventory power features
    if (feat_id == d_cfg.feat_inv_carbon_p1)     { sc->inv_carbon_p1 = value; return; }
    if (feat_id == d_cfg.feat_inv_carbon_p2)     { sc->inv_carbon_p2 = value; return; }
    if (feat_id == d_cfg.feat_inv_oxygen_p1)     { sc->inv_oxygen_p1 = value; return; }
    if (feat_id == d_cfg.feat_inv_oxygen_p2)     { sc->inv_oxygen_p2 = value; return; }
    if (feat_id == d_cfg.feat_inv_germanium_p1)  { sc->inv_germanium_p1 = value; return; }
    if (feat_id == d_cfg.feat_inv_germanium_p2)  { sc->inv_germanium_p2 = value; return; }
    if (feat_id == d_cfg.feat_inv_silicon_p1)    { sc->inv_silicon_p1 = value; return; }
    if (feat_id == d_cfg.feat_inv_silicon_p2)    { sc->inv_silicon_p2 = value; return; }
    if (feat_id == d_cfg.feat_inv_heart_p1)      { sc->inv_heart_p1 = value; return; }
    if (feat_id == d_cfg.feat_inv_heart_p2)      { sc->inv_heart_p2 = value; return; }

    // Hub protocol
    if (feat_id == d_cfg.feat_proto_input_carbon)     { sc->proto_input_carbon = value; return; }
    if (feat_id == d_cfg.feat_proto_input_oxygen)      { sc->proto_input_oxygen = value; return; }
    if (feat_id == d_cfg.feat_proto_input_germanium)   { sc->proto_input_germanium = value; return; }
    if (feat_id == d_cfg.feat_proto_input_silicon)     { sc->proto_input_silicon = value; return; }
    if (feat_id == d_cfg.feat_proto_output_heart)      { sc->proto_output_heart = value; return; }
}

// ---------------------------------------------------------------------------
// Parse a self-feature token (at relative 0,0 or 0xFE)
// ---------------------------------------------------------------------------

__device__ void parse_self_feature(SelfFeatures* sf, int feat_id, int value) {
    if (feat_id == d_cfg.feat_inv_energy)       { sf->inv_energy = value; return; }
    if (feat_id == d_cfg.feat_inv_carbon)       { sf->inv_carbon = value; return; }
    if (feat_id == d_cfg.feat_inv_oxygen)       { sf->inv_oxygen = value; return; }
    if (feat_id == d_cfg.feat_inv_germanium)    { sf->inv_germanium = value; return; }
    if (feat_id == d_cfg.feat_inv_silicon)      { sf->inv_silicon = value; return; }
    if (feat_id == d_cfg.feat_inv_heart)        { sf->inv_heart = value; return; }
    if (feat_id == d_cfg.feat_inv_decoder)      { sf->inv_decoder = value; return; }
    if (feat_id == d_cfg.feat_inv_modulator)    { sf->inv_modulator = value; return; }
    if (feat_id == d_cfg.feat_inv_resonator)    { sf->inv_resonator = value; return; }
    if (feat_id == d_cfg.feat_inv_scrambler)    { sf->inv_scrambler = value; return; }
    if (feat_id == d_cfg.feat_vibe)             { sf->current_vibe = value; return; }
    if (feat_id == d_cfg.feat_last_action)      { sf->last_action = value; return; }

    // Power features for self inventory
    if (feat_id == d_cfg.feat_inv_carbon_p1)    { sf->inv_carbon_p1 = value; return; }
    if (feat_id == d_cfg.feat_inv_carbon_p2)    { sf->inv_carbon_p2 = value; return; }
    if (feat_id == d_cfg.feat_inv_oxygen_p1)    { sf->inv_oxygen_p1 = value; return; }
    if (feat_id == d_cfg.feat_inv_oxygen_p2)    { sf->inv_oxygen_p2 = value; return; }
    if (feat_id == d_cfg.feat_inv_germanium_p1) { sf->inv_germanium_p1 = value; return; }
    if (feat_id == d_cfg.feat_inv_germanium_p2) { sf->inv_germanium_p2 = value; return; }
    if (feat_id == d_cfg.feat_inv_silicon_p1)   { sf->inv_silicon_p1 = value; return; }
    if (feat_id == d_cfg.feat_inv_silicon_p2)   { sf->inv_silicon_p2 = value; return; }
    if (feat_id == d_cfg.feat_inv_heart_p1)     { sf->inv_heart_p1 = value; return; }
    if (feat_id == d_cfg.feat_inv_heart_p2)     { sf->inv_heart_p2 = value; return; }

    // Position features
    if (feat_id == d_cfg.feat_lp_east)          { sf->lp_east = value; return; }
    if (feat_id == d_cfg.feat_lp_west)          { sf->lp_west = value; return; }
    if (feat_id == d_cfg.feat_lp_north)         { sf->lp_north = value; return; }
    if (feat_id == d_cfg.feat_lp_south)         { sf->lp_south = value; return; }
}

// ---------------------------------------------------------------------------
// Reconstruct self inventory values using power features
// ---------------------------------------------------------------------------

__device__ void reconstruct_self_inventory(SelfFeatures* sf) {
    sf->inv_energy = (sf->inv_energy < 0) ? 0 : sf->inv_energy;
    sf->inv_carbon = reconstruct_inventory(sf->inv_carbon, sf->inv_carbon_p1, sf->inv_carbon_p2);
    sf->inv_oxygen = reconstruct_inventory(sf->inv_oxygen, sf->inv_oxygen_p1, sf->inv_oxygen_p2);
    sf->inv_germanium = reconstruct_inventory(sf->inv_germanium, sf->inv_germanium_p1, sf->inv_germanium_p2);
    sf->inv_silicon = reconstruct_inventory(sf->inv_silicon, sf->inv_silicon_p1, sf->inv_silicon_p2);
    sf->inv_heart = reconstruct_inventory(sf->inv_heart, sf->inv_heart_p1, sf->inv_heart_p2);
    sf->inv_decoder = (sf->inv_decoder < 0) ? 0 : sf->inv_decoder;
    sf->inv_modulator = (sf->inv_modulator < 0) ? 0 : sf->inv_modulator;
    sf->inv_resonator = (sf->inv_resonator < 0) ? 0 : sf->inv_resonator;
    sf->inv_scrambler = (sf->inv_scrambler < 0) ? 0 : sf->inv_scrambler;
}

// ---------------------------------------------------------------------------
// Main observation parsing
// ---------------------------------------------------------------------------

__device__ void parse_observations(
    const uint8_t* obs,
    int num_tokens,
    AgentState* state,
    SelfFeatures* sf
) {
    init_self_features(sf);

    // Mark the "written_this_step" bit (bit 4) as clear for the visible window.
    // We'll set it on cells that receive data, then use it to clear stale cells.
    int halfW = d_cfg.obs_half_w;
    int halfH = d_cfg.obs_half_h;
    int pmx = to_mx(state->pos_x);
    int pmy = to_my(state->pos_y);

    for (int t = 0; t < num_tokens; t++) {
        uint8_t loc_packed = obs[t * 3];
        uint8_t feat_id    = obs[t * 3 + 1];
        uint8_t value      = obs[t * 3 + 2];

        // Sentinel
        if (loc_packed == 0xFF && feat_id == 0xFF && value == 0xFF) break;

        int rel_x, rel_y;
        bool is_self_token = false;

        if (loc_packed == 0xFE) {
            // Global/self token → relative (0,0)
            rel_x = 0; rel_y = 0;
            is_self_token = true;
        } else if (loc_packed != 0xFF) {
            rel_y = (int)(loc_packed >> 4) - halfH;
            rel_x = (int)(loc_packed & 0x0F) - halfW;
        } else {
            continue;
        }

        // Map coordinates
        int mx = pmx + rel_x;
        int my = pmy + rel_y;
        if (!in_map(mx, my)) {
            // Still parse self features even if out of map bounds
            if (rel_x == 0 && rel_y == 0) {
                parse_self_feature(sf, feat_id, value);
            }
            continue;
        }

        CellCompact* cell = &state->map[my][mx];

        if (feat_id == d_cfg.feat_tag) {
            cell->tag = (int8_t)value;
            cell->flags = (cell->flags & ~2) | (1 | 16);  // has_data + written_this_step, clear group_present
            if (is_special_tag((int8_t)value)) {
                upsert_special(state, mx, my);
            }
        } else if (feat_id == d_cfg.feat_group) {
            cell->flags |= (1 | 2 | 16);  // has_data + group_present + written_this_step
        } else {
            // Other features (vibe, remaining_uses, inventory, protocol)
            // Route to special cell if one exists at this location
            cell->flags |= 16;  // written_this_step
            update_special_feature(state, mx, my, feat_id, value);
        }

        // Self-features (at relative 0,0)
        if (rel_x == 0 && rel_y == 0) {
            parse_self_feature(sf, feat_id, value);
        }

        set_seen(state, mx, my);
    }

    // Reconstruct full inventory values from power features
    reconstruct_self_inventory(sf);
}

// ---------------------------------------------------------------------------
// Clear stale cells in visible window
// After parsing, cells in the visible window that were NOT written this step
// should be marked as observed-but-empty (matching Nim's map[loc] = @[])
// ---------------------------------------------------------------------------

__device__ void clear_visible_stale(AgentState* state) {
    int halfW = d_cfg.obs_half_w;
    int halfH = d_cfg.obs_half_h;
    int pmx = to_mx(state->pos_x);
    int pmy = to_my(state->pos_y);

    for (int dy = -halfH; dy <= halfH; dy++) {
        for (int dx = -halfW; dx <= halfW; dx++) {
            int mx = pmx + dx;
            int my = pmy + dy;
            if (!in_map(mx, my)) continue;

            CellCompact* cell = &state->map[my][mx];
            if (cell->flags & 16) {
                // Was written this step — clear the temporary bit
                cell->flags &= ~16;
            } else {
                // Not written this step — cell is empty in current view
                cell->tag = -1;
                cell->flags = 1;  // has_data=1, group_present=0, written=0
            }
            // Always mark as seen
            set_seen(state, mx, my);
        }
    }
}

// ---------------------------------------------------------------------------
// Position update (mirrors Nim updateMap position logic)
// ---------------------------------------------------------------------------

__device__ void update_position(AgentState* state, const SelfFeatures* sf) {
    if (state->first_step) {
        state->pos_x = 0;
        state->pos_y = 0;
        state->first_step = 0;
    }

    bool has_lp = false;
    int col_offset = 0, row_offset = 0;

    if (sf->lp_east >= 0) { col_offset += sf->lp_east; has_lp = true; }
    if (sf->lp_west >= 0) { col_offset -= sf->lp_west; has_lp = true; }
    if (sf->lp_south >= 0) { row_offset += sf->lp_south; has_lp = true; }
    if (sf->lp_north >= 0) { row_offset -= sf->lp_north; has_lp = true; }

    if (has_lp) {
        state->pos_x = (int16_t)col_offset;
        state->pos_y = (int16_t)row_offset;
    } else {
        int la = sf->last_action;
        if      (la == d_cfg.act_move_north) state->pos_y -= 1;
        else if (la == d_cfg.act_move_south) state->pos_y += 1;
        else if (la == d_cfg.act_move_west)  state->pos_x -= 1;
        else if (la == d_cfg.act_move_east)  state->pos_x += 1;
    }
}
