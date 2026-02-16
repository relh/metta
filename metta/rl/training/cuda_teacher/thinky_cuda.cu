#include <torch/extension.h>
#include <cuda_runtime.h>
#include <cstring>

#include "kernels/decision_tree.cuh"

// ---------------------------------------------------------------------------
// Main kernel: one thread per agent
// ---------------------------------------------------------------------------

__global__ void thinky_astar_thread(
    const uint8_t* __restrict__ obs,     // [N, T, 3] flattened
    int64_t* __restrict__ actions,        // [N]
    AgentState* __restrict__ states,      // [N]
    const bool* __restrict__ dones,       // [N] or nullptr
    int N, int T
) {
    int agent_id = blockIdx.x * blockDim.x + threadIdx.x;
    if (agent_id >= N) return;

    AgentState* state = &states[agent_id];

    // Reset state on episode boundary
    if (dones != nullptr && dones[agent_id]) {
        state->first_step = 1;
        state->num_specials = 0;
        state->num_explore_locs = 0;
        state->last_action_0 = -1;
        state->last_action_1 = -1;
        state->pos_x = 0;
        state->pos_y = 0;
        state->seen_hub = 0;
        state->seen_chest = 0;
        state->carbon_target = 0;
        state->oxygen_target = 0;
        state->germanium_target = 0;
        state->silicon_target = 0;
        state->hub_mx = 0; state->hub_my = 0;
        state->chest_mx = 0; state->chest_my = 0;
        for (int y = 0; y < MAP_H; y++)
            for (int x = 0; x < MAP_W; x++) {
                state->map[y][x].tag = -1;
                state->map[y][x].flags = 0;
            }
        for (int j = 0; j < MAP_H * MAP_W / 32; j++)
            state->seen[j] = 0;
        // Re-seed explore locations
        int16_t init_explore[4][2] = {{-7, 0}, {0, 7}, {7, 0}, {0, -7}};
        for (int j = 0; j < 4; j++) {
            state->explore_locs[j][0] = (int16_t)(init_explore[j][0] + MAP_W / 2);
            state->explore_locs[j][1] = (int16_t)(init_explore[j][1] + MAP_H / 2);
        }
        state->num_explore_locs = 4;
        for (int j = 3; j > 0; j--) {
            uint32_t r = xorshift32(&state->rng_state);
            int k = (int)(r % (uint32_t)(j + 1));
            int16_t t0 = state->explore_locs[j][0], t1 = state->explore_locs[j][1];
            state->explore_locs[j][0] = state->explore_locs[k][0];
            state->explore_locs[j][1] = state->explore_locs[k][1];
            state->explore_locs[k][0] = t0; state->explore_locs[k][1] = t1;
        }
        // Re-shuffle direction order
        state->offsets4_order[0] = 0; state->offsets4_order[1] = 1;
        state->offsets4_order[2] = 2; state->offsets4_order[3] = 3;
        for (int j = 3; j > 0; j--) {
            uint32_t r = xorshift32(&state->rng_state);
            int k = (int)(r % (uint32_t)(j + 1));
            uint8_t tmp = state->offsets4_order[j];
            state->offsets4_order[j] = state->offsets4_order[k];
            state->offsets4_order[k] = tmp;
        }
    }

    const uint8_t* my_obs = &obs[agent_id * T * 3];

    // 1. Update position BEFORE parsing (need old pos for map writes)
    //    But we need lp/last_action from obs first. Do a two-pass approach:
    //    First parse to get self features, then update position, then parse map.
    //    Actually, Nim does: parseVisible -> updateMap (which reads last_action
    //    from parsed visible). So parse first to get self features, update pos,
    //    then write map cells.

    // Parse observations: extracts self features AND writes to compact map
    // Position hasn't moved yet, so map writes use the OLD position.
    // We need to parse self features first, update position, then re-parse
    // the map portion with the new position.

    // Step 1: Quick scan for self features only (lp/last_action)
    SelfFeatures sf;
    init_self_features(&sf);

    int halfW = d_cfg.obs_half_w;
    int halfH = d_cfg.obs_half_h;

    for (int t = 0; t < T; t++) {
        uint8_t loc_packed = my_obs[t * 3];
        uint8_t feat_id    = my_obs[t * 3 + 1];
        uint8_t val        = my_obs[t * 3 + 2];
        if (loc_packed == 0xFF && feat_id == 0xFF && val == 0xFF) break;

        // Only process self/global tokens for position features
        bool is_self = false;
        if (loc_packed == 0xFE) {
            is_self = true;
        } else if (loc_packed != 0xFF) {
            int ry = (int)(loc_packed >> 4) - halfH;
            int rx = (int)(loc_packed & 0x0F) - halfW;
            if (rx == 0 && ry == 0) is_self = true;
        }
        if (is_self) {
            parse_self_feature(&sf, feat_id, val);
        }
    }

    // Step 2: Update position using parsed lp/last_action
    update_position(state, &sf);

    // Step 3: Full observation parse (writes to map using updated position)
    parse_observations(my_obs, T, state, &sf);

    // Step 4: Clear stale visible cells
    clear_visible_stale(state);

    // Step 5: Update action history from observed last_action
    state->last_action_1 = state->last_action_0;
    state->last_action_0 = (int8_t)sf.last_action;

    // Step 6: Decision tree
    int action = decision_tree(state, &sf);

    // Step 7: Write output
    actions[agent_id] = (int64_t)action;
}

