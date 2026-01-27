"use client";

import { useState } from "react";
import { H2 } from "../H2";

type MyPolicy = {
  policyName: string;
  score: number;
  submittedAt: string;
  status: string;
};

type PolicyMission = {
  mission: string;
  score: number;
  date: string;
};

type PolicyGame = {
  game: string;
  score: number;
};

type PoolResult = {
  poolId: number;
  date: string; // Format: MMM.DD.HH.MM (e.g., "Nov.19.12.31")
  results: {
    policyName: string;
    newScore: number;
    scoreDelta?: number; // optional, only ~1/3 of entries have this
  }[];
};

type PracticeMissionPlayer = {
  missionNumber: number;
  policyName: string;
  highScore: number;
};

// Placeholder data - will be replaced with database queries later
// Ordered descending: Pool #10 first, then #9, #8, etc. down to #1
// Each pool has incrementing number of policies: Pool #1 has 5, Pool #2 has 6, etc.
// Scores are between 10-230, only ~1/3 of entries have scoreDelta (-15 to +25)
const recentPools: PoolResult[] = [
  {
    poolId: 10,
    date: "Nov.28.18.20",
    results: [
      { policyName: "Policy_1", newScore: 187, scoreDelta: 18 },
      { policyName: "Policy_2", newScore: 142 },
      { policyName: "Policy_3", newScore: 203, scoreDelta: -8 },
      { policyName: "Policy_4", newScore: 165 },
      { policyName: "Policy_5", newScore: 128 },
      { policyName: "Policy_6", newScore: 219, scoreDelta: 22 },
      { policyName: "Policy_7", newScore: 91 },
      { policyName: "Policy_8", newScore: 156, scoreDelta: 12 },
      { policyName: "Policy_9", newScore: 178 },
      { policyName: "Policy_10", newScore: 134 },
      { policyName: "Policy_11", newScore: 195, scoreDelta: -12 },
      { policyName: "Policy_12", newScore: 167 },
      { policyName: "Policy_13", newScore: 148, scoreDelta: 7 },
      { policyName: "Policy_14", newScore: 211 },
    ],
  },
  {
    poolId: 9,
    date: "Nov.27.15.45",
    results: [
      { policyName: "Policy_1", newScore: 174, scoreDelta: 15 },
      { policyName: "Policy_2", newScore: 139 },
      { policyName: "Policy_3", newScore: 198, scoreDelta: -10 },
      { policyName: "Policy_4", newScore: 162 },
      { policyName: "Policy_5", newScore: 125 },
      { policyName: "Policy_6", newScore: 214, scoreDelta: 20 },
      { policyName: "Policy_7", newScore: 88 },
      { policyName: "Policy_8", newScore: 153, scoreDelta: 9 },
      { policyName: "Policy_9", newScore: 176 },
      { policyName: "Policy_10", newScore: 131 },
      { policyName: "Policy_11", newScore: 192, scoreDelta: -14 },
      { policyName: "Policy_12", newScore: 164 },
      { policyName: "Policy_13", newScore: 145, scoreDelta: 5 },
    ],
  },
  {
    poolId: 8,
    date: "Nov.26.12.30",
    results: [
      { policyName: "Policy_1", newScore: 181, scoreDelta: 17 },
      { policyName: "Policy_2", newScore: 136 },
      { policyName: "Policy_3", newScore: 201, scoreDelta: -9 },
      { policyName: "Policy_4", newScore: 168 },
      { policyName: "Policy_5", newScore: 122 },
      { policyName: "Policy_6", newScore: 217, scoreDelta: 23 },
      { policyName: "Policy_7", newScore: 94 },
      { policyName: "Policy_8", newScore: 159, scoreDelta: 11 },
      { policyName: "Policy_9", newScore: 173 },
      { policyName: "Policy_10", newScore: 133 },
      { policyName: "Policy_11", newScore: 194, scoreDelta: -13 },
      { policyName: "Policy_12", newScore: 166 },
    ],
  },
  {
    poolId: 7,
    date: "Nov.25.10.00",
    results: [
      { policyName: "Policy_1", newScore: 179, scoreDelta: 16 },
      { policyName: "Policy_2", newScore: 138 },
      { policyName: "Policy_3", newScore: 200, scoreDelta: -11 },
      { policyName: "Policy_4", newScore: 163 },
      { policyName: "Policy_5", newScore: 124 },
      { policyName: "Policy_6", newScore: 216, scoreDelta: 21 },
      { policyName: "Policy_7", newScore: 89 },
      { policyName: "Policy_8", newScore: 157, scoreDelta: 10 },
      { policyName: "Policy_9", newScore: 175 },
      { policyName: "Policy_10", newScore: 132 },
      { policyName: "Policy_11", newScore: 193, scoreDelta: -15 },
    ],
  },
  {
    poolId: 6,
    date: "Nov.24.22.15",
    results: [
      { policyName: "Policy_1", newScore: 183, scoreDelta: 19 },
      { policyName: "Policy_2", newScore: 141 },
      { policyName: "Policy_3", newScore: 202 },
      { policyName: "Policy_4", newScore: 169 },
      { policyName: "Policy_5", newScore: 123, scoreDelta: -7 },
      { policyName: "Policy_6", newScore: 218 },
      { policyName: "Policy_7", newScore: 92, scoreDelta: 13 },
      { policyName: "Policy_8", newScore: 158 },
      { policyName: "Policy_9", newScore: 177, scoreDelta: 14 },
      { policyName: "Policy_10", newScore: 135 },
    ],
  },
  {
    poolId: 5,
    date: "Nov.23.20.30",
    results: [
      { policyName: "Policy_1", newScore: 185, scoreDelta: 24 },
      { policyName: "Policy_2", newScore: 143 },
      { policyName: "Policy_3", newScore: 204 },
      { policyName: "Policy_4", newScore: 170, scoreDelta: -6 },
      { policyName: "Policy_5", newScore: 126 },
      { policyName: "Policy_6", newScore: 220 },
      { policyName: "Policy_7", newScore: 93, scoreDelta: 8 },
      { policyName: "Policy_8", newScore: 160 },
      { policyName: "Policy_9", newScore: 180, scoreDelta: 6 },
    ],
  },
  {
    poolId: 4,
    date: "Nov.22.18.10",
    results: [
      { policyName: "Policy_1", newScore: 182, scoreDelta: 25 },
      { policyName: "Policy_2", newScore: 140 },
      { policyName: "Policy_3", newScore: 205 },
      { policyName: "Policy_4", newScore: 171, scoreDelta: -5 },
      { policyName: "Policy_5", newScore: 127 },
      { policyName: "Policy_6", newScore: 221 },
      { policyName: "Policy_7", newScore: 95, scoreDelta: 4 },
      { policyName: "Policy_8", newScore: 161 },
    ],
  },
  {
    poolId: 3,
    date: "Nov.21.16.20",
    results: [
      { policyName: "Policy_1", newScore: 186, scoreDelta: 3 },
      { policyName: "Policy_2", newScore: 144 },
      { policyName: "Policy_3", newScore: 206, scoreDelta: -4 },
      { policyName: "Policy_4", newScore: 172 },
      { policyName: "Policy_5", newScore: 129 },
      { policyName: "Policy_6", newScore: 222 },
      { policyName: "Policy_7", newScore: 96, scoreDelta: 2 },
    ],
  },
  {
    poolId: 2,
    date: "Nov.20.14.45",
    results: [
      { policyName: "Policy_1", newScore: 188, scoreDelta: 1 },
      { policyName: "Policy_2", newScore: 146 },
      { policyName: "Policy_3", newScore: 207, scoreDelta: -3 },
      { policyName: "Policy_4", newScore: 173 },
      { policyName: "Policy_5", newScore: 130 },
      { policyName: "Policy_6", newScore: 223 },
    ],
  },
  {
    poolId: 1,
    date: "Nov.19.12.31",
    results: [
      { policyName: "Policy_1", newScore: 189, scoreDelta: -2 },
      { policyName: "Policy_2", newScore: 147 },
      { policyName: "Policy_3", newScore: 208, scoreDelta: -1 },
      { policyName: "Policy_4", newScore: 174 },
      { policyName: "Policy_5", newScore: 131 },
    ],
  },
];

