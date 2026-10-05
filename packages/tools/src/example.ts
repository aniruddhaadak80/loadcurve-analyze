import type { NetworkModel, StudyRequest } from '@loadcurveanalyze/engine-model'

/**
 * A small radial 11 kV feeder behind a 40 MVA transformer, with a DER site and a battery at
 * the end of a lateral.
 *
 * This is the worked example the README, the CLI's `--example` flag and the web demo all
 * use. It is deliberately small enough to read in full and deliberately *infeasible* under the
 * supplied plan, because a feasible example demonstrates nothing: the product's value is in the
 * two-limit conflict, which only shows up when the plan cannot be dispatched.
 *
 * The conflict is real, not staged. BESS1 starts at 50% SOC with 8 MWh of energy, so a 70%
 * floor by hour 2 needs at least `(0.70 - 0.50) * 8 / 0.95 = 1.684 MW` of charging at B5.
 * L45 is the only path to B5 and carries a 1 MW lateral. Neither limit is violated alone —
 * the floor is satisfiable if the lateral is upgraded, the lateral is satisfiable if the floor
 * is dropped — and the pair is impossible. That is the smallest unsatisfiable core this tool
 * exists to find.
 */
export const EXAMPLE_MODEL: NetworkModel = {
  name: 'radial-11kv-feeder',
  baseMva: 40,
  slackBus: 'SLACK',
  buses: [
    { id: 'SLACK', baseKv: 69 },
    { id: 'B1', baseKv: 11 },
    { id: 'B2', baseKv: 11 },
    { id: 'B3', baseKv: 11 },
    { id: 'B4', baseKv: 11 },
    { id: 'B5', baseKv: 11 },
  ],
  branches: [
    { id: 'TX1', fromBus: 'SLACK', toBus: 'B1', reactancePu: 0.04, ratingMw: 25 },
    { id: 'L12', fromBus: 'B1', toBus: 'B2', reactancePu: 0.05, ratingMw: 12 },
    { id: 'L23', fromBus: 'B2', toBus: 'B3', reactancePu: 0.06, ratingMw: 10 },
    { id: 'L14', fromBus: 'B1', toBus: 'B4', reactancePu: 0.07, ratingMw: 9 },
    { id: 'L45', fromBus: 'B4', toBus: 'B5', reactancePu: 0.08, ratingMw: 6 },
  ],
  storage: [
    {
      id: 'BESS1',
      bus: 'B5',
      chargeMwMax: 4,
      dischargeMwMax: 4,
      energyMwh: 8,
      socFracMin: 0.15,
      socFracMax: 0.95,
      socFracInitial: 0.5,
      efficiency: 0.95,
    },
  ],
}

export const EXAMPLE_REQUEST: StudyRequest = {
  model: EXAMPLE_MODEL,
  plan: {
    intervals: [
      { hours: 1, buses: { B3: { lowerMw: 4, upperMw: 4 }, B5: { lowerMw: -2, upperMw: 6 } } },
      { hours: 1, buses: { B3: { lowerMw: 2, upperMw: 2 }, B5: { lowerMw: -2, upperMw: 6 } } },
    ],
    partial: false,
  },
  constraints: [
    {
      id: 'l23-rating',
      kind: 'line_thermal',
      target: 'L23',
      label: 'L23 conductor rating',
      members: [],
      lower: -10,
      upper: 10,
      enabled: true,
      fromInterval: 0,
      toInterval: null,
    },
    {
      id: 'soc-floor',
      kind: 'storage_soc',
      target: 'BESS1',
      label: 'BESS1 must be 70% charged by hour 2',
      members: [],
      lower: 0.7,
      upper: null,
      enabled: true,
      fromInterval: 1,
      toInterval: null,
    },
    {
      id: 'l45-lateral',
      kind: 'line_thermal',
      target: 'L45',
      label: 'L45 lateral rating (1 MW firm upgrade limit)',
      members: [],
      lower: -1,
      upper: 1,
      enabled: true,
      fromInterval: 0,
      toInterval: null,
    },
    {
      id: 'poi-export',
      kind: 'poi_export',
      target: 'poi',
      label: 'Point-of-interconnection export cap',
      members: ['B3', 'B5'],
      lower: null,
      upper: 8,
      enabled: true,
      fromInterval: 0,
      toInterval: null,
    },
  ],
  outages: [
    { id: 'lose-l12', branchId: 'L12', label: 'Loss of L12' },
    { id: 'lose-l14', branchId: 'L14', label: 'Loss of L14' },
  ],
  budget: 64,
  explain: true,
}

/** The one-line summary of what the example demonstrates. Shown in the README and the web demo. */
export const EXAMPLE_PREMISE =
  'BESS1 must reach 70% charge by hour 2, which needs 1.684 MW through a lateral rated 1 MW.'
