# General Agent Substrate Formalization

This document records the full end-state mathematical target for the General Agent Substrate.

The implementation plans under `docs/user/subho/gas/` stage that target into reviewable phases and may intentionally
defer parts of the full formalization, especially communication cost, intrinsic reward, and the optional local fabric
backend.

This document is the normative mathematical reference for the design. If any plan breakdown describes a narrower
baseline, proxy target, or staged implementation slice, the formalization in this document takes precedence.

## Overview

We define a cooperative multi-agent recurrent substrate with \(N\) agents. Each agent is a multiscale recurrent cortex
executed for \(K\) internal thinking steps per environment step. Agents communicate by emitting vibe actions, which
the environment transforms into vibe observations for other agents.

To reduce loss interference, the cortex is split at layer \(L_s\):

- layers \(1,\dots,L_s\) are shared across objectives
- layers \(L_s+1,\dots,L\) are route-specific

We use the route set

$$
\mathcal R = \{\mathrm{RL}, \mathrm{WM}, \mathrm{SF}\},
$$

corresponding to:

- control: task action, vibe action, value
- world modeling
- successor features

Thus the model keeps a common lower-level substrate while allowing objective-specific upper recurrent circuits.

Instead of writing explicit copy or carry equations at skipped inner steps, each layer is formulated as a
sequence-processing recurrent operator:

$$
h_{\mathrm{out}},\; Y_{1:U} = \mathrm{RNNLayer}(X_{1:U}, h_{\mathrm{in}}),
$$

where the input sequence \(X_{1:U}\) is formed by repeating observations or selecting schedule-aligned outputs of
lower layers. This keeps the recurrence inside the layer operator and makes the execution compatible with ordinary
batched sequence kernels.

## 1. Environment Time, Agents, Observations, And Schedules

Let \(t=1,2,\dots\) index environment steps, and let \(i \in \{1,\dots,N\}\) index agents.

Each agent receives an observation

$$
o_t^{(i)} = \bigl(o_{t,\mathrm{env}}^{(i)},\; o_{t,\mathrm{vibe}}^{(i)}\bigr),
$$

where:

- \(o_{t,\mathrm{env}}^{(i)}\) is the ordinary task or environment observation
- \(o_{t,\mathrm{vibe}}^{(i)}\) is the social observation generated from other agents' previous vibe actions

Each layer \(\ell\) has an integer update period \(p_\ell\), with monotone timescale ordering

$$
p_1 \le p_2 \le \cdots \le p_L.
$$

We assume

$$
p_{\ell-1} \mid p_\ell \quad \text{for } \ell=2,\dots,L,
\qquad
p_\ell \mid K \quad \text{for all } \ell,
$$

so that inner-step schedules nest cleanly.

Define the number of actual updates performed by layer \(\ell\) per environment step as

$$
U_\ell := \frac{K}{p_\ell}.
$$

Thus lower layers process longer inner sequences and higher layers process shorter inner sequences.

## 2. Sequence Operators

We use two simple sequence operators.

For any vector \(z \in \mathbb R^d\), define the repetition operator

$$
\mathrm{Repeat}_U(z) := (z,\dots,z) \in \mathbb R^{U \times d}.
$$

For any sequence \(Y_{1:U} = (Y_1,\dots,Y_U)\) and stride \(s\) dividing \(U\), define the schedule-selection
operator

$$
\mathrm{Stride}_s(Y_{1:U}) := (Y_s, Y_{2s}, \dots, Y_U).
$$

When

$$
s_\ell := \frac{p_\ell}{p_{\ell-1}},
$$

the sequence seen by layer \(\ell\) is obtained by taking every \(s_\ell\)-th output from layer \(\ell-1\). This
replaces explicit copy equations: skipped inner steps are not materialized at the top level; instead, each layer
simply receives the subsequence corresponding to its own update schedule.

## 3. Shared Lower Cortex

For each shared layer \(\ell=1,\dots,L_s\) and agent \(i\), let \(h_t^{(\ell,i)}\) denote the recurrent carry state
passed from environment step \(t-1\) to \(t\), and let

