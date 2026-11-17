export interface PowSolution {
  salt: string;
  nonce: number;
}

// Server contract (tokens.py verify_and_consume_pow): sha256(utf8(salt + str(nonce))) as lowercase hex must start
// with `difficulty` zero characters, where `salt` is the signed `pow_salt` from the HTTP 429 `challenge_required`
// body. Checking nibbles on the raw digest is equivalent to the hex-prefix test.
function hasLeadingZeroNibbles(hash: Uint8Array, difficulty: number): boolean {
  const fullBytes = Math.floor(difficulty / 2);
  for (let i = 0; i < fullBytes; i++) {
    if (hash[i] !== 0) return false;
  }
  if (difficulty % 2 !== 0 && (hash[fullBytes] >> 4) !== 0) return false;
  return true;
}

/**
 * Solves the server's proof-of-work. Hashes run through Web Crypto in batches and the event loop is yielded
 * between batches, so the main thread is never blocked for long. Returns null when Web Crypto is unavailable
 * (e.g. an insecure context) or no solution is found within `maxAttempts` (difficulty 5 needs ~1M hashes on average).
 */
export async function solvePow(
  powSalt: string,
  difficulty: number = 4,
  maxAttempts: number = 20000000,
): Promise<PowSolution | null> {
  if (typeof crypto === "undefined" || !crypto.subtle || typeof TextEncoder === "undefined") return null;
  if (!powSalt) return null;
  const diff = Math.max(1, Math.floor(Number(difficulty) || 4));
  const encoder = new TextEncoder();
  const batchSize = 1000;

  for (let start = 0; start < maxAttempts; start += batchSize) {
    const digests: Array<Promise<ArrayBuffer>> = [];
    for (let i = 0; i < batchSize; i++) {
      digests.push(crypto.subtle.digest("SHA-256", encoder.encode(powSalt + (start + i))));
    }
    const results = await Promise.all(digests);
    for (let i = 0; i < results.length; i++) {
      if (hasLeadingZeroNibbles(new Uint8Array(results[i]), diff)) {
        return { salt: powSalt, nonce: start + i };
      }
    }
    // Yield to the browser so rendering and input stay responsive.
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
  }
  return null;
}