const practiceMissions: PracticeMissionPlayer[] = [
  { missionNumber: 1, policyName: "Policy_1", highScore: 850 },
  { missionNumber: 2, policyName: "Policy_2", highScore: 620 },
  { missionNumber: 3, policyName: "Policy_3", highScore: 480 },
  { missionNumber: 4, policyName: "Policy_4", highScore: 350 },
  { missionNumber: 5, policyName: "Policy_5", highScore: 210 },
];

// Placeholder data for Private view
const myPolicies: MyPolicy[] = [
  {
    policyName: "My_Policy_1",
    score: 187,
    submittedAt: "Nov.28",
    status: "active",
  },
  {
    policyName: "My_Policy_2",
    score: 142,
    submittedAt: "Nov.27",
    status: "active",
  },
  {
    policyName: "My_Policy_3",
    score: 203,
    submittedAt: "Nov.26",
    status: "active",
  },
];

const policyMissions: Record<string, PolicyMission[]> = {
  My_Policy_1: [
    { mission: "Integrative Mission #1", score: 850, date: "Nov.28" },
    { mission: "Integrative Mission #2", score: 620, date: "Nov.27" },
    { mission: "Integrative Mission #3", score: 480, date: "Nov.26" },
    { mission: "Integrative Mission #4", score: 350, date: "Nov.25" },
    { mission: "Integrative Mission #5", score: 210, date: "Nov.24" },
  ],
  My_Policy_2: [
    { mission: "Integrative Mission #1", score: 750, date: "Nov.28" },
    { mission: "Integrative Mission #2", score: 520, date: "Nov.27" },
    { mission: "Integrative Mission #3", score: 380, date: "Nov.26" },
    { mission: "Integrative Mission #4", score: 250, date: "Nov.25" },
    { mission: "Integrative Mission #5", score: 110, date: "Nov.24" },
  ],
  My_Policy_3: [
    { mission: "Integrative Mission #1", score: 950, date: "Nov.28" },
    { mission: "Integrative Mission #2", score: 720, date: "Nov.27" },
    { mission: "Integrative Mission #3", score: 580, date: "Nov.26" },
    { mission: "Integrative Mission #4", score: 450, date: "Nov.25" },
    { mission: "Integrative Mission #5", score: 310, date: "Nov.24" },
  ],
};

