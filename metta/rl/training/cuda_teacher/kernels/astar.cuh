#pragma once

#include "common.cuh"
#include "priority_queue.cuh"

// ---------------------------------------------------------------------------
// Visited node for A* (flat array, linear scan for lookup)
// Uses CellCompact.flags bit 2 for O(1) "in visited set" checks.
// ---------------------------------------------------------------------------

struct VisitedNode {
    int16_t mx, my;
    int16_t g;
    int16_t from_mx, from_my;
};

// Mark a cell as A* visited (bit 2 of flags)
__device__ __forceinline__ void astar_mark(AgentState* s, int mx, int my) {
    s->map[my][mx].flags |= 4;
}

__device__ __forceinline__ bool astar_is_marked(const AgentState* s, int mx, int my) {
    return s->map[my][mx].flags & 4;
}

// ---------------------------------------------------------------------------
// Visited array operations
// ---------------------------------------------------------------------------

__device__ int visited_find(const VisitedNode* visited, int num, int mx, int my) {
    for (int i = 0; i < num; i++) {
        if (visited[i].mx == mx && visited[i].my == my) return i;
    }
    return -1;
}

__device__ void visited_upsert(VisitedNode* visited, int* num,
                               int16_t mx, int16_t my, int16_t g,
                               int16_t from_mx, int16_t from_my) {
    int idx = visited_find(visited, *num, mx, my);
    if (idx >= 0) {
        visited[idx].g = g;
        visited[idx].from_mx = from_mx;
        visited[idx].from_my = from_my;
    } else if (*num < ASTAR_MAX_VISITED) {
        VisitedNode* n = &visited[*num];
        n->mx = mx; n->my = my;
        n->g = g;
        n->from_mx = from_mx;
        n->from_my = from_my;
        (*num)++;
    }
}

__device__ int16_t visited_get_g(const VisitedNode* visited, int num,
                                 int mx, int my) {
    int idx = visited_find(visited, num, mx, my);
    if (idx >= 0) return visited[idx].g;
    return INT16_MAX;
}

// ---------------------------------------------------------------------------
// Path reconstruction: walk came_from from target back to start,
// return the action for the first step.
// ---------------------------------------------------------------------------

__device__ int reconstruct_first_action(
    const VisitedNode* visited, int num,
    int16_t target_mx, int16_t target_my,
    int16_t start_mx, int16_t start_my
) {
    int16_t cx = target_mx, cy = target_my;
    // Safety bound to avoid infinite loops
    for (int steps = 0; steps < ASTAR_MAX_VISITED; steps++) {
        int idx = visited_find(visited, num, cx, cy);
        if (idx < 0) return d_cfg.act_noop;  // shouldn't happen
        int16_t px = visited[idx].from_mx;
        int16_t py = visited[idx].from_my;
        if (px == start_mx && py == start_my) {
            return delta_to_action(cx - start_mx, cy - start_my);
        }
        cx = px;
        cy = py;
    }
    return d_cfg.act_noop;
}

// ---------------------------------------------------------------------------
// Clear A* visited bits from the compact map (bit 2)
// ---------------------------------------------------------------------------

__device__ void astar_clear_marks(AgentState* s,
                                  const VisitedNode* visited, int num) {
    for (int i = 0; i < num; i++) {
        s->map[visited[i].my][visited[i].mx].flags &= ~4;
    }
}

// Also clear from heap entries that may not be in visited
__device__ void astar_clear_marks_heap(AgentState* s,
                                       const HeapEntry* heap, int heap_size) {
    for (int i = 0; i < heap_size; i++) {
        s->map[heap[i].my][heap[i].mx].flags &= ~4;
    }
}

// ---------------------------------------------------------------------------
// A* pathfinding
// Returns the move action for the first step toward target, or -1 if no path.
// ---------------------------------------------------------------------------

__device__ int astar(
    AgentState* state,
    int16_t start_mx, int16_t start_my,
    int16_t target_mx, int16_t target_my
) {
    if (start_mx == target_mx && start_my == target_my) return -1;

    HeapEntry heap[ASTAR_MAX_OPEN];
    int heap_size = 0;

    VisitedNode visited[ASTAR_MAX_VISITED];
    int num_visited = 0;

    int16_t h0 = (int16_t)manhattan(start_mx, start_my, target_mx, target_my);
    heap_push(heap, &heap_size, start_mx, start_my, h0);
    visited_upsert(visited, &num_visited, start_mx, start_my, 0, -1, -1);
    astar_mark(state, start_mx, start_my);

    int result = -1;

    while (heap_size > 0) {
        // Bailout: Nim bails when openSet.len > 100
        if (heap_size > 100) break;

        HeapEntry cur = heap_pop(heap, &heap_size);

        if (cur.mx == target_mx && cur.my == target_my) {
            result = reconstruct_first_action(visited, num_visited,
                                              target_mx, target_my,
                                              start_mx, start_my);
            break;
        }

        int16_t cur_g = visited_get_g(visited, num_visited, cur.mx, cur.my);

        // Expand 4 neighbors (E, W, N, S — matches Nim neighbors() order)
        for (int d = 0; d < 4; d++) {
            int nx = cur.mx + DX[d];
            int ny = cur.my + DY[d];

            if (!in_map(nx, ny)) continue;

            // Target is always walkable (Nim: nb != targetLocation and not isWalkable)
            if (!(nx == target_mx && ny == target_my)) {
                if (!is_walkable(state, nx, ny)) continue;
            }

            int16_t tent_g = cur_g + 1;

            // Check if already visited with better g
            if (astar_is_marked(state, nx, ny)) {
                int16_t existing_g = visited_get_g(visited, num_visited, nx, ny);
                if (tent_g >= existing_g) continue;
            }

            visited_upsert(visited, &num_visited, (int16_t)nx, (int16_t)ny,
                          tent_g, cur.mx, cur.my);
            astar_mark(state, nx, ny);

            int16_t f = tent_g + (int16_t)manhattan(nx, ny, target_mx, target_my);
            heap_push(heap, &heap_size, (int16_t)nx, (int16_t)ny, f);
        }
    }

    // Clean up: clear A* visited bits
    astar_clear_marks(state, visited, num_visited);
    // Also clear any marks left by heap entries not in visited
    astar_clear_marks_heap(state, heap, heap_size);

    return result;
}
