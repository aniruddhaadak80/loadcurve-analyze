/**
 * Canonical JSON — the form a content address is computed over.
 *
 * Split out from the store because it is the one piece of this package that the engine also
 * implements (in `digest.py`) and the piece whose agreement is load-bearing. If the two
 * canonicalisers diverge, a re-run of an unchanged study is stored as a new study, and the
 * reproducibility the whole design rests on quietly stops working.
 *
 * The rules, and why each exists:
 *
 * - **Sorted keys.** Two serialisers emitting the same object in different key order must
 *   produce the same address.
 * - **Fixed decimal places.** `0.1 + 0.2 !== 0.3` in IEEE-754, and the same computation can
 *   arrive at a differently-rounded double on another machine. Six places on MW quantities is
 *   far below any engineering tolerance, so it cannot merge two genuinely different studies.
 * - **Negative zero normalised.** `-0` and `0` are equal as numbers but not identical as
 *   strings; without this they would hash differently.
 * - **Non-finite rejected.** `NaN` and `Infinity` have no JSON representation, so accepting
 *   them would make the address depend on the serialiser's fallback.
 */
export function canonicalize(value: unknown): unknown {
  if (typeof value === 'boolean' || value === null) return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      throw new TypeError(`cannot content-address a non-finite number: ${String(value)}`)
    }
    const rounded = Number(value.toFixed(6))
    return rounded === 0 ? 0 : rounded
  }
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(canonicalize)
  if (typeof value === 'object') {
    const source = value as Record<string, unknown>
    return Object.fromEntries(
      Object.keys(source)
        .sort()
        .map((key) => [key, canonicalize(source[key])]),
    )
  }
  throw new TypeError(`cannot content-address a ${typeof value}`)
}

/** The canonical serialisation, as a string. */
export function canonicalJson(value: unknown): string {
  // `JSON.stringify` emits `3` for 3.0, Python's `json.dumps` emits `3.0`. For a SHA-256 over
  // the bytes, that is the whole difference — so integral floats are rendered with an explicit
  // `.0`, matching the engine. Without this the two implementations disagree on every model
  // that contains a whole number of MW, which is most of them.
  return stringifyPythonCompatible(canonicalize(value))
}

/**
 * JSON serialisation that matches Python's `json.dumps` byte for byte.
 *
 * The only divergence that matters for a content address is integral floats: Python's repr
 * keeps the decimal point (`3.0`) and JavaScript's does not (`3`). Strings and non-integral
 * numbers agree between the two, and non-ASCII is passed through unescaped on both sides
 * because Python's default `ensure_ascii` is disabled in the engine.
 */
function stringifyPythonCompatible(value: unknown): string {
  if (value === null) return 'null'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return Number.isInteger(value) ? `${value}.0` : String(value)
  if (typeof value === 'string') return JSON.stringify(value)
  if (Array.isArray(value)) {
    return `[${value.map(stringifyPythonCompatible).join(',')}]`
  }
  if (typeof value === 'object') {
    const source = value as Record<string, unknown>
    const entries = Object.keys(source)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stringifyPythonCompatible(source[key])}`)
    return `{${entries.join(',')}}`
  }
  throw new TypeError(`cannot serialise a ${typeof value}`)
}

/**
 * SHA-256 of the canonical form, as `sha256:<hex>`.
 *
 * Async because SHA-256 is only reachable synchronously through Node's `node:crypto`, and this
 * package is also imported by the web app — a Node built-in in the browser bundle would be
 * worse than one `await`. Web Crypto exists in both runtimes.
 */
export async function contentDigest(value: unknown): Promise<string> {
  const subtle = globalThis.crypto?.subtle
  if (subtle === undefined) {
    throw new TypeError('no Web Crypto implementation available')
  }
  const hash = await subtle.digest('SHA-256', new TextEncoder().encode(canonicalJson(value)))
  const hex = Array.from(new Uint8Array(hash))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
  return `sha256:${hex}`
}
