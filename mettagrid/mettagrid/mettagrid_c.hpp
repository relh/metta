#ifndef METTAGRID_C_HPP
#define METTAGRID_C_HPP

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <map>
#include <memory>
#include <string>
#include <vector>

// Forward declarations of existing C++ classes
class Grid;
class EventManager;
class StatsTracker;
class ActionHandler;
class Agent;
class ObservationEncoder;
class GridObject;

namespace py = pybind11;

class MettaGrid {
public:
  MettaGrid(py::dict env_cfg, py::array map);
  ~MettaGrid();

  // Python API methods
  py::tuple reset();
  py::tuple step(py::array_t<int> actions);
  void set_buffers(std::reference_wrapper<py::array_t<unsigned char>> observations,
                   std::reference_wrapper<py::array_t<bool>> terminals,
                   std::reference_wrapper<py::array_t<bool>> truncations,
                   std::reference_wrapper<py::array_t<float>> rewards);
  py::dict grid_objects();
  py::list action_names();
  unsigned int current_timestep();
  unsigned int map_width();
  unsigned int map_height();
  py::list grid_features();
  unsigned int num_agents();
  py::array_t<float> get_episode_rewards();
  py::dict get_episode_stats();
  py::object action_space();
  py::object observation_space();
  py::list action_success();
  py::list max_action_args();
  py::list object_type_names();
  py::list inventory_item_names();
  static Agent* create_agent(int r,
                             int c,
                             const std::string& group_name,
                             unsigned int group_id,
                             const py::dict& group_cfg_py,
                             const py::dict& agent_cfg_py);

private:
  // Member variables
  py::dict _cfg;
  std::map<unsigned int, float> _group_reward_pct;
  std::map<unsigned int, unsigned int> _group_sizes;
  // TODO: it's not clear why we need two of these, or why they need to be numpy arrays.
  // See if we can change that.
  py::array_t<double> _group_rewards;
  std::unique_ptr<Grid> _grid;
  std::unique_ptr<EventManager> _event_manager;
  unsigned int _current_timestep;
  unsigned int _max_timestep;

  std::vector<std::unique_ptr<ActionHandler>> _action_handlers;
  int _num_action_handlers;
  std::vector<unsigned char> _max_action_args;
  unsigned char _max_action_arg;
  unsigned char _max_action_priority;

  std::unique_ptr<ObservationEncoder> _obs_encoder;
  std::unique_ptr<StatsTracker> _stats;

  unsigned short _obs_width;
  unsigned short _obs_height;

  // TODO: currently these are owned and destroyed by the grid, but we should
  // probably move ownership here.
  std::vector<Agent*> _agents;

  py::array_t<unsigned char> _observations;
  py::array_t<bool> _terminals;
  py::array_t<bool> _truncations;
  py::array_t<float> _rewards;
  py::array_t<float> _episode_rewards;

  std::vector<std::string> _grid_features;

  std::vector<bool> _action_success;

  void init_action_handlers();
  void add_agent(Agent* agent);
  void _compute_observation(unsigned int observer_r,
                            unsigned int observer_c,
                            unsigned short obs_width,
                            unsigned short obs_height,
                            size_t agent_idx);
  void _compute_observations(py::array_t<int> actions);
  void _step(py::array_t<int> actions);
};

#endif  // METTAGRID_C_HPP