// ---------------------------------------------------------------------------
// Host-side functions exposed to Python via pybind11
// ---------------------------------------------------------------------------

void set_config(
    // Action IDs
    int act_noop, int act_move_north, int act_move_south,
    int act_move_west, int act_move_east,
    int act_vibe_carbon_a, int act_vibe_carbon_b,
    int act_vibe_oxygen_a, int act_vibe_oxygen_b,
    int act_vibe_germanium_a, int act_vibe_germanium_b,
    int act_vibe_silicon_a, int act_vibe_silicon_b,
    int act_vibe_heart_a, int act_vibe_heart_b,
    int act_vibe_junction,
    // Feature IDs
    int feat_tag, int feat_group, int feat_vibe, int feat_last_action,
    int feat_inv_energy, int feat_inv_carbon, int feat_inv_oxygen,
    int feat_inv_germanium, int feat_inv_silicon, int feat_inv_heart,
    int feat_inv_decoder, int feat_inv_modulator,
    int feat_inv_resonator, int feat_inv_scrambler,
    int feat_remaining_uses,
    int feat_inv_carbon_p1, int feat_inv_carbon_p2,
    int feat_inv_oxygen_p1, int feat_inv_oxygen_p2,
    int feat_inv_germanium_p1, int feat_inv_germanium_p2,
    int feat_inv_silicon_p1, int feat_inv_silicon_p2,
    int feat_inv_heart_p1, int feat_inv_heart_p2,
    int feat_proto_input_carbon, int feat_proto_input_oxygen,
    int feat_proto_input_germanium, int feat_proto_input_silicon,
    int feat_proto_output_heart,
    int feat_lp_east, int feat_lp_west, int feat_lp_north, int feat_lp_south,
    // Tag IDs
    int tag_agent, int tag_wall, int tag_hub, int tag_chest, int tag_junction,
    int tag_carbon_ext, int tag_oxygen_ext, int tag_germanium_ext, int tag_silicon_ext,
    // Vibe IDs
    int vibe_default, int vibe_junction,
    int vibe_carbon_a, int vibe_carbon_b,
    int vibe_oxygen_a, int vibe_oxygen_b,
    int vibe_germanium_a, int vibe_germanium_b,
    int vibe_silicon_a, int vibe_silicon_b,
    int vibe_heart_a, int vibe_heart_b,
    // Observation dims
    int obs_half_w, int obs_half_h,
    int num_tokens, int token_dim,
    int inventory_token_base
) {
    EnvConfig cfg = {};

    cfg.act_noop = act_noop; cfg.act_move_north = act_move_north;
    cfg.act_move_south = act_move_south; cfg.act_move_west = act_move_west;
    cfg.act_move_east = act_move_east;
    cfg.act_vibe_carbon_a = act_vibe_carbon_a; cfg.act_vibe_carbon_b = act_vibe_carbon_b;
    cfg.act_vibe_oxygen_a = act_vibe_oxygen_a; cfg.act_vibe_oxygen_b = act_vibe_oxygen_b;
    cfg.act_vibe_germanium_a = act_vibe_germanium_a; cfg.act_vibe_germanium_b = act_vibe_germanium_b;
    cfg.act_vibe_silicon_a = act_vibe_silicon_a; cfg.act_vibe_silicon_b = act_vibe_silicon_b;
    cfg.act_vibe_heart_a = act_vibe_heart_a; cfg.act_vibe_heart_b = act_vibe_heart_b;
    cfg.act_vibe_junction = act_vibe_junction;

    cfg.feat_tag = feat_tag; cfg.feat_group = feat_group;
    cfg.feat_vibe = feat_vibe; cfg.feat_last_action = feat_last_action;
    cfg.feat_inv_energy = feat_inv_energy; cfg.feat_inv_carbon = feat_inv_carbon;
    cfg.feat_inv_oxygen = feat_inv_oxygen;
    cfg.feat_inv_germanium = feat_inv_germanium; cfg.feat_inv_silicon = feat_inv_silicon;
    cfg.feat_inv_heart = feat_inv_heart;
    cfg.feat_inv_decoder = feat_inv_decoder; cfg.feat_inv_modulator = feat_inv_modulator;
    cfg.feat_inv_resonator = feat_inv_resonator; cfg.feat_inv_scrambler = feat_inv_scrambler;
    cfg.feat_remaining_uses = feat_remaining_uses;
    cfg.feat_inv_carbon_p1 = feat_inv_carbon_p1; cfg.feat_inv_carbon_p2 = feat_inv_carbon_p2;
    cfg.feat_inv_oxygen_p1 = feat_inv_oxygen_p1; cfg.feat_inv_oxygen_p2 = feat_inv_oxygen_p2;
    cfg.feat_inv_germanium_p1 = feat_inv_germanium_p1; cfg.feat_inv_germanium_p2 = feat_inv_germanium_p2;
    cfg.feat_inv_silicon_p1 = feat_inv_silicon_p1; cfg.feat_inv_silicon_p2 = feat_inv_silicon_p2;
    cfg.feat_inv_heart_p1 = feat_inv_heart_p1; cfg.feat_inv_heart_p2 = feat_inv_heart_p2;
    cfg.feat_proto_input_carbon = feat_proto_input_carbon;
    cfg.feat_proto_input_oxygen = feat_proto_input_oxygen;
    cfg.feat_proto_input_germanium = feat_proto_input_germanium;
    cfg.feat_proto_input_silicon = feat_proto_input_silicon;
    cfg.feat_proto_output_heart = feat_proto_output_heart;
    cfg.feat_lp_east = feat_lp_east; cfg.feat_lp_west = feat_lp_west;
    cfg.feat_lp_north = feat_lp_north; cfg.feat_lp_south = feat_lp_south;

    cfg.tag_agent = tag_agent; cfg.tag_wall = tag_wall;
    cfg.tag_hub = tag_hub; cfg.tag_chest = tag_chest; cfg.tag_junction = tag_junction;
    cfg.tag_carbon_ext = tag_carbon_ext; cfg.tag_oxygen_ext = tag_oxygen_ext;
    cfg.tag_germanium_ext = tag_germanium_ext; cfg.tag_silicon_ext = tag_silicon_ext;

    cfg.vibe_default = vibe_default; cfg.vibe_junction = vibe_junction;
    cfg.vibe_carbon_a = vibe_carbon_a; cfg.vibe_carbon_b = vibe_carbon_b;
    cfg.vibe_oxygen_a = vibe_oxygen_a; cfg.vibe_oxygen_b = vibe_oxygen_b;
    cfg.vibe_germanium_a = vibe_germanium_a; cfg.vibe_germanium_b = vibe_germanium_b;
    cfg.vibe_silicon_a = vibe_silicon_a; cfg.vibe_silicon_b = vibe_silicon_b;
    cfg.vibe_heart_a = vibe_heart_a; cfg.vibe_heart_b = vibe_heart_b;

    cfg.obs_half_w = obs_half_w; cfg.obs_half_h = obs_half_h;
    cfg.num_tokens = num_tokens; cfg.token_dim = token_dim;
    cfg.inventory_token_base = inventory_token_base;

    cudaMemcpyToSymbol(d_cfg, &cfg, sizeof(EnvConfig));
}