$$
Y_{t,1:U_\ell}^{(\ell,i)} =
\bigl(Y_{t,1}^{(\ell,i)}, \dots, Y_{t,U_\ell}^{(\ell,i)}\bigr)
$$

denote the output sequence produced by layer \(\ell\) during environment step \(t\).

The bottom shared layer consumes the repeated current observation:

$$
X_{t,1:U_1}^{(1,i)} = \mathrm{Repeat}_{U_1}\bigl(o_t^{(i)}\bigr).
$$

The layer update is

$$
h_t^{(1,i)},\; Y_{t,1:U_1}^{(1,i)}
=
\mathrm{RNNLayer}_1\!\left(
X_{t,1:U_1}^{(1,i)},
h_{t-1}^{(1,i)}
\right).
$$

For higher shared layers \(\ell=2,\dots,L_s\), define

$$
s_\ell := \frac{p_\ell}{p_{\ell-1}},
\qquad
X_{t,1:U_\ell}^{(\ell,i)}
=
\mathrm{Stride}_{s_\ell}\!\left(
Y_{t,1:U_{\ell-1}}^{(\ell-1,i)}
\right),
$$

and update

$$
h_t^{(\ell,i)},\; Y_{t,1:U_\ell}^{(\ell,i)}
=
\mathrm{RNNLayer}_\ell\!\left(
X_{t,1:U_\ell}^{(\ell,i)},
h_{t-1}^{(\ell,i)}
\right).
$$

The final refined shared-layer output at environment step \(t\) is the last element of the layer sequence:

$$
y_t^{(\ell,i)} := Y_{t,U_\ell}^{(\ell,i)},
\qquad
\ell=1,\dots,L_s.
$$

Thus the shared lower cortex is a stack of sequence-processing recurrent layers, each operating at its own effective
inner timescale.

## 4. Route-Specialized Upper Cortex

For each route \(r \in \mathcal R\), upper layer \(\ell=L_s+1,\dots,L\), and agent \(i\), let
\(h_t^{(\ell,i,r)}\) denote the route-specific recurrent carry state, and let
\(Y_{t,1:U_\ell}^{(\ell,i,r)}\) denote the route-specific output sequence at layer \(\ell\) during environment
step \(t\).

The first route-specific layer consumes the shared boundary sequence at the appropriate stride:

$$
s_{L_s+1} := \frac{p_{L_s+1}}{p_{L_s}},
\qquad
X_{t,1:U_{L_s+1}}^{(L_s+1,i,r)}
=
\mathrm{Stride}_{s_{L_s+1}}\!\left(
Y_{t,1:U_{L_s}}^{(L_s,i)}
\right).
$$

For \(\ell=L_s+2,\dots,L\), define

$$
s_\ell := \frac{p_\ell}{p_{\ell-1}},
\qquad
X_{t,1:U_\ell}^{(\ell,i,r)}
=
\mathrm{Stride}_{s_\ell}\!\left(
Y_{t,1:U_{\ell-1}}^{(\ell-1,i,r)}
\right).
$$

Each route-specific layer updates as

$$
h_t^{(\ell,i,r)},\; Y_{t,1:U_\ell}^{(\ell,i,r)}
=
\mathrm{RNNLayer}_{\ell,r}\!\left(
X_{t,1:U_\ell}^{(\ell,i,r)},
h_{t-1}^{(\ell,i,r)}
\right).
$$

The final routed top-layer states are

$$
y_t^{(L,i,\mathrm{RL})} := Y_{t,U_L}^{(L,i,\mathrm{RL})},
$$

$$
y_t^{(L,i,\mathrm{WM})} := Y_{t,U_L}^{(L,i,\mathrm{WM})},
$$

$$
y_t^{(L,i,\mathrm{SF})} := Y_{t,U_L}^{(L,i,\mathrm{SF})}.
$$

So the model has:

- one shared lower recurrent substrate
- three specialized upper recurrent circuits

## 5. Dual Policy Heads: Task Action And Vibe Action

The RL route is the control route. From the refined RL top-layer state, each agent emits:

- a task action
- a vibe action
- a value estimate

The task action policy is

$$
a_t^{(i)} \sim \pi_a\!\left(\cdot \mid y_t^{(L,i,\mathrm{RL})}\right),
$$

