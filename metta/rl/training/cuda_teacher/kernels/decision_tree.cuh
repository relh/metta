#pragma once

#include "common.cuh"
#include "parse_obs.cuh"
#include "map_scan.cuh"
#include "astar.cuh"
#include "bfs_explore.cuh"

// ---------------------------------------------------------------------------
// Stuck prevention (doAction)
// Checks for oscillation patterns and randomly noop-s to break them.
// ---------------------------------------------------------------------------

__device__ int do_action(AgentState* s, int action) {
    bool oscillating = false;

    // Check all 4 oscillation patterns: A-B-A where A and B are opposites
    if (s->last_action_1 == d_cfg.act_move_west &&
        s->last_action_0 == d_cfg.act_move_east &&
        action == d_cfg.act_move_west) oscillating = true;

    if (s->last_action_1 == d_cfg.act_move_east &&
        s->last_action_0 == d_cfg.act_move_west &&
        action == d_cfg.act_move_east) oscillating = true;

    if (s->last_action_1 == d_cfg.act_move_north &&
        s->last_action_0 == d_cfg.act_move_south &&
        action == d_cfg.act_move_north) oscillating = true;

    if (s->last_action_1 == d_cfg.act_move_south &&
        s->last_action_0 == d_cfg.act_move_north &&
        action == d_cfg.act_move_south) oscillating = true;

    if (oscillating && rand_range(&s->rng_state, 1, 2) == 1) {
        return d_cfg.act_noop;
    }
    return action;
}

// ---------------------------------------------------------------------------
// Recipe reading: get active recipe from hub's stored map data
// Mirrors getActiveRecipe from thinky_agents.nim
// ---------------------------------------------------------------------------

struct RecipeInfo {
    int carbon_cost, oxygen_cost, germanium_cost, silicon_cost;
    int pattern_len;  // number of vibes in the 3x3 neighborhood
};

__device__ RecipeInfo get_active_recipe(AgentState* s) {
    RecipeInfo recipe = {};

    int16_t hmx, hmy;
    if (!get_nearby(s, d_cfg.tag_hub, &hmx, &hmy)) return recipe;

    // Count vibes in the 3x3 neighborhood (Offsets8 = self + 8 neighbors)
    for (int dy = -1; dy <= 1; dy++) {
        for (int dx = -1; dx <= 1; dx++) {
            int nx = hmx + dx, ny = hmy + dy;
            if (!in_map(nx, ny)) continue;
            int v = get_special_vibe(s, nx, ny);
            if (v != -1) recipe.pattern_len++;
        }
    }

    // Read protocol features from the hub's special cell
    SpecialCell* hub = find_special(s, hmx, hmy);
    if (hub) {
        recipe.carbon_cost = hub->proto_input_carbon;
        recipe.oxygen_cost = hub->proto_input_oxygen;
        recipe.germanium_cost = hub->proto_input_germanium;
        recipe.silicon_cost = hub->proto_input_silicon;
    }

    return recipe;
}

// ---------------------------------------------------------------------------
// divUp: integer division rounding up
// ---------------------------------------------------------------------------

__device__ __forceinline__ int div_up(int a, int b) {
    return a / b + (a % b > 0 ? 1 : 0);
}

// ---------------------------------------------------------------------------
// Update resource targets from the active recipe
// ---------------------------------------------------------------------------

__device__ void update_resource_targets(AgentState* s, const RecipeInfo* recipe) {
    if (recipe->pattern_len > 0) {
        int n = recipe->pattern_len;
        int ct = div_up(recipe->carbon_cost, n);
        int ot = div_up(recipe->oxygen_cost, n);
        int gt = div_up(recipe->germanium_cost, n);
        int st = div_up(recipe->silicon_cost, n);
        if (ct > s->carbon_target)    s->carbon_target = (int16_t)ct;
        if (ot > s->oxygen_target)    s->oxygen_target = (int16_t)ot;
        if (gt > s->germanium_target) s->germanium_target = (int16_t)gt;
        if (st > s->silicon_target)   s->silicon_target = (int16_t)st;
    } else {
        if (recipe->carbon_cost > s->carbon_target)
            s->carbon_target = (int16_t)recipe->carbon_cost;
        if (recipe->oxygen_cost > s->oxygen_target)
            s->oxygen_target = (int16_t)recipe->oxygen_cost;
        if (recipe->germanium_cost > s->germanium_target)
            s->germanium_target = (int16_t)recipe->germanium_cost;
        if (recipe->silicon_cost > s->silicon_target)
            s->silicon_target = (int16_t)recipe->silicon_cost;
    }
}

