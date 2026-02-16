#pragma once

#include <cstdint>

// ---------------------------------------------------------------------------
// Binary min-heap for A* open set (thread-local, stack allocated)
// ---------------------------------------------------------------------------

struct HeapEntry {
    int16_t mx, my;
    int16_t f;
};

__device__ __forceinline__ void heap_push(HeapEntry* heap, int* size,
                                          int16_t mx, int16_t my, int16_t f) {
    if (*size >= ASTAR_MAX_OPEN) return;
    int i = (*size)++;
    heap[i].mx = mx;
    heap[i].my = my;
    heap[i].f = f;
    // Sift up
    while (i > 0) {
        int parent = (i - 1) / 2;
        if (heap[parent].f <= heap[i].f) break;
        HeapEntry tmp = heap[i];
        heap[i] = heap[parent];
        heap[parent] = tmp;
        i = parent;
    }
}

__device__ __forceinline__ HeapEntry heap_pop(HeapEntry* heap, int* size) {
    HeapEntry result = heap[0];
    (*size)--;
    if (*size > 0) {
        heap[0] = heap[*size];
        // Sift down
        int i = 0;
        while (true) {
            int left = 2 * i + 1;
            int right = 2 * i + 2;
            int smallest = i;
            if (left < *size && heap[left].f < heap[smallest].f)
                smallest = left;
            if (right < *size && heap[right].f < heap[smallest].f)
                smallest = right;
            if (smallest == i) break;
            HeapEntry tmp = heap[i];
            heap[i] = heap[smallest];
            heap[smallest] = tmp;
            i = smallest;
        }
    }
    return result;
}