the vibe action policy is

$$
v_t^{(i)} \sim \pi_v\!\left(\cdot \mid y_t^{(L,i,\mathrm{RL})}\right),
$$

and the value function is

$$
V_t^{(i)} = V_\phi\!\left(y_t^{(L,i,\mathrm{RL})}\right).
$$

Thus both task behavior and communication are driven by the RL route.

## 6. Vibe Observation Dynamics

The environment transforms joint vibe actions into next-step vibe observations. For each agent \(i\),

$$
o_{t+1,\mathrm{vibe}}^{(i)}
=
\Omega^{(i)}\!\left(
v_t^{(1)},\dots,v_t^{(N)}
\right).
$$

The next total observation is then

$$
o_{t+1}^{(i)}
=
\bigl(
o_{t+1,\mathrm{env}}^{(i)},
\; o_{t+1,\mathrm{vibe}}^{(i)}
\bigr).
$$

So communication is treated as part of the environment dynamics:

$$
\bigl(o_{t+1}^{(1:N)}, r_t^{(1:N)}\bigr)
\sim
P\!\left(
\cdot \mid
o_t^{(1:N)},
a_t^{(1:N)},
v_t^{(1:N)}
\right).
$$

This keeps communication simple: agents act, including via vibe actions, and the environment returns the resulting
social observations.

## 7. Communication Budget

To prevent the vibe channel from becoming either ignored or an unconstrained high-bandwidth shortcut, define a
communication cost on vibe actions.

For each agent \(i\),

$$
c_t^{\mathrm{comm},(i)} = C\!\left(v_t^{(i)}\right).
$$

A simple default for continuous vibe vectors is

$$
C\!\left(v_t^{(i)}\right) = \lVert v_t^{(i)} \rVert_2^2.
$$

Then define the total reward used for learning as

$$
r_t^{\mathrm{tot},(i)}
=
r_t^{\mathrm{ext},(i)}
+
r_t^{\mathrm{int},(i)}
-
\beta_{\mathrm{comm}} \, c_t^{\mathrm{comm},(i)},
$$

where \(\beta_{\mathrm{comm}} \ge 0\) is the communication-budget hyperparameter.

Interpretation:

- \(\beta_{\mathrm{comm}}=0\): communication is free
- larger \(\beta_{\mathrm{comm}}\): communication becomes more expensive
- communication must improve reward enough to justify itself

## 8. World-Model Route

The world-model branch reads from the WM route. For each agent \(i\),

$$
\hat y_{t+1}^{(L,i,\mathrm{WM})},
\;
\hat r_t^{\mathrm{wm},(i)},
\;
\hat o_{t+1,\mathrm{vibe}}^{(i)}
=
M_\eta\!\left(
y_t^{(L,i,\mathrm{WM})},
a_t^{(i)},
v_t^{(i)}
\right).
$$

This branch predicts:

- the next routed WM top-layer state
- the immediate reward
- the next vibe observation

The corresponding auxiliary loss is

$$
\mathcal L_{\mathrm{wm}}
=
\sum_{i=1}^N
\Big[
\lambda_y
\left\lVert
\hat y_{t+1}^{(L,i,\mathrm{WM})}
-
y_{t+1}^{(L,i,\mathrm{WM})}
\right\rVert_2^2
+
\lambda_r^{\mathrm{wm}}
\,
\ell_r\!\left(
\hat r_t^{\mathrm{wm},(i)},
r_t^{(i)}
\right)
+
\lambda_v
\left\lVert
\hat o_{t+1,\mathrm{vibe}}^{(i)}
-
o_{t+1,\mathrm{vibe}}^{(i)}
\right\rVert_2^2
\Big].
$$

So the world model is predictive, but it no longer has to use exactly the same upper recurrent circuit as control.

## 9. Successor-Feature Route

The SF branch reads from the SF route. For each agent \(i\), define

$$
\phi_t^{(i)} = P_{\mathrm{sf}}\!\left(y_t^{(L,i,\mathrm{SF})}\right),
\qquad
\psi_t^{(i)} = G_{\mathrm{sf}}\!\left(y_t^{(L,i,\mathrm{SF})}\right).
$$

