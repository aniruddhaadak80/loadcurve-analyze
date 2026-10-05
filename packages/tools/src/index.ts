/**
 * `@loadcurveanalyze/tools` — the product's capabilities, declared once.
 *
 * `buildProductRegistry` is the function every surface calls to get the one registry the
 * narrow waist requires. There is no second way to reach a capability: the CLI, the MCP
 * server and the web API all call this, so a tool added here is available everywhere and a
 * tool missing here is available nowhere.
 */
export { EngineClient, parseStudyRequest, type EngineClientOptions, type CallOptions } from './client.js'
export { EXAMPLE_MODEL, EXAMPLE_PREMISE, EXAMPLE_REQUEST } from './example.js'
export { productTools, buildProductRegistry, type BuildToolsOptions } from './registry.js'
export { discoveryTools, type DiscoveryOptions } from './discovery.js'