const policyGames: Record<string, PolicyGame[]> = {
  My_Policy_1: [
    { game: "Game #1", score: 187 },
    { game: "Game #2", score: 192 },
    { game: "Game #3", score: 185 },
    { game: "Game #4", score: 190 },
  ],
  My_Policy_2: [
    { game: "Game #1", score: 142 },
    { game: "Game #2", score: 148 },
    { game: "Game #3", score: 145 },
    { game: "Game #4", score: 150 },
  ],
  My_Policy_3: [
    { game: "Game #1", score: 203 },
    { game: "Game #2", score: 198 },
    { game: "Game #3", score: 205 },
    { game: "Game #4", score: 200 },
  ],
};

function formatScoreDelta(delta: number): string {
  return delta >= 0 ? `+${delta}` : `${delta}`;
}

export function LeaderboardSection() {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isPrivate, setIsPrivate] = useState(false);
  const [selectedPolicy, setSelectedPolicy] = useState("beta");
  const visiblePools = isExpanded ? recentPools : recentPools.slice(0, 3);
  const hasMorePools = recentPools.length > 3;

  const filteredPolicies =
    selectedPolicy === "All"
      ? myPolicies
      : myPolicies.filter((p) => p.policyName === selectedPolicy);

  return (
    <section className="mt-8">
      <div className="mb-10 flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <H2>Leaderboard</H2>
          <select
            className="rounded-lg border border-[#d8d2bf] bg-[#fffef8] px-4 py-2 text-sm font-medium text-[#0e2758] focus:ring-2 focus:ring-[#4a5f8c] focus:outline-none"
            value={selectedPolicy}
            onChange={(e) => setSelectedPolicy(e.target.value)}
          >
            {isPrivate ? (
              <>
                <option value="All">All</option>
                <option value="My_Policy_1">My_Policy_1</option>
                <option value="My_Policy_2">My_Policy_2</option>
                <option value="My_Policy_3">My_Policy_3</option>
              </>
            ) : (
              <>
                <option value="beta">Beta policy pool</option>
                <option value="tournament" disabled>
                  Tournament policy pool
                </option>
                <option value="challengers" disabled>
                  Challengers policy pool
                </option>
              </>
            )}
          </select>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => {
              setIsPrivate(false);
              setSelectedPolicy("beta");
            }}
            className={`rounded-lg border border-[#d8d2bf] px-4 py-2 text-sm font-medium transition-colors focus:ring-2 focus:ring-[#4a5f8c] focus:outline-none ${
              !isPrivate
                ? "bg-[#0e2758] text-white"
                : "bg-[#fffef8] text-[#0e2758] hover:bg-[#f5f3ed]"
            }`}
          >
            Public
          </button>
          <button
            onClick={() => {
              setIsPrivate(true);
              setSelectedPolicy("All");
            }}
            className={`rounded-lg border border-[#d8d2bf] px-4 py-2 text-sm font-medium transition-colors focus:ring-2 focus:ring-[#4a5f8c] focus:outline-none ${
              isPrivate
                ? "bg-[#0e2758] text-white"
                : "bg-[#fffef8] text-[#0e2758] hover:bg-[#f5f3ed]"
            }`}
          >
            Private
          </button>
        </div>
      </div>

      {/* Temporarily commented out - Leaderboard content */}
      {false &&
        (isPrivate ? (
          <>
            {/* My Policies Table */}
            <div className="mb-8 rounded-2xl border border-[#d8d2bf] bg-[#fffef8] p-6">
              <h3 className="mb-4 text-lg font-semibold text-[#0e2758]">
                My Policies
              </h3>
              <div className="overflow-x-auto">
                <table
                  className="w-full text-sm text-[#333]"
                  style={{ tableLayout: "fixed" }}
                >
                  <thead>
                    <tr className="text-xs tracking-wide text-[#4a5f8c] uppercase">
                      <th
                        className="pb-2 text-left font-semibold"
                        style={{ width: "25%" }}
                      >
                        Policy Name
                      </th>
                      <th
                        className="pb-2 text-right font-semibold"
                        style={{ width: "25%" }}
                      >
                        Score
                      </th>
                      <th
                        className="pb-2 text-left font-semibold"
                        style={{ width: "25%" }}
                      >
                        Submitted At
                      </th>
                      <th
                        className="pb-2 text-left font-semibold"
                        style={{ width: "25%" }}
                      >
                        Status
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPolicies.map((policy, index) => (
                      <tr
                        key={index}
                        className="border-b border-[#e6dcc2] last:border-b-0"
                      >
                        <td
                          className="px-4 py-2 text-[#0e2758]"
                          style={{ width: "25%" }}
                        >
                          {policy.policyName}
                        </td>
                        <td
                          className="px-4 py-2 text-right text-[#0e2758]"
                          style={{ width: "25%" }}
                        >
                          {policy.score.toLocaleString()}
                        </td>
                        <td
                          className="px-4 py-2 text-[#0e2758]"
                          style={{ width: "25%" }}
                        >
                          {policy.submittedAt}
                        </td>
                        <td
                          className="px-4 py-2 text-[#0e2758]"
                          style={{ width: "25%" }}
                        >
                          {policy.status}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Policy Cards with Missions */}
            <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-3">
              {filteredPolicies.map((policy) => (
                <div
                  key={policy.policyName}
                  className="rounded-2xl border border-[#d8d2bf] bg-[#fffef8] p-6"
                >
                  <h3 className="mb-4 text-lg font-semibold text-[#0e2758]">
                    {policy.policyName}
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm text-[#333]">
                      <thead>
                        <tr className="text-xs tracking-wide text-[#4a5f8c] uppercase">
                          <th className="pb-2 text-left font-semibold">
                            Mission
                          </th>
                          <th className="pr-8 pb-2 text-right font-semibold">
                            Score
                          </th>
                          <th className="pb-2 text-left font-semibold">Date</th>
                        </tr>
                      </thead>
                      <tbody>
                        {policyMissions[policy.policyName]?.map(
                          (mission, index) => (
                            <tr
                              key={index}
                              className="border-b border-[#e6dcc2] last:border-b-0"
                            >
                              <td className="py-2 pr-4 text-[#0e2758]">
                                {mission.mission}
                              </td>
                              <td className="py-2 pr-8 text-right text-[#0e2758]">
                                {mission.score.toLocaleString()}
                              </td>
                              <td className="py-2 text-[#0e2758]">
                                {mission.date}
                              </td>
                            </tr>
                          ),
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </div>

            {/* Policy vs Thinky Games */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {filteredPolicies.map((policy) => (
                <div
                  key={policy.policyName}
                  className="rounded-2xl border border-[#d8d2bf] bg-[#fffef8] p-6"
                >
                  <h3 className="mb-4 text-lg font-semibold text-[#0e2758]">
                    {policy.policyName} vs Thinky
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm text-[#333]">
                      <thead>
                        <tr className="text-xs tracking-wide text-[#4a5f8c] uppercase">
                          <th className="pb-2 text-left font-semibold">Game</th>
                          <th className="pb-2 text-right font-semibold">
                            Score
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {policyGames[policy.policyName]?.map((game, index) => (
                          <tr
                            key={index}
                            className="border-b border-[#e6dcc2] last:border-b-0"
                          >
                            <td className="py-2 pr-4 text-[#0e2758]">
                              {game.game}
                            </td>
                            <td className="py-2 text-right text-[#0e2758]">
                              {game.score.toLocaleString()}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </div>
          </>
        ) : (
          <>
            {/* Practice Missions: Top Players - First */}
            <div className="mb-8 rounded-2xl border border-[#d8d2bf] bg-[#fffef8] p-6">
              <h3 className="mb-4 text-lg font-semibold text-[#0e2758]">
                Practice Missions: Top Players
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-[#333]">
                  <thead>
                    <tr className="text-xs tracking-wide text-[#4a5f8c] uppercase">
                      <th className="pb-2 text-left font-semibold">Mission</th>
                      <th className="pb-2 text-left font-semibold">
                        Policy Name
                      </th>
                      <th className="pb-2 text-right font-semibold">Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {practiceMissions.map((player, index) => (
                      <tr
                        key={index}
                        className="border-b border-[#e6dcc2] last:border-b-0"
                      >
                        <td className="py-2 pr-4 text-[#0e2758]">
                          Integrative Mission #{player.missionNumber}
                        </td>
                        <td className="py-2 pr-4 text-[#0e2758]">
                          {player.policyName}
                        </td>
                        <td className="py-2 text-right text-[#0e2758]">
                          {player.highScore.toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Recent Pools - Grid Layout */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {visiblePools.map((pool) => {
                const hasAnyDelta = pool.results.some(
                  (r) => r.scoreDelta !== undefined,
                );
                const maxVisible = 10;
                const hasMore = pool.results.length > maxVisible;

                return (
                  <div
                    key={pool.poolId}
                    className="rounded-2xl border border-[#d8d2bf] bg-[#fffef8] p-6"
                  >
                    <h3 className="mb-4 text-lg font-semibold text-[#0e2758]">
                      {pool.date.split(".").slice(0, 2).join(".")}.
                      <span className="text-[#8a9bb8]">
                        {pool.date.split(".").slice(2).join(".")}
                      </span>
                    </h3>
                    <div className="relative">
                      {/* Scrollable container with blur effect */}
                      <div
                        className={`overflow-y-auto ${hasMore ? "max-h-[400px]" : ""}`}
                        style={{
                          scrollbarWidth: "thin",
                          scrollbarColor: "#d8d2bf transparent",
                        }}
                      >
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm text-[#333]">
                            <thead className="sticky top-0 z-10 bg-[#fffef8]">
                              <tr className="text-xs tracking-wide text-[#4a5f8c] uppercase">
                                <th className="pb-2 text-left font-semibold">
                                  Policy Name
                                </th>
                                <th className="pb-2 text-right font-semibold">
                                  New Score
                                </th>
                                {hasAnyDelta && (
                                  <th className="pb-2 text-right font-semibold">
                                    Change
                                  </th>
                                )}
                              </tr>
                            </thead>
                            <tbody>
                              {pool.results.map((result, index) => (
                                <tr
                                  key={index}
                                  className="border-b border-[#e6dcc2] last:border-b-0"
                                >
                                  <td className="py-2 pr-4 text-[#0e2758]">
                                    {result.policyName}
                                  </td>
                                  <td className="py-2 pr-4 text-right text-[#0e2758]">
                                    {result.newScore.toLocaleString()}
                                  </td>
                                  {hasAnyDelta && (
                                    <td className="py-2 text-right text-[#0e2758]">
                                      {result.scoreDelta !== undefined && (
                                        <span
                                          className={`font-medium ${
                                            result.scoreDelta >= 0
                                              ? "text-[#2e7d32]"
                                              : "text-[#c62828]"
                                          }`}
                                        >
                                          {formatScoreDelta(result.scoreDelta)}
                                        </span>
                                      )}
                                    </td>
                                  )}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                      {/* Gradient fade mask at bottom when there are more than 10 policies */}
                      {hasMore && (
                        <div className="pointer-events-none absolute right-0 bottom-0 left-0 h-12 bg-gradient-to-t from-[#fffef8] via-[#fffef8]/70 to-transparent" />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {hasMorePools && (
              <div className="mt-6 flex justify-center">
                <button
                  onClick={() => setIsExpanded(!isExpanded)}
                  className="rounded-lg border border-[#d8d2bf] bg-[#fffef8] px-6 py-2 text-sm font-medium text-[#0e2758] transition-colors hover:bg-[#f5f3ed] focus:ring-2 focus:ring-[#4a5f8c] focus:outline-none"
                >
                  {isExpanded ? "Collapse" : "Expand to see all"}
                </button>
              </div>
            )}
          </>
        ))}
    </section>
  );
}