// ---------------------------------------------------------------------------
// findAndTakeResource: check chest first, then extractor
// Returns action >= 0 if found, -1 otherwise
// ---------------------------------------------------------------------------

__device__ int find_and_take_resource(
    AgentState* s,
    int current_vibe,
    int16_t resource_feat_id,
    int16_t vibe_get_resource,
    int16_t vibe_action,
    int16_t extractor_tag
) {
    int pmx = to_mx(s->pos_x);
    int pmy = to_my(s->pos_y);

    // Check chest
    int16_t cmx, cmy;
    if (get_nearby(s, d_cfg.tag_chest, &cmx, &cmy)) {
        int chest_inv = get_special_inventory(s, cmx, cmy, resource_feat_id);
        if (chest_inv > 0) {
            if (current_vibe != vibe_get_resource) {
                return vibe_action;
            }
            int action = astar(s, (int16_t)pmx, (int16_t)pmy, cmx, cmy);
            if (action >= 0) return do_action(s, action);
        }
    }

    // Check extractor
    int16_t emx, emy;
    if (get_nearby_extractor(s, extractor_tag, &emx, &emy)) {
        int action = astar(s, (int16_t)pmx, (int16_t)pmy, emx, emy);
        if (action >= 0) return do_action(s, action);
    }

    return -1;
}

// ---------------------------------------------------------------------------
// Main decision tree
// Faithfully mirrors thinky_agents.nim step() lines 217-618
// ---------------------------------------------------------------------------