// Agent state initialization kernel
__global__ void init_agent_states_kernel(AgentState* states, int N) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= N) return;
    AgentState* s = &states[i];
    s->first_step = 1;
    s->num_specials = 0;
    s->num_explore_locs = 0;
    s->last_action_0 = -1;
    s->last_action_1 = -1;
    s->pos_x = 0;
    s->pos_y = 0;
    s->seen_hub = 0;
    s->seen_chest = 0;
    s->rng_state = (uint32_t)(i + 1);
    for (int y = 0; y < MAP_H; y++) {
        for (int x = 0; x < MAP_W; x++) {
            s->map[y][x].tag = -1;
            s->map[y][x].flags = 0;
        }
    }
    // Zero seen bitfield
    for (int j = 0; j < MAP_H * MAP_W / 32; j++) {
        s->seen[j] = 0;
    }
    // Resource targets
    s->carbon_target = 0;
    s->oxygen_target = 0;
    s->germanium_target = 0;
    s->silicon_target = 0;
    // Exploration locations
    int16_t init_explore[4][2] = {{-7, 0}, {0, 7}, {7, 0}, {0, -7}};
    for (int j = 0; j < 4; j++) {
        s->explore_locs[j][0] = (int16_t)(init_explore[j][0] + MAP_W / 2);
        s->explore_locs[j][1] = (int16_t)(init_explore[j][1] + MAP_H / 2);
    }
    s->num_explore_locs = 4;
    for (int j = 3; j > 0; j--) {
        uint32_t r = xorshift32(&s->rng_state);
        int k = (int)(r % (uint32_t)(j + 1));
        int16_t t0 = s->explore_locs[j][0], t1 = s->explore_locs[j][1];
        s->explore_locs[j][0] = s->explore_locs[k][0];
        s->explore_locs[j][1] = s->explore_locs[k][1];
        s->explore_locs[k][0] = t0; s->explore_locs[k][1] = t1;
    }
    s->offsets4_order[0] = 0; s->offsets4_order[1] = 1;
    s->offsets4_order[2] = 2; s->offsets4_order[3] = 3;
    for (int j = 3; j > 0; j--) {
        uint32_t r = xorshift32(&s->rng_state);
        int k = (int)(r % (uint32_t)(j + 1));
        uint8_t tmp = s->offsets4_order[j];
        s->offsets4_order[j] = s->offsets4_order[k];
        s->offsets4_order[k] = tmp;
    }
    // Zero special cells
    for (int j = 0; j < MAX_SPECIAL_CELLS; j++) {
        s->specials[j] = {};
    }
}

