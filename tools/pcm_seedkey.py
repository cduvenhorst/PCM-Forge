#!/usr/bin/env python3
"""PCM 3.x KWP2000 SecurityAccess key generator.

Given the seed the PCM returns to `27 01`, computes the key to send with
`27 02` and unlock the unit. No PIWIS, no ride-along.

## Provenance

Recovered from the PIWIS tester's own code: `ASAM_seedkey_PCM30.jar`
(`common/java/ASAM_seedkey_PCM30.class`), the class PIWIS calls to unlock a
PCM 3.x head unit. The 14-byte configuration array `__PCM3` was read out of a
live instance by reflection; the algorithm below is a faithful port of that
class's `SecM_ComputeKey`, verified byte-exact against the real Java across all
65536 possible seeds (0 mismatches), and against a seed/key pair captured from
our own PCM 3.1 A3.2 on the bench: seed 0x9263 -> key 0x017F.

## The algorithm

16-bit seed, 16-bit key. What makes it awkward to guess -- and what defeated a
naive rotate-then-combine fit -- is that every parameter is **data-dependent**,
selected by specific bits of the seed via the config array:

  * rotate count  (0..15) : four seed bits, weights 8/4/2/1
  * rotate direction      : one seed bit (right if clear, left if set)
  * final operation       : two seed bits -> add / xor / not / none

so the transform the unit applies changes from one seed to the next.
"""

#: The __PCM3 config, read by reflection from a live ASAM_seedkey_PCM30 instance.
#: Indices: [0]=dir-bit selector, [1]=dir compare, [2..5]=rotate-count bit
#: selectors, [6..7]=op bit selectors, [8..13]=op dispatch values.
_CFG = [8, 0, 3, 0, 12, 15, 5, 10, 8, 8, 1, 3, 2, 0]


def _bit(b):
    """The mask table PIWIS uses: bit index -> mask, MSB first."""
    return 0x8000 >> b


def compute_key(seed):
    """Seed (int 0..0xFFFF) -> key (int 0..0xFFFF)."""
    ns = seed & 0xFFFF
    nr = ns

    # rotate count: four seed bits, weighted
    rot = 0
    if ns & _bit(_CFG[2]):
        rot += 8
    if ns & _bit(_CFG[3]):
        rot += 4
    if ns & _bit(_CFG[4]):
        rot += 2
    if ns & _bit(_CFG[5]):
        rot += 1

    # direction: one seed bit
    direction = 1 if (ns & _bit(_CFG[0])) else 0
    if direction == _CFG[1]:                       # rotate right
        for _ in range(rot):
            carry = nr & 1
            nr = (nr >> 1) & 0x7FFF
            if carry:
                nr |= 0x8000
    else:                                          # rotate left
        for _ in range(rot):
            carry = nr & 0x8000
            nr = (nr << 1) & 0xFFFE
            if carry:
                nr |= 1

    # final operation: two seed bits. _CFG[8]/[9] compare against 8, which the
    # 2-bit op index can never equal, so OR/AND are dead -- exactly as shipped.
    op = 0
    if ns & _bit(_CFG[6]):
        op += 2
    if ns & _bit(_CFG[7]):
        op += 1
    if op == _CFG[8]:
        nr = (nr | ns) & 0xFFFF
    elif op == _CFG[9]:
        nr = (nr & ns) & 0xFFFF
    elif op == _CFG[10]:
        nr = (nr ^ ns) & 0xFFFF
    elif op == _CFG[11]:
        pass
    elif op == _CFG[12]:
        nr = (~ns) & 0xFFFF
    elif op == _CFG[13]:
        nr = (nr + ns) & 0xFFFF
    return nr & 0xFFFF


def key_bytes(seed_bytes):
    """Two seed bytes (big-endian, as the unit sends them) -> two key bytes."""
    seed = (seed_bytes[0] << 8) | seed_bytes[1]
    k = compute_key(seed)
    return bytes(((k >> 8) & 0xFF, k & 0xFF))


#: Verified test vector -- captured from our PCM 3.1 A3.2 on the bench.
_KNOWN = {0x9263: 0x017F}


def _selftest():
    for s, k in _KNOWN.items():
        assert compute_key(s) == k, "%04X -> %04X != %04X" % (s, compute_key(s), k)
    return True


if __name__ == "__main__":
    import sys
    _selftest()
    if len(sys.argv) != 2:
        print("usage: pcm_seedkey.py <seed hex, e.g. 9263>")
        print("       (self-test on the captured 9263->017F pair passed)")
        sys.exit(0)
    seed = int(sys.argv[1], 16)
    print("seed %04X -> key %04X" % (seed, compute_key(seed)))