__device__ int decision_tree(
    AgentState* s,
    const SelfFeatures* sf
) {
    int pmx = to_mx(s->pos_x);
    int pmy = to_my(s->pos_y);

    int vibe = sf->current_vibe;
    int inv_energy = sf->inv_energy;
    int inv_carbon = sf->inv_carbon;
    int inv_oxygen = sf->inv_oxygen;
    int inv_germanium = sf->inv_germanium;
    int inv_silicon = sf->inv_silicon;
    int inv_heart = sf->inv_heart;

    // --- Recipe update ---
    RecipeInfo recipe = get_active_recipe(s);
    update_resource_targets(s, &recipe);

    int16_t tx, ty;
    int action;

    // --- Priority 1: Emergency energy (< 25%) ---
    if (inv_energy < MAX_ENERGY / 4) {
        if (get_nearby_extractor(s, d_cfg.tag_junction, &tx, &ty)) {
            action = astar(s, (int16_t)pmx, (int16_t)pmy, tx, ty);
            if (action >= 0) return do_action(s, action);
        }
    }

    // --- Priority 2: Opportunistic charging (< 80%) ---
    if (inv_energy < MAX_ENERGY - 20) {
        if (get_nearby_extractor(s, d_cfg.tag_junction, &tx, &ty)) {
            if (manhattan(s->pos_x, s->pos_y, to_wx(tx), to_wy(ty)) < 2) {
                action = astar(s, (int16_t)pmx, (int16_t)pmy, tx, ty);
                if (action >= 0) return do_action(s, action);
            }
        }
    }

    // --- Priority 3: Deposit hearts ---
    if (inv_heart > 0) {
        s->carbon_target = 0;
        s->oxygen_target = 0;
        s->germanium_target = 0;
        s->silicon_target = 0;

        if (d_cfg.act_vibe_heart_b != 0 && vibe != d_cfg.vibe_heart_b) {
            return do_action(s, d_cfg.act_vibe_heart_b);
        }
        if (get_nearby(s, d_cfg.tag_chest, &tx, &ty)) {
            action = astar(s, (int16_t)pmx, (int16_t)pmy, tx, ty);
            if (action >= 0) return do_action(s, action);
        }
    }

    // --- Priority 4: Craft heart (have all resources) ---
    // Nim has no guard for targets > 0; when all targets are 0 and inventory is 0,
    // this branch fires and the agent tries to change vibe / go to hub.
    if (inv_carbon >= s->carbon_target &&
        inv_oxygen >= s->oxygen_target &&
        inv_germanium >= s->germanium_target &&
        inv_silicon >= s->silicon_target) {

        if (vibe != d_cfg.vibe_heart_a) {
            return do_action(s, d_cfg.act_vibe_heart_a);
        }
        if (get_nearby(s, d_cfg.tag_hub, &tx, &ty)) {
            action = astar(s, (int16_t)pmx, (int16_t)pmy, tx, ty);
            if (action >= 0) return do_action(s, action);
        }
    }

    // --- Priority 5: Dump excess resources ---
    int total_res = inv_carbon + inv_oxygen + inv_germanium + inv_silicon;
    bool at_max = (total_res >= MAX_RESOURCE_INVENTORY);
    int avg_res = total_res / 4;

    if (at_max && inv_carbon > avg_res && inv_carbon > s->carbon_target + PUT_CARBON_AMOUNT) {
        if (get_nearby(s, d_cfg.tag_chest, &tx, &ty)) {
            if (vibe != d_cfg.vibe_carbon_b) return do_action(s, d_cfg.act_vibe_carbon_b);
            action = astar(s, (int16_t)pmx, (int16_t)pmy, tx, ty);
            if (action >= 0) return do_action(s, action);
        }
    }

    if (at_max && inv_silicon > avg_res && inv_silicon > s->silicon_target + PUT_SILICON_AMOUNT) {
        if (get_nearby(s, d_cfg.tag_chest, &tx, &ty)) {
            if (vibe != d_cfg.vibe_silicon_b) return do_action(s, d_cfg.act_vibe_silicon_b);
            action = astar(s, (int16_t)pmx, (int16_t)pmy, tx, ty);
            if (action >= 0) return do_action(s, action);
        }
    }

    if (at_max && inv_oxygen > avg_res && inv_oxygen > s->oxygen_target + PUT_OXYGEN_AMOUNT) {
        if (get_nearby(s, d_cfg.tag_chest, &tx, &ty)) {
            if (vibe != d_cfg.vibe_oxygen_b) return do_action(s, d_cfg.act_vibe_oxygen_b);
            action = astar(s, (int16_t)pmx, (int16_t)pmy, tx, ty);
            if (action >= 0) return do_action(s, action);
        }
    }

    if (at_max && inv_germanium > avg_res && inv_germanium > s->germanium_target + PUT_GERMANIUM_AMOUNT) {
        if (get_nearby(s, d_cfg.tag_chest, &tx, &ty)) {
            if (vibe != d_cfg.vibe_germanium_b) return do_action(s, d_cfg.act_vibe_germanium_b);
            action = astar(s, (int16_t)pmx, (int16_t)pmy, tx, ty);
            if (action >= 0) return do_action(s, action);
        }
    }

    // --- Priority 6: Gather resources ---
    // Carbon
    if (s->carbon_target > 0 && inv_carbon < s->carbon_target) {
        action = find_and_take_resource(s, vibe,
            d_cfg.feat_inv_carbon, d_cfg.vibe_carbon_a,
            d_cfg.act_vibe_carbon_a, d_cfg.tag_carbon_ext);
        if (action >= 0) return action;
    }

    // Silicon
    if (s->silicon_target > 0 && inv_silicon < s->silicon_target) {
        action = find_and_take_resource(s, vibe,
            d_cfg.feat_inv_silicon, d_cfg.vibe_silicon_a,
            d_cfg.act_vibe_silicon_a, d_cfg.tag_silicon_ext);
        if (action >= 0) return action;
    }

    // Oxygen
    if (s->oxygen_target > 0 && inv_oxygen < s->oxygen_target) {
        action = find_and_take_resource(s, vibe,
            d_cfg.feat_inv_oxygen, d_cfg.vibe_oxygen_a,
            d_cfg.act_vibe_oxygen_a, d_cfg.tag_oxygen_ext);
        if (action >= 0) return action;
    }

    // Germanium
    if (s->germanium_target > 0 && inv_germanium < s->germanium_target) {
        action = find_and_take_resource(s, vibe,
            d_cfg.feat_inv_germanium, d_cfg.vibe_germanium_a,
            d_cfg.act_vibe_germanium_a, d_cfg.tag_germanium_ext);
        if (action >= 0) return action;
    }

    // --- Priority 7: Exploration ---
    inject_explore_locations(s);

    if (s->num_explore_locs == 0) {
        bfs_find_unseen(s);
    }

    if (s->num_explore_locs > 0) {
        for (int i = 0; i < s->num_explore_locs; i++) {
            int emx = s->explore_locs[i][0];
            int emy = s->explore_locs[i][1];
            if (!is_seen(s, emx, emy)) {
                action = astar(s, (int16_t)pmx, (int16_t)pmy, (int16_t)emx, (int16_t)emy);
                if (action >= 0) return do_action(s, action);
                // A* failed — remove and break (try next step)
                remove_explore_loc(s, i);
                break;
            } else {
                // Already seen — remove and break
                remove_explore_loc(s, i);
                break;
            }
        }
    }

    // --- Priority 8: Random move (fallback) ---
    int dir = rand_range(&s->rng_state, 1, 4);
    int move_actions[4] = {
        d_cfg.act_move_north, d_cfg.act_move_south,
        d_cfg.act_move_west, d_cfg.act_move_east
    };
    return do_action(s, move_actions[dir - 1]);
}
