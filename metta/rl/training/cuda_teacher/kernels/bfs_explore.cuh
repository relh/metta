#pragma once

#include "common.cuh"
#include "map_scan.cuh"

// ---------------------------------------------------------------------------
// BFS visited bit helpers (bit 3 of CellCompact.flags)
// ---------------------------------------------------------------------------

__device__ __forceinline__ void bfs_mark(AgentState* s, int mx, int my) {
    s->map[my][mx].flags |= 8;
}

__device__ __forceinline__ bool bfs_is_marked(const AgentState* s, int mx, int my) {
    return s->map[my][mx].flags & 8;
}

// ---------------------------------------------------------------------------
// Clear BFS marks across entire map
// This is expensive but necessary — only cells that were actually pushed
// onto the stack need clearing.  We track them with a parallel array.
// ---------------------------------------------------------------------------

__device__ void bfs_clear_marks(AgentState* s,
                                const int16_t (*touched)[2], int num_touched) {
    for (int i = 0; i < num_touched; i++) {
        s->map[touched[i][1]][touched[i][0]].flags &= ~8;
    }
}

// ---------------------------------------------------------------------------
// Remove an exploration location by index (shift left)
// ---------------------------------------------------------------------------

__device__ void remove_explore_loc(AgentState* s, int idx) {
    for (int i = idx; i < s->num_explore_locs - 1; i++) {
        s->explore_locs[i][0] = s->explore_locs[i + 1][0];
        s->explore_locs[i][1] = s->explore_locs[i + 1][1];
    }
    s->num_explore_locs--;
}

// ---------------------------------------------------------------------------
// Inject exploration locations around newly discovered hub/chest
// Mirrors Nim thinky_agents.nim lines 536-561
// ---------------------------------------------------------------------------

__device__ void inject_explore_locations(AgentState* s) {
    if (!s->seen_hub) {
        int16_t hmx, hmy;
        if (get_nearby(s, d_cfg.tag_hub, &hmx, &hmy)) {
            s->seen_hub = 1;
            s->hub_mx = hmx;
            s->hub_my = hmy;
            // Add 4 diagonal offsets from hub
            const int offsets[4][2] = {{-10, -10}, {-10, 10}, {10, -10}, {10, 10}};
            for (int i = 0; i < 4; i++) {
                if (s->num_explore_locs >= MAX_EXPLORE) break;
                int emx = hmx + offsets[i][0];
                int emy = hmy + offsets[i][1];
                if (in_map(emx, emy)) {
                    s->explore_locs[s->num_explore_locs][0] = (int16_t)emx;
                    s->explore_locs[s->num_explore_locs][1] = (int16_t)emy;
                    s->num_explore_locs++;
                }
            }
        }
    }

    if (!s->seen_chest) {
        int16_t cmx, cmy;
        if (get_nearby(s, d_cfg.tag_chest, &cmx, &cmy)) {
            s->seen_chest = 1;
            s->chest_mx = cmx;
            s->chest_my = cmy;
            // Add 4 cardinal offsets from chest
            const int offsets[4][2] = {{-3, 0}, {0, 3}, {3, 0}, {0, -3}};
            for (int i = 0; i < 4; i++) {
                if (s->num_explore_locs >= MAX_EXPLORE) break;
                int emx = cmx + offsets[i][0];
                int emy = cmy + offsets[i][1];
                if (in_map(emx, emy)) {
                    s->explore_locs[s->num_explore_locs][0] = (int16_t)emx;
                    s->explore_locs[s->num_explore_locs][1] = (int16_t)emy;
                    s->num_explore_locs++;
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// DFS to find nearest unseen reachable cell
// Nim uses popLast (DFS). Seeds from hub if known, else current position.
// ---------------------------------------------------------------------------

__device__ void bfs_find_unseen(AgentState* s) {
    int16_t stack[BFS_MAX_STACK][2];
    int stack_size = 0;

    // Track touched cells for cleanup
    int16_t touched[BFS_MAX_STACK][2];
    int num_touched = 0;

    // Seed location
    int16_t seed_mx, seed_my;
    if (s->seen_hub) {
        seed_mx = s->hub_mx;
        seed_my = s->hub_my;
    } else {
        seed_mx = (int16_t)to_mx(s->pos_x);
        seed_my = (int16_t)to_my(s->pos_y);
    }

    if (!in_map(seed_mx, seed_my)) {
        return;
    }

    stack[0][0] = seed_mx;
    stack[0][1] = seed_my;
    stack_size = 1;
    bfs_mark(s, seed_mx, seed_my);
    touched[0][0] = seed_mx;
    touched[0][1] = seed_my;
    num_touched = 1;

    while (stack_size > 0) {
        // Pop from top (DFS, matching Nim's popLast)
        stack_size--;
        int16_t cx = stack[stack_size][0];
        int16_t cy = stack[stack_size][1];

        if (!is_seen(s, cx, cy)) {
            // Found unseen cell — add to explore locations
            if (s->num_explore_locs < MAX_EXPLORE) {
                s->explore_locs[s->num_explore_locs][0] = cx;
                s->explore_locs[s->num_explore_locs][1] = cy;
                s->num_explore_locs++;
            }
            bfs_clear_marks(s, touched, num_touched);
            return;
        }

        // Expand 4 neighbors using per-agent randomized order (Nim shuffles Offsets4)
        const int ndx[4] = {-1, 0, 0, 1};
        const int ndy[4] = {0, 1, -1, 0};
        for (int di = 0; di < 4; di++) {
            int d = s->offsets4_order[di];
            int nx = cx + ndx[d];
            int ny = cy + ndy[d];
            if (!in_map(nx, ny)) continue;
            if (bfs_is_marked(s, nx, ny)) continue;
            if (!is_walkable(s, nx, ny)) continue;
            if (stack_size >= BFS_MAX_STACK) continue;
            if (num_touched >= BFS_MAX_STACK) continue;  // don't mark if can't track

            bfs_mark(s, nx, ny);
            touched[num_touched][0] = (int16_t)nx;
            touched[num_touched][1] = (int16_t)ny;
            num_touched++;
            stack[stack_size][0] = (int16_t)nx;
            stack[stack_size][1] = (int16_t)ny;
            stack_size++;
        }
    }

    bfs_clear_marks(s, touched, num_touched);
}