The SF branch includes a linear reward head

$$
\hat r_t^{\mathrm{sf},(i)} = w^\top \phi_t^{(i)}.
$$

The SF reward loss is

$$
\mathcal L_{\mathrm{sf\text{-}r}}
=
\sum_{i=1}^N
\left\lVert
\hat r_t^{\mathrm{sf},(i)} - r_t^{(i)}
\right\rVert_2^2.
$$

For each agent, the SF predictor satisfies the fixed-point relation

$$
\psi^{\pi,(i)}\!\left(y_t^{(L,i,\mathrm{SF})}\right)
\approx
\phi_t^{(i)}
+
\gamma
\mathbb E_\pi
\!\left[
\psi^{\pi,(i)}\!\left(y_{t+1}^{(L,i,\mathrm{SF})}\right)
\right].
$$

Define the SF TD residual

$$
\delta_t^{\mathrm{sf},(i)}
=
\phi_t^{(i)}
+
\gamma \psi_{t+1}^{(i)}
-
\psi_t^{(i)}.
$$

Rather than writing target-network clutter, define SF learning abstractly as a GTD-style update:

$$
(\theta_{\mathrm{sf}}, \nu_{\mathrm{sf}})
\leftarrow
\mathrm{GTD}_{\mathrm{sf}}
\!\left(
\theta_{\mathrm{sf}},
\nu_{\mathrm{sf}};
\{y_t^{(L,i,\mathrm{SF})},
y_{t+1}^{(L,i,\mathrm{SF})},
\phi_t^{(i)},
\psi_t^{(i)},
\psi_{t+1}^{(i)}\}_{i=1}^N
\right).
$$

Thus SF remains a predictive abstraction branch, but it also gets its own upper recurrent circuit.

## 10. Intrinsic Exploration

For each agent \(i\), define an intrinsic reward from change in successor structure:

$$
r_t^{\mathrm{int},(i)}
=
\kappa
\left\lVert
\psi_{t+\Delta}^{(i)} - \psi_t^{(i)}
\right\rVert_2^2.
$$

This intrinsic reward is added to external reward before subtracting the communication cost:

$$
r_t^{\mathrm{tot},(i)}
=
r_t^{\mathrm{ext},(i)}
+
r_t^{\mathrm{int},(i)}
-
\beta_{\mathrm{comm}} c_t^{\mathrm{comm},(i)}.
$$

So the learning signal balances:

- task reward
- exploration pressure
- communication budget

## 11. Actor-Critic Objective

The RL route is trained by a multi-agent actor-critic objective:

$$
\mathcal L_{\mathrm{RL}}
=
\sum_{i=1}^N
\Big[
\mathcal L_{\mathrm{pg}}^{(i)}
+
c_V \, \mathcal L_{\mathrm{value}}^{(i)}
-
\alpha_a \,
\mathbb E\big[
\mathcal H(\pi_a(\cdot \mid y_t^{(L,i,\mathrm{RL})}))
\big]
-
\alpha_v \,
\mathbb E\big[
\mathcal H(\pi_v(\cdot \mid y_t^{(L,i,\mathrm{RL})}))
\big]
\Big],
$$

computed using returns or targets derived from \(r_t^{\mathrm{tot},(i)}\).

This allows separate entropy regularization for:

- task-action exploration
- vibe-action exploration

## 12. Total Scalar Objective And Update Structure

Define the ordinary scalar objective

$$
\mathcal L_{\mathrm{scalar}}
=
\mathcal L_{\mathrm{RL}}
+
\lambda_{\mathrm{wm}} \, \mathcal L_{\mathrm{wm}}
+
\lambda_{\mathrm{sfr}} \, \mathcal L_{\mathrm{sf\text{-}r}}.
$$

Then training is defined by the coupled update scheme

$$
\theta
\leftarrow
\mathrm{Opt}\!\left(
\theta;\mathcal L_{\mathrm{scalar}}
\right),
$$

$$
(\theta_{\mathrm{sf}}, \nu_{\mathrm{sf}})
\leftarrow
\mathrm{GTD}_{\mathrm{sf}}(\cdots).
$$

Here \(\theta\) contains the ordinary differentiable parameters of:

- the shared lower cortex
- the RL upper route
- the WM upper route
- the SF upper route
- the task-action and vibe-action policies
- the value function
- the world model

The SF parameters also participate in the GTD-style update through \((\theta_{\mathrm{sf}}, \nu_{\mathrm{sf}})\).

## 13. Rollout-State Execution And Batched Training Layout

This formulation is intended to match how recurrent layers are typically implemented in practice.

### 13.1 Rollout-Time Execution

At rollout time, recurrence is carried across environment steps, not manually across every skipped inner microstep in
top-level code.

For each agent \(i\), route \(r\) when applicable, and layer \(\ell\), the runtime keeps only the carry state

$$
h_{t-1}^{(\ell,i)}
\quad\text{or}\quad
h_{t-1}^{(\ell,i,r)}
$$

from the previous environment step.

At the current environment step \(t\), the runtime forms the layer input sequence by:

- repeating the current observation or boundary activation when the environment input is constant across inner thinking
- selecting the schedule-aligned subsequence of lower-layer outputs using \(\mathrm{Stride}_{s_\ell}\)

Then it applies the layer operator once:

$$
h_t^{(\ell,i)},\; Y_{t,1:U_\ell}^{(\ell,i)}
=
\mathrm{RNNLayer}_\ell\!\left(
X_{t,1:U_\ell}^{(\ell,i)},
h_{t-1}^{(\ell,i)}
\right),
$$

or the route-specific analogue.

Thus the per-step inner thinking is represented as a short sequence processed by the layer kernel. The explicit copy
equations are replaced by repetition and subsequence selection at the input level.

### 13.2 Batched PPO Training

Suppose a collected rollout has batch shape \(B \times T\), where \(B\) indexes environments, agent-batches, or
flattened environment-agent pairs, and \(T\) indexes environment time.

For each layer \(\ell\), define the per-step input sequence \(X_{t,1:U_\ell}^{(\ell)}\) as above, and pack the rollout
into a single batched sequence by concatenating the inner sequence axis into time:

$$
\mathrm{Pack}_\ell
\!\left(
X_{1:T,\;,1:U_\ell}^{(\ell)}
\right)
\in
\mathbb R^{B \times (T U_\ell) \times d_\ell}.
$$

Then the layer can be run with the standard batched sequence interface

$$
H_{\mathrm{final}}^{(\ell)},\; \bar Y^{(\ell)}
=
\mathrm{RNNLayer}_\ell\!\left(
\mathrm{Pack}_\ell(X^{(\ell)}),
H_{\mathrm{init}}^{(\ell)}
\right).
$$

So in batched training:

- the bottom layer typically sees an effective sequence length \(T U_1\)
- in the common case \(p_1=1\), this is \(T K\)
- higher layers see shorter effective lengths \(T U_\ell = T K / p_\ell\)