// Wrapper that calls the init kernel
torch::Tensor init_states_impl(int num_agents, torch::Device device) {
    int64_t bytes = (int64_t)num_agents * sizeof(AgentState);
    auto options = torch::TensorOptions().dtype(torch::kUInt8).device(device);
    auto states = torch::empty({bytes}, options);

    AgentState* ptr = reinterpret_cast<AgentState*>(states.data_ptr<uint8_t>());
    int threads = 128;
    int blocks = (num_agents + threads - 1) / threads;
    init_agent_states_kernel<<<blocks, threads>>>(ptr, num_agents);

    return states;
}

void teacher_step(
    torch::Tensor observations,  // [N, T, 3] uint8
    torch::Tensor actions,       // [N] int64
    torch::Tensor states_flat,   // flat byte tensor holding AgentState[N]
    torch::optional<torch::Tensor> dones  // [N] bool, optional
) {
    TORCH_CHECK(observations.is_cuda(), "observations must be on CUDA");
    TORCH_CHECK(actions.is_cuda(), "actions must be on CUDA");
    TORCH_CHECK(states_flat.is_cuda(), "states must be on CUDA");
    TORCH_CHECK(observations.dtype() == torch::kUInt8, "observations must be uint8");
    TORCH_CHECK(actions.dtype() == torch::kInt64, "actions must be int64");

    int N = observations.size(0);
    int T = observations.size(1);

    const uint8_t* obs_ptr = observations.data_ptr<uint8_t>();
    int64_t* act_ptr = actions.data_ptr<int64_t>();
    AgentState* state_ptr = reinterpret_cast<AgentState*>(states_flat.data_ptr<uint8_t>());

    const bool* dones_ptr = nullptr;
    if (dones.has_value() && dones->defined()) {
        TORCH_CHECK(dones->is_cuda(), "dones must be on CUDA");
        TORCH_CHECK(dones->dtype() == torch::kBool, "dones must be bool");
        dones_ptr = dones->data_ptr<bool>();
    }

    int threads = 128;
    int blocks = (N + threads - 1) / threads;
    thinky_astar_thread<<<blocks, threads>>>(obs_ptr, act_ptr, state_ptr, dones_ptr, N, T);
}

// ---------------------------------------------------------------------------
// pybind11 module
// ---------------------------------------------------------------------------

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
    m.def("set_config", &set_config, "Upload EnvConfig to CUDA constant memory");
    m.def("init_states", &init_states_impl, "Allocate and initialize agent states on GPU");
    m.def("teacher_step", &teacher_step, "Run one thinky step for all agents");
}