Equivalently, fixed \(K\) turns each outer environment step into an inner sequence block, and training packs the outer
and inner axes together into a larger sequence axis. This is exactly the setting most sequence kernels expect:
\(B \times T' \times H\).

In plain language:

- rollout carries recurrent state across outer environment time
- per-step thinking is expressed by repeating observations or lower-layer activations into a length-\(U_\ell\) sequence
- batched training can flatten the outer and inner axes into an effective time axis of length \(T U_\ell\)

For linear or otherwise scan-friendly recurrent layers, the packed time axis can additionally be parallelized by the
layer's native sequence algorithm. The formulation itself does not require any particular scan method; it only exposes
the computation in the standard sequence form that such kernels expect.

## 14. Optional Route-Consistency Regularization

If the routed upper circuits drift too far apart, add a weak consistency regularizer near the split boundary.

For example, on the first routed layer:

$$
\mathcal L_{\mathrm{cons}}
=
\lambda_{\mathrm{cons}}
\sum_{i=1}^N
\Big(
\left\lVert
y_t^{(L_s+1,i,\mathrm{WM})}
-
\mathrm{sg}\!\big[y_t^{(L_s+1,i,\mathrm{RL})}\big]
\right\rVert_2^2
+
\left\lVert
y_t^{(L_s+1,i,\mathrm{SF})}
-
\mathrm{sg}\!\big[y_t^{(L_s+1,i,\mathrm{RL})}\big]
\right\rVert_2^2
\Big).
$$

Then the scalar objective becomes

$$
\mathcal L_{\mathrm{scalar}}
=
\mathcal L_{\mathrm{RL}}
+
\lambda_{\mathrm{wm}} \, \mathcal L_{\mathrm{wm}}
+
\lambda_{\mathrm{sfr}} \, \mathcal L_{\mathrm{sf\text{-}r}}
+
\mathcal L_{\mathrm{cons}}.
$$

This term is optional. The clean baseline is to omit it and add it only if routes drift into separate representational
planets.

---

# 15. Optional: Local Inter-Layer Fabric Via Masked Cross-Attention

As an optional structured alternative to direct strided layer transfer, define a local inter-layer fabric in which
each cell receives messages from a masked neighborhood of nearby cells across the same layer and adjacent layers.

This replaces rigid direct transfer with a learned local routing mechanism while preserving parallel updates across
layers within each internal thinking step.

This section is orthogonal to the route split above. It replaces the direct layer-to-layer sequence construction rules
in Sections 3 and 4 with a masked local message-passing fabric inside each environment-step inner computation.

## 15.1 Layer Cells And Cortex-Style Update

Let \(t\) index environment steps, \(k \in \{1,\dots,K\}\) index internal thinking steps,
\(\ell \in \{1,\dots,L\}\) index layers, and \(j \in \{1,\dots,C_\ell\}\) index cells within layer \(\ell\).

Each cell \((\ell,j)\) is a recurrent Cortex module with output \(Y_{t,\ell,j}^{(k)}\) and private recurrent state
\(S_{t,\ell,j}^{(k)}\). Its update has the standard Cortex form

$$
Y_{t,\ell,j}^{(k)},\; S_{t,\ell,j}^{(k)}
=
\mathrm{Cell}_{\ell,j}\!\left(
X_{t,\ell,j}^{(k)},
S_{t,\ell,j}^{(k-1)}
\right).
$$

Initialization at the start of environment step \(t\) is

$$
S_{t,\ell,j}^{(0)} := S_{t-1,\ell,j},
\qquad
Y_{t,\ell,j}^{(0)} := Y_{t-1,\ell,j}.
$$

Thus inner thinking refines the cell outputs over \(k=1,\dots,K\).

## 15.2 Public Interface Vectors

Each cell exposes a smaller public interface vector used for fabric communication:

$$
Z_{t,\ell,j}^{(k)} = P_\ell\!\left(Y_{t,\ell,j}^{(k)}\right).
$$

Here:

- \(Y_{t,\ell,j}^{(k)}\) is the full private working state or output
- \(Z_{t,\ell,j}^{(k)}\) is the public signal visible to nearby cells

## 15.3 Fixed Receiver Slots

Each receiver cell \((\ell,j)\) has a learned slot embedding

$$
u_{\ell,j} \in \mathbb R^{d_u}.
$$

This slot embedding defines the receiver's identity and is used to form its query:

$$
q_{\ell,j} = W_Q u_{\ell,j}.
$$

Thus receiver queries are fixed learned functions of cell identity, rather than being generated dynamically from a
partially updated receiver state.

## 15.4 Sender Keys And Values

For each sender cell \((m,i)\), define key and value projections from the previous-snapshot interface vector:

$$
k_{t,m,i}^{(k-1)} = W_K Z_{t,m,i}^{(k-1)},
\qquad
v_{t,m,i}^{(k-1)} = W_V Z_{t,m,i}^{(k-1)}.
$$

These are computed from the frozen snapshot at thinking step \(k-1\).

## 15.5 Local Box Mask

Each receiver cell \((\ell,j)\) is allowed to attend only to a local neighborhood of cells in the same layer and
adjacent layers.

Let \(C_\ell\) denote the number of cells in layer \(\ell\). Define the proportional index map

$$
\pi_{m\to\ell}(j)
=
\left\lfloor
j \cdot \frac{C_m}{C_\ell}
\right\rfloor.
$$

Let \(r_{-1}, r_0, r_{+1}\) denote the radii for the lower layer, same layer, and upper layer respectively.

Define the attention mask

$$
\mathcal M_{\ell,j;m,i}
=
\begin{cases}
0, &
\text{if } |m-\ell| \le 1
\text{ and }
\left|i-\pi_{m\to\ell}(j)\right| \le r_{m-\ell},
\\
-\infty, &
\text{otherwise.}
\end{cases}
$$

Thus receiver \((\ell,j)\) may only read from:

- nearby cells in layer \(\ell-1\)
- nearby cells in layer \(\ell\)
- nearby cells in layer \(\ell+1\)

This defines a local box in the \((\text{layer}, \text{cell-position})\) lattice.

## 15.6 Masked Local Cross-Attention

Using the fixed receiver query and the sender keys and values, define masked local attention weights

$$
\alpha_{t,\ell,j;m,i}^{(k)}
=
\operatorname{softmax}_{m,i}
\left(
\frac{q_{\ell,j}^{\top} k_{t,m,i}^{(k-1)}}{\sqrt d}
+
\mathcal M_{\ell,j;m,i}
\right).
$$

The resulting local fabric message is

$$
X_{t,\ell,j}^{(k)}
=
\sum_{m=1}^{L}
\sum_{i=1}^{C_m}
\alpha_{t,\ell,j;m,i}^{(k)} \, v_{t,m,i}^{(k-1)}.
$$

Because the mask sets disallowed sender positions to \(-\infty\), this sum is effectively restricted to the local
box neighborhood.

This gives a unified message construction rule:

- same-layer local interaction
- bottom-up local interaction
- top-down local interaction

## 15.7 No Explicit Self-Output In The Mixer

The mixer does not separately take \(Y_{t,\ell,j}^{(k-1)}\) as an explicit self input. The cell's own history is
already preserved in the private recurrent state \(S_{t,\ell,j}^{(k-1)}\).

So the decomposition is:

- \(S_{t,\ell,j}^{(k-1)}\): private memory of the cell
- \(X_{t,\ell,j}^{(k)}\): incoming local neighborhood message

This keeps the public interface and private recurrence conceptually separate.

## 15.8 Parallel Synchronous Update

At thinking step \(k\), all layer-cell updates are computed from the frozen previous snapshot
\(\{Z_{t,m,i}^{(k-1)}, S_{t,m,i}^{(k-1)}\}_{m,i}\).

The update proceeds in three phases:

1. compute all public interface vectors

   $$
   Z_{t,\ell,j}^{(k-1)} = P_\ell\!\left(Y_{t,\ell,j}^{(k-1)}\right)
   $$

2. compute all masked local messages

   $$
   X_{t,\ell,j}^{(k)}
   $$

3. update all cells in parallel

   $$
   Y_{t,\ell,j}^{(k)},\; S_{t,\ell,j}^{(k)}
   =
   \mathrm{Cell}_{\ell,j}\!\left(
   X_{t,\ell,j}^{(k)},
   S_{t,\ell,j}^{(k-1)}
   \right)
   $$

Thus the inner thinking loop is sequential over \(k\), but parallel over layers and cells within each thinking step.
Equivalently, the dependency is isolated to the transition

$$
\{Z^{(k-1)}, S^{(k-1)}\} \to \{Z^{(k)}, S^{(k)}\},
$$

while all batch elements, rollout positions, layers, and cells can be processed simultaneously at fixed \(k\).

## 15.9 Schedule-Aligned Retained Sequences

The same schedule logic used in the base architecture can also be applied to the fabric outputs as a temporal
subsampling rule over inner thinking steps.

For each layer \(\ell\) and cell \(j\), define the retained public-interface sequence

$$
\bar Z_{t,\ell,j,1:U_\ell}
=
\mathrm{Stride}_{p_\ell}\!\left(
Z_{t,\ell,j}^{(1:K)}
\right),
$$

and similarly, if needed, the retained private-output sequence

$$
\bar Y_{t,\ell,j,1:U_\ell}
=
\mathrm{Stride}_{p_\ell}\!\left(
Y_{t,\ell,j}^{(1:K)}
\right).
$$

Thus the fabric may run on all inner thinking steps \(k=1,\dots,K\), while slower downstream modules, route heads, or
readouts consume only the schedule-aligned subsequence associated with their effective clock.

This does not replace the local mask. The mask determines where messages come from in the layer-cell lattice; stride
selection determines which inner-time snapshots are retained.

## 15.10 Batched \((B \times T)\) Execution For The Fabric

The fabric is also compatible with batched rollout training, but its execution pattern differs from the non-fabric
stacked version.

Suppose a collected rollout has batch shape \(B \times T\). At a fixed thinking step \(k\), the fabric state can be
organized as a tensor of the form

$$
[B,\; T,\; L,\; C,\; d],
$$

or any equivalent reshaping that preserves batch, rollout-time, layer, and cell axes.

Then at each fixed \(k\):

1. all interface vectors \(Z_{t,\ell,j}^{(k-1)}\) are computed in parallel over
   \(B \times T \times \ell \times j\)
2. all masked local messages \(X_{t,\ell,j}^{(k)}\) are computed in parallel over the same batched axes
3. all cell updates are applied in parallel over the same batched axes

So the fabric is parallel over \(B \times T\) at each inner thinking step, even though the inner thinking loop itself
remains sequential:

$$
k=1 \to 2 \to \cdots \to K.
$$

This is the key distinction:

- non-fabric stacked version: the inner sequence can be packed directly into a standard \(B \times T' \times H\)
  layer call
- fabric version: one typically keeps an explicit loop over \(k\), but each step of that loop is itself a large
  batched operation over \(B \times T\)

Thus the sequential dependency is decoupled from the batch and rollout axes because each cell uses the previous
thinking-step snapshot as input. The only strict causal dependency is

$$
(k-1) \to k,
$$

not between different batch items or rollout positions.

## 15.11 Final Refined State

After \(K\) internal thinking steps, define the refined cell outputs and states as

$$
Y_{t,\ell,j} := Y_{t,\ell,j}^{(K)},
\qquad
S_{t,\ell,j} := S_{t,\ell,j}^{(K)}.
$$

If schedule-aligned retained sequences are used, one may also define

$$
\bar Y_{t,\ell,j,1:U_\ell}
=
\mathrm{Stride}_{p_\ell}\!\left(
Y_{t,\ell,j}^{(1:K)}
\right)
$$

as the subsampled sequence exposed to slower heads or downstream modules.

These refined outputs can then feed the main readout modules exactly as in the base architecture.

For example, if the top layer is still the decision layer, its refined cell outputs can be pooled or projected into the
final decision state used by policy, value, world model, and successor features.

## Concise Definition

We define a cooperative multi-agent substrate in which each agent is a multiscale recurrent cortex executed for
\(K\) internal thinking steps per environment step and modulated by layer-dependent update periods \(p_\ell\). The
cortex is split into a shared lower substrate and route-specialized upper recurrent circuits for RL, world modeling,
and successor features. Instead of writing skipped inner updates as explicit copy equations, each layer is treated as a
sequence-processing recurrent operator: the current observation or shared boundary activation is repeated to form a
local inner sequence, lower-layer outputs are downsampled by schedule-aligned stride selection, and each layer
processes its own inner sequence through an ordinary \(\mathrm{RNNLayer}(X,h)\) interface. From the RL route's final
refined top-layer state, each agent emits both a task action and a vibe action. The environment maps joint vibe
actions into next-step vibe observations, so communication is treated as part of the transition dynamics. A
communication-cost term weighted by \(\beta_{\mathrm{comm}}\) controls channel use. The WM route predicts next routed
latent state, reward, and next vibe observation, while the SF route defines reward-relevant features and successor
features trained by a GTD-style update. In rollout, recurrent state is carried across outer environment steps; in
batched PPO training, the outer time axis and inner thinking axis can be packed into an effective sequence axis of
length \(T U_\ell\), typically \(T K\) for the bottom layer. The optional local inter-layer fabric replaces direct
strided transfer with masked local cross-attention between neighboring cells across adjacent layers, permits the same
schedule-aligned retained subsequences over inner thinking time, and remains parallel over batch and rollout axes at
each fixed thinking step even though the inner thinking loop itself is sequential over \(k\).
