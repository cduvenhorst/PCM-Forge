#!/usr/bin/env python3
"""
PCM-Forge: Porsche PCM 3.1 Activation Code Generator
https://github.com/dspl1236/PCM-Forge

Generates activation codes for ALL 27 features of the Porsche PCM 3.1.

Usage:
  python generate_codes.py <VIN>                     # list all codes (911 default)
  python generate_codes.py <VIN> <USB_PATH>          # build an activation USB stick
  python generate_codes.py <VIN> --model <key>       # pick model variant
  python generate_codes.py <VIN> <USB_PATH> --model <key>
  python generate_codes.py <VIN> <USB_PATH> --add TEL,KOMP     # add features
  python generate_codes.py <VIN> <USB_PATH> --remove KOMP      # remove features
  python generate_codes.py --diag <USB_PATH>         # diagnostic stick (no VIN needed)
  python generate_codes.py --show <PATH>             # decode an existing PagSWAct.002
  python generate_codes.py <USB_PATH> --from-backup  # rebuild from the car's backup
  python generate_codes.py <VIN> <USB_PATH> --from-backup --add TEL
  python generate_codes.py <VIN> --show <PATH>       # ...and check it belongs to that VIN
  python generate_codes.py --list-models             # show available models
  python generate_codes.py --list-features           # show feature names
  python generate_codes.py <VIN> --subid NavDBEurope=0x0001   # pick a variant

Most features have a single SubID, but a few carry variants: the nav databases
take a map index (0x00ff = all, or a specific index), and TVINF, SSS and
OnlineServices differ per vehicle. --subid NAME=HEX selects one; it is
repeatable. The built-in defaults are the values the factory used most often
in research/firmware/PagSWAct.csv, so overriding is the exception.

After a diagnostic run the stick holds the car's own PagSWAct_backup_<stamp>.002.
--from-backup turns that into a ready activation stick in one step: it seeds
PagSWAct.002 from the backup, applies any --add/--remove, and switches run.sh
back to activation mode. Without --add/--remove it simply restores what the car
had. Adding features needs the VIN, and it must be the one the backup was signed
for -- codes from two cars in one file would be rejected by the PCM.

The USB stick carries copie_scr.sh (an XOR-encoded bootstrap, as
proc_scriptlauncher expects), run.sh, PagSWAct.002 and the splash assets.
--no-xor writes the bootstrap as plaintext; it is for testing only, since the
PCM's launcher XOR-decodes the file and a plaintext script decodes to garbage.

Model keys (for correct FeatureLevel / boot logo):
  cayenne-958      Cayenne 958 base                        (SubID 0x0039)
  cayenne-958s     Cayenne 958 S                           (SubID 0x003a)
  cayenne-958t     Cayenne 958 Turbo                       (SubID 0x003b)
  cayenne-958ts    Cayenne 958 Turbo S                     (SubID 0x003c)
  cayenne-958gts   Cayenne 958 GTS                         (SubID 0x003d)
  cayenne-958sh    Cayenne 958 S Hybrid                    (SubID 0x003e)
  cayenne-958-v6   Cayenne 958 V6                          (SubID 0x003f)
  cayenne-958se    Cayenne 958 S E-Hybrid                  (SubID 0x0043)  [Andrew's car!]
  991              911 (991) Carrera                        (SubID 0x0003)  [default]
  991-base         911 (991) base variant                 (SubID 0x0000)
  991t             911 (991) Turbo                        (SubID 0x0005)
  boxster-cayman   Boxster / Cayman (981)                 (SubID 0x0007)
  997              911 (997) Carrera                      (SubID 0x002a)
  panamera         Panamera (970) V8                      (SubID 0x002d)
  997t             911 (997) Turbo                        (SubID 0x002e)
  997-alt          911 (997) alternate coding             (SubID 0x0031)

For unknown models (Macan 95B, GT3/GT2):
  Pass --featlevel-subid 0xNNNN with the known SubID for that vehicle.
"""
import struct, sys, os, argparse

# RSA parameters recovered from CPPorscheEncrypter::verify in the PCM3Root
# firmware (research/ALGORITHM_CRACKED.md). N and E sit in the binary as hex
# strings at 0x082270b4 and 0x082270b8; D is not in the firmware -- at 63 bits
# the modulus factors in seconds (1831263461 x 4169044001), which is what makes
# generating codes possible at all. The unit only ever verifies, using E.
N = 0x69f39c927ef94985
E = 0x4c1c5eeaf397c0b3
D = 0x5483975015d0287b

# Complete Model → FeatureLevel SubID mapping
# All 78 models visually confirmed from PCM 3.1 bootscreen images
# SubID = FeatureLevel value = boot logo selector (they're the same!)
MODELS = {
    # ── 911 (997) Coupe ──
    '911':                   (0x0001, '911 (997) base'),
    '911-carrera':           (0x0002, '911 (997) Carrera'),
    '911-carrera-s':         (0x0003, '911 (997) Carrera S'),
    '911-carrera-4':         (0x0004, '911 (997) Carrera 4'),
    '911-carrera-4s':        (0x0005, '911 (997) Carrera 4S'),
    # ── 911 (997) Cabriolet ──
    '911-cab':               (0x0006, '911 (997) Carrera Cabriolet'),
    '911-cab-s':             (0x0007, '911 (997) Carrera S Cabriolet'),
    '911-cab-4':             (0x0008, '911 (997) Carrera 4 Cabriolet'),
    '911-cab-4s':            (0x0009, '911 (997) Carrera 4S Cabriolet'),
    # ── 911 (997) Targa ──
    '911-targa-4':           (0x000a, '911 (997) targa 4'),
    '911-targa-4s':          (0x000b, '911 (997) targa 4S'),
    # ── 911 (997) Turbo / GT ──
    '911-turbo':             (0x000c, '911 (997) Turbo'),
    '911-turbo-cab':         (0x000d, '911 (997) Turbo Cabriolet'),
    '911-turbo-s':           (0x000e, '911 (997) Turbo S'),
    '911-turbo-s-cab':       (0x000f, '911 (997) Turbo S Cabriolet'),
    '911-gt3':               (0x0010, '911 (997) GT3'),
    '911-gt3rs':             (0x0012, '911 (997) GT3 RS'),
    # ── 911 (991) ──
    '911-991':               (0x0014, '911 (991)'),
    '911-991-alt':           (0x0015, '911 (991) alt'),
    '911-991-gts':           (0x0016, '911 (991) Carrera GTS'),
    '911-991-4gts':          (0x0017, '911 (991) Carrera 4 GTS'),
    '911-991-gts-cab':       (0x0018, '911 (991) Carrera GTS Cabriolet'),
    '911-991-4gts-cab':      (0x0019, '911 (991) Carrera 4 GTS Cabriolet'),
    # ── Boxster (987 / 981) ──
    'boxster':               (0x001a, 'Boxster'),
    'boxster-alt':           (0x001b, 'Boxster (alt)'),
    'boxster-s':             (0x001c, 'Boxster S'),
    'boxster-rs':            (0x001d, 'Boxster RS'),
    'boxster-gts':           (0x001e, 'Boxster GTS'),
    'boxster-spyder':        (0x001f, 'Boxster Spyder'),
    # ── Cayman (987 / 981) ──
    'cayman':                (0x0022, 'Cayman'),
    'cayman-alt':            (0x0023, 'Cayman (alt)'),
    'cayman-s':              (0x0024, 'Cayman S'),
    'cayman-r':              (0x0025, 'Cayman R'),
    'cayman-gts':            (0x0026, 'Cayman GTS'),
    'cayman-gt4':            (0x0027, 'Cayman GT4'),
    # ── Panamera (970) ──
    'panamera':              (0x0029, 'Panamera'),
    'panamera-alt':          (0x002a, 'Panamera (alt)'),
    'panamera-4':            (0x002b, 'Panamera 4'),
    'panamera-s':            (0x002c, 'Panamera S'),
    'panamera-4s':           (0x002d, 'Panamera 4S'),
    'panamera-turbo':        (0x002e, 'Panamera Turbo'),
    'panamera-turbo-s':      (0x002f, 'Panamera Turbo S'),
    'panamera-gts':          (0x0030, 'Panamera GTS'),
    'panamera-sh':           (0x0031, 'Panamera S Hybrid'),
    'panamera-2':            (0x0032, 'Panamera (gen2)'),
    'panamera-s2':           (0x0033, 'Panamera S (gen2)'),
    'panamera-4sd':          (0x0034, 'Panamera 4S Diesel'),
    'panamera-sh2':          (0x0035, 'Panamera S Hybrid (gen2)'),
    'panamera-se':           (0x0036, 'Panamera S E-Hybrid'),
    # ── Cayenne (958) ──
    'cayenne':               (0x0038, 'Cayenne'),
    'cayenne-alt':           (0x0039, 'Cayenne (alt)'),
    'cayenne-s':             (0x003a, 'Cayenne S'),
    'cayenne-turbo':         (0x003b, 'Cayenne Turbo'),
    'cayenne-turbo-s':       (0x003c, 'Cayenne Turbo S'),
    'cayenne-gts':           (0x003d, 'Cayenne GTS'),
    'cayenne-sh':            (0x003e, 'Cayenne S Hybrid'),
    'cayenne-v6':            (0x003f, 'Cayenne V6'),
    'cayenne-s-alt':         (0x0040, 'Cayenne S (alt)'),
    'cayenne-ds':            (0x0041, 'Cayenne Diesel S'),
    'cayenne-sh2':           (0x0042, 'Cayenne S Hybrid (alt)'),
    'cayenne-se':            (0x0043, 'Cayenne S E-Hybrid'),
    # ── Macan (95B) ──
    'macan':                 (0x0047, 'Macan'),
    'macan-s':               (0x0048, 'Macan S'),
    'macan-hybrid':          (0x0049, 'Macan Hybrid'),
    'macan-se':              (0x004a, 'Macan S E-Hybrid'),
    'macan-turbo':           (0x004b, 'Macan Turbo'),
    'macan-turbo-s':         (0x004c, 'Macan Turbo S'),
    'macan-gts':             (0x004d, 'Macan GTS'),
    'macan-diesel':          (0x004e, 'Macan Diesel'),
    'macan-sd':              (0x004f, 'Macan S Diesel'),
    # ── 911 Special Editions ──
    '911-50th':              (0x0056, '911 50th Anniversary'),
    '911-clubsport':         (0x0057, '911 Club Sport'),
    '911-r':                 (0x0058, '911 R'),
    # ── 911 (991.2) / Targa ──
    '911-targa-4gts':        (0x005e, '911 targa 4 GTS'),
    '911-targa':             (0x005f, '911 targa'),
    '911-targa-s':           (0x0060, '911 targa S'),
    '911-991-2':             (0x0061, '911 (991.2)'),
    '911-991-2-cab':         (0x0062, '911 (991.2) Cabriolet'),
}

def features_for(featlvl_subid, subid_overrides=None):
    """Build the feature list using a specific FeatureLevel SubID.

    subid_overrides maps a feature name to a SubID, selecting a non-default
    variant (e.g. a nav database at map index 1 instead of 0xff). The defaults
    below are the values the factory used most often in
    research/firmware/PagSWAct.csv.
    """
    featlvl_hex = f"010e{featlvl_subid:04x}"
    # (name, feature hex, SWID, SubID, description). The feature hex is just
    # SWID and SubID written out, and it is what gets signed.
    #
    # Every SWID here is distinct, which is why --add/--remove can identify a
    # record by SWID alone; tests/test_generate_codes.py guards that.
    #
    # The SubIDs are the variant the factory used most often in
    # research/firmware/PagSWAct.csv -- SSS, TVINF, OnlineServices and the nav
    # databases are known to carry others on some cars. --subid picks those.
    feats = [
        ("ENGINEERING",      "010b0000", 0x010b, 0x0000, "Engineering & diagnostic menu"),
        ("BTH",              "010a0000", 0x010a, 0x0000, "Bluetooth telephony"),
        ("KOMP",             "01060000", 0x0106, 0x0000, "Kompass (compass display)"),
        ("Navigation",       "01010000", 0x0101, 0x0000, "Navigation system"),
        ("TEL",              "01020000", 0x0102, 0x0000, "Telephone module"),
        ("UMS",              "01090000", 0x0109, 0x0000, "USB media support"),
        ("FB",               "01030000", 0x0103, 0x0000, "Fahrtenbuch (electronic logbook)"),
        ("SSS",              "01040000", 0x0104, 0x0000, "Voice control"),
        ("SC",               "01050000", 0x0105, 0x0000, "Sport Chrono"),
        ("TVINF",            "01070166", 0x0107, 0x0166, "Video in Motion"),
        ("SDARS",            "01080000", 0x0108, 0x0000, "Satellite radio"),
        ("INDMEM",           "010d0000", 0x010d, 0x0000, "Individual memory"),
        ("FeatureLevel",     featlvl_hex, 0x010e, featlvl_subid, "Feature level / boot logo"),
        ("HDTuner",          "010f0000", 0x010f, 0x0000, "HD Radio tuner"),
        ("DABTuner",         "01100000", 0x0110, 0x0000, "DAB digital radio"),
        ("OnlineServices",   "01110001", 0x0111, 0x0001, "Online services"),
        ("NavDBEurope",      "200100ff", 0x2001, 0x00ff, "Europe"),
        ("NavDBNorthAmerica","200200ff", 0x2002, 0x00ff, "North America"),
        ("NavDBSouthAfrica", "200300ff", 0x2003, 0x00ff, "South Africa"),
        ("NavDBMiddleEast",  "200400ff", 0x2004, 0x00ff, "Middle East"),
        ("NavDBAustralia",   "200500ff", 0x2005, 0x00ff, "Australia"),
        ("NavDBAsiaPacific", "200600ff", 0x2006, 0x00ff, "Asia Pacific"),
        ("NavDBRussia",      "200700ff", 0x2007, 0x00ff, "Russia"),
        ("NavDBSouthAmerica","200800ff", 0x2008, 0x00ff, "South America"),
        ("NavDBChina",       "200900ff", 0x2009, 0x00ff, "China"),
        ("NavDBChile",       "200a00ff", 0x200a, 0x00ff, "Chile"),
        ("NavDBArgentina",   "200b00ff", 0x200b, 0x00ff, "Argentina"),
    ]
    if not subid_overrides:
        return feats
    wanted = {k.lower(): v for k, v in subid_overrides.items()}
    out = []
    for name, feat_hex, swid, subid, desc in feats:
        if name.lower() in wanted:
            subid = wanted[name.lower()]
            feat_hex = f"{swid:04x}{subid:04x}"
        out.append((name, feat_hex, swid, subid, desc))
    return out


def vin_to_number(vin):
    """Weighted-sum VIN -> integer, matching CPPorscheEncrypter::vinToNumber.

    Only eight of the seventeen characters count. Position 8 (the North
    American check digit) and position 10 (the plant code) are skipped, so
    two cars from different plants can share a hash -- the value identifies a
    car well enough for the unit's purposes, but it is not a VIN in disguise
    and cannot be turned back into one.
    """
    vl = vin.lower()
    positions = [7, 9, 11, 12, 13, 14, 15, 16]
    # Weight starts at 10, not 1: the firmware consumes one round on the
    # string's terminating null before reaching the first digit. It is then
    # truncated to 16 bits every round, so it wraps rather than growing.
    result, weight = 0, 10
    for pos in reversed(positions):
        c = vl[pos]
        # ASCII tests, not str.isdigit()/islower(): those are Unicode-aware and
        # would diverge from the SH4 firmware (and crash on e.g. U+00B2).
        if '0' <= c <= '9':
            b = ord(c) - ord('0')
        elif 'a' <= c <= 'z':
            b = ord(c) % 10
        else:
            b = 0
        result = (result + b * weight) & 0xFFFFFFFF
        weight = (weight * 10) & 0xFFFF
    return result

def interleave(a, b):
    """Weave two 8-character hex strings into one 16-character string.

    a0 b0 a1 b1 ... -- not concatenation. Getting this wrong yields a
    plausible-looking code that the unit rejects, so it is worth stating.
    """
    return ''.join(a[i] + b[i] for i in range(8))

def generate_code(vin, feat_hex):
    """Generate the 16-character activation code for a (VIN, feature) pair.

    The plaintext cannot overflow the 63-bit modulus: its top hex digit is
    feat_hex[0], which is '0' or '2' across every feature, so the value stays
    below 0x3000000000000000 < N. Verified against 487 factory codes.
    """
    vh = f"{vin_to_number(vin):08x}"
    pt = int(interleave(feat_hex, vh), 16)
    return f"{pow(pt, D, N):016x}"

def build_pagswact(vin, features):
    """Pack a whole feature list into PagSWAct.002 form."""
    return b''.join(build_record(vin, f[1], f[2], f[3]) for f in features)

# XOR PRNG cipher -- matches proc_scriptlauncher in the PCM 3.1 / MMI3G firmware.
# The launcher XOR-decodes copie_scr.sh before running it, so a plaintext script
# decodes to garbage and is silently ignored (research/DISCOVERY_NARRATIVE.md).
SUBID_WILDCARD = 0xffff  # record header value meaning "any SubID"

XOR_SEED_INIT = 0x001be3ac

def xor_encode(data):
    """Encode bytes so proc_scriptlauncher's decoder yields the original script."""
    seed = XOR_SEED_INIT

    def rand():
        nonlocal seed
        r0 = seed & 0xFFFFFFFF
        r1 = ((seed >> 1) | (seed << 31)) & 0xFFFFFFFF
        r3 = (((r1 >> 16) & 0xFF) + r1) & 0xFFFFFFFF
        r1 = (((r3 >> 8) & 0xFF) << 16) & 0xFFFFFFFF
        seed = (r3 - r1) & 0xFFFFFFFF
        return r0

    rand()  # first call discarded
    return bytes(b ^ (rand() & 0xFF) for b in data)

# The USB stick carries three files: copie_scr.sh (this bootstrap, XOR-encoded),
# run.sh (plaintext, from payloads/), and PagSWAct.002 (activation records).
# The bootstrap deliberately stays in code: a raw, unencoded copy of it on a
# stick is the documented silent-failure case, so it must not be downloadable
# as a plain file (see CLAUDE.md).
BOOTSTRAP = (
    "#!/bin/ksh\n"
    "export SDPATH=$1\n"
    "mount -u $SDPATH\n"
    "cd $SDPATH\n"
    "exec ksh ./run.sh $SDPATH\n"
)

PAYLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'payloads')

def load_payload(name):
    """Read a ksh payload verbatim.

    newline='' keeps line endings exactly as stored, so a stray CRLF shows up
    here instead of silently reaching the head unit's shell, which rejects it.
    """
    with open(os.path.join(PAYLOAD_DIR, name), encoding='utf-8', newline='') as f:
        return f.read()

RUN_ACTIVATE = load_payload('run_activate.sh')
RUN_DIAG = load_payload('run_diag.sh')

def parse_subid_overrides(values, valid_names):
    """Turn ["NavDBEurope=0x0001", ...] into {name: subid}; raises ValueError."""
    lookup = {n.lower(): n for n in valid_names}
    out = {}
    for item in values or []:
        if '=' not in item:
            raise ValueError(f"--subid needs NAME=VALUE, got '{item}'")
        name, _, raw = item.partition('=')
        key = name.strip().lower()
        if key not in lookup:
            raise ValueError(f"unknown feature '{name.strip()}' in --subid "
                             f"(use --list-features)")
        try:
            sub = int(raw, 16)
        except ValueError:
            raise ValueError(f"--subid value for {name.strip()} must be hex, "
                             f"got '{raw}'")
        if not 0 <= sub <= 0xFFFF:
            raise ValueError(f"--subid value for {name.strip()} out of range: {raw}")
        out[lookup[key]] = sub
    return out


def load_records(path):
    """Read PagSWAct.002 into a list of (swid, record).

    A length that is not a whole number of records means the file is not what
    it claims to be -- refuse it rather than parse a prefix and silently drop
    the tail.
    """
    with open(path, 'rb') as f:
        data = f.read()
    if not data or len(data) % 28:
        raise ValueError(f"{path} is not a valid PagSWAct.002 ({len(data)} bytes)")
    recs = []
    for i in range(0, len(data), 28):
        rec = bytearray(data[i:i + 28])
        recs.append((struct.unpack_from('<H', rec, 18)[0], rec))
    return recs

# One activation record as PCM3Root reads it back out of flash
# (research/DISCOVERY_NARRATIVE.md):
#
#   offset  size  field
#   0x00      16  activation code, ASCII hex
#   0x10       2  padding, zero
#   0x12       2  SWID, uint16 LE      -- which feature
#   0x14       2  SubID, uint16 LE     -- which variant of it
#   0x16       1  active flag, 1 = on
#   0x17       1  padding, zero
#   0x18       4  count, uint32 LE, always 1
#
# SWID and SubID appear twice over: in the clear here, and inside the signed
# code. The unit compares the two, so editing the header alone gets a record
# rejected -- which is what --show checks for.
RECORD_SIZE = 28

def build_record(vin, feat_hex, swid, subid):
    """Pack one feature into its activation record."""
    code = generate_code(vin, feat_hex)
    rec = bytearray(RECORD_SIZE)
    rec[0:16] = code[:16].encode('ascii')
    struct.pack_into('<H', rec, 0x12, swid)
    struct.pack_into('<H', rec, 0x14, subid)
    rec[0x16] = 1
    struct.pack_into('<I', rec, 0x18, 1)
    return rec


CORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'core')
SPLASH_ASSETS = [('bin', 'forge_splash'), ('lib', 'running.bin'), ('lib', 'done.bin')]

def write_usb(out, run_sh, xor=True, pagswact=None):
    """Write the three-file USB payload plus the splash assets to `out`.

    Nothing here deletes: a stick may already hold diagnostic logs, music or
    a previous backup, and all of that stays. Missing splash assets are
    skipped silently -- they only drive the on-screen status, so their
    absence must not stop a stick from being built.
    """
    os.makedirs(out, exist_ok=True)
    boot = BOOTSTRAP.encode('utf-8')
    with open(os.path.join(out, 'copie_scr.sh'), 'wb') as f:
        f.write(xor_encode(boot) if xor else boot)
    with open(os.path.join(out, 'run.sh'), 'wb') as f:
        f.write(run_sh.encode('utf-8'))
    if pagswact is not None:
        with open(os.path.join(out, 'PagSWAct.002'), 'wb') as f:
            f.write(pagswact)
    for subdir, name in SPLASH_ASSETS:
        src_path = os.path.join(CORE_DIR, subdir, name)
        if not os.path.exists(src_path):
            continue
        dst_dir = os.path.join(out, subdir)
        os.makedirs(dst_dir, exist_ok=True)
        with open(src_path, 'rb') as s, open(os.path.join(dst_dir, name), 'wb') as d:
            d.write(s.read())


def validate_vin(raw):
    """Uppercase a VIN, or raise ValueError explaining what is wrong."""
    vin = raw.upper()
    if len(vin) != 17:
        raise ValueError(f"VIN must be 17 characters (got {len(vin)})")
    return vin

def features_from_args(args):
    """The feature table the flags ask for: model plus any --subid overrides."""
    featlvl_subid, model_desc = resolve_model(args)
    overrides = parse_subid_overrides(
        args.subid, [f[0] for f in features_for(featlvl_subid)])
    return features_for(featlvl_subid, overrides), featlvl_subid, model_desc


def resolve_feature_names(names, features):
    """Map user-typed names to feature records, case-insensitively.

    Raises ValueError naming every unknown entry, so one typo does not get
    applied halfway through a file the head unit depends on.
    """
    by_name = {f[0].lower(): f for f in features}
    unknown = [n for n in names if n.lower() not in by_name]
    if unknown:
        raise ValueError(f"unknown feature(s): {', '.join(unknown)}. "
                         f"Use --list-features to see options.")
    return [by_name[n.lower()] for n in names]

def apply_feature_edits(recs, matches, vin, adding):
    """Return `recs` with `matches` added (replacing same-SWID records) or removed."""
    touched = {swid for _n, _h, swid, _s, _d in matches}
    out = [(s, r) for s, r in recs if s not in touched]
    if adding:
        for _name, feat_hex, swid, subid, _desc in matches:
            out.append((swid, build_record(vin, feat_hex, swid, subid)))
    return out


def find_backup(usb_path, explicit=''):
    """Locate the vehicle's own PagSWAct_backup_*.002 on a stick.

    Deliberately ignores a plain PagSWAct.002: that one is a file we wrote,
    while the backup is what the car itself reported. Raises ValueError when
    the choice is not obvious.
    """
    if explicit:
        if not os.path.exists(explicit):
            raise ValueError(f"{explicit} not found")
        return explicit
    if not os.path.isdir(usb_path):
        raise ValueError(f"{usb_path} is not a directory")
    backups = sorted(f for f in os.listdir(usb_path)
                     if f.startswith('PagSWAct_backup') and f.endswith('.002'))
    if len(backups) == 1:
        return os.path.join(usb_path, backups[0])
    if not backups:
        raise ValueError(f"no PagSWAct_backup_*.002 in {usb_path}; "
                         f"run --diag on the car first")
    listing = '\n    '.join(backups)
    raise ValueError(f"several backups in {usb_path}; "
                     f"pass one to --from-backup:\n    {listing}")

def backup_vin_hash(recs):
    """The VIN hash every record was signed for, or None if they disagree.

    None also covers the empty case. Callers treat it as "cannot tell" and
    skip the VIN check rather than assume a match.
    """
    hashes = set()
    for _swid, rec in recs:
        try:
            plain = f"{pow(int(rec[:16].decode('ascii'), 16), E, N):016x}"
        except ValueError:
            continue
        hashes.add(plain[1::2])
    return hashes.pop() if len(hashes) == 1 else None


def split_feature_names(values):
    """["TEL,KOMP", " SC "] -> ["TEL", "KOMP", "SC"], empty segments dropped."""
    names = []
    for value in values:
        for part in value.split(','):
            part = part.strip()
            if part and part not in names:
                names.append(part)
    return names


def resolve_pagswact(path):
    """Accept the file itself, or a directory holding it.

    Used by --show, which should read whatever is on a stick. Contrast
    find_backup, which deliberately looks only for the car's own backup.

    A diagnostic run leaves the unit's own activation file as
    PagSWAct_backup_<stamp>.002, so a stick often has no plain PagSWAct.002.
    Raises ValueError when the choice is not obvious.
    """
    if not os.path.isdir(path):
        return path
    canonical = os.path.join(path, 'PagSWAct.002')
    if os.path.exists(canonical):
        return canonical
    backups = sorted(f for f in os.listdir(path)
                     if f.startswith('PagSWAct_backup') and f.endswith('.002'))
    if len(backups) == 1:
        return os.path.join(path, backups[0])
    if not backups:
        raise ValueError(f"no PagSWAct.002 or PagSWAct_backup_*.002 in {path}")
    listing = '\n    '.join(backups)
    raise ValueError(f"several backups in {path}; name one explicitly:\n    {listing}")

def show_pagswact(path, vin=None):
    """Print what an existing PagSWAct.002 activates, as the PCM reads it."""
    try:
        target = resolve_pagswact(path)
        recs = load_records(target)
    except FileNotFoundError:
        print(f"Error: {target} not found.", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Any FeatureLevel SubID does here: this lookup is by SWID, and only the
    # FeatureLevel entry's SubID depends on the model.
    known = {f[2]: f for f in features_for(0x0003)}
    print(f"\n  {target}")
    print(f"  {len(recs)} feature(s), {len(recs) * 28} bytes\n")
    print(f"  {'Feature':<20s} {'SubID':<8s} {'Code':<18s} Notes")
    print(f"  {'-'*20}  {'-'*6}  {'-'*16}  {'-'*30}")

    vin_hashes = set()
    for swid, rec in recs:
        code = rec[:16].decode('ascii', 'replace')
        subid = struct.unpack_from('<H', rec, 20)[0]
        active = rec[22]
        entry = known.get(swid)
        name = entry[0] if entry else f"Unknown (0x{swid:04x})"

        notes = []
        signed_subid = None
        try:
            plain = f"{pow(int(code, 16), E, N):016x}"
            feat_half, vin_half = plain[0::2], plain[1::2]
            signed_subid = int(feat_half[4:], 16)
            # A header SubID of 0xffff is a wildcard: the factory stores it for
            # features whose code is signed with SubID 0x0000 (seen on a car in
            # Navigation, UMS and BTH records).
            subid_ok = subid == signed_subid or subid == SUBID_WILDCARD
            if int(feat_half[:4], 16) != swid or not subid_ok:
                notes.append('! code does not match its record header')
            else:
                vin_hashes.add(vin_half)
        except ValueError:
            notes.append('! code is not valid hex')
        if subid == SUBID_WILDCARD:
            if signed_subid is not None:
                notes.append(f'wildcard header, signed 0x{signed_subid:04x}')
        elif entry and subid != entry[3]:
            notes.append(f'variant (default 0x{entry[3]:04x})')
        if not active:
            notes.append('inactive')

        print(f"  {name:<20s} 0x{subid:04x}  {code:<18s} {'; '.join(notes)}")

    print()
    if len(vin_hashes) == 1:
        vh = vin_hashes.pop()
        print(f"  Signed for VIN hash: {vh}")
        if vin:
            ours = f"{vin_to_number(vin):08x}"
            verdict = 'MATCH' if ours == vh else 'MISMATCH'
            print(f"  {vin} hashes to {ours} -> {verdict}")
            if verdict == 'MISMATCH':
                print("  These codes belong to a different VIN (donor PCM?).")
    elif len(vin_hashes) > 1:
        print(f"  Warning: records carry {len(vin_hashes)} different VIN hashes: "
              f"{', '.join(sorted(vin_hashes))}")
    print()
    return 0


def resolve_model(args):
    """(FeatureLevel SubID, description) from --model / --featlevel-subid.

    Raises ValueError with a message fit for the user.
    """
    if args.featlevel_subid:
        try:
            return int(args.featlevel_subid, 16), \
                f"custom SubID 0x{int(args.featlevel_subid, 16):04x}"
        except ValueError:
            raise ValueError("--featlevel-subid must be hex (e.g. 0x0039)")
    if args.model:
        if args.model not in MODELS:
            raise ValueError(f"unknown model '{args.model}'. "
                             f"Use --list-models to see options.")
        return MODELS[args.model]
    return 0x0003, '911 (991) Carrera [default — use --model for others]'


def build_from_backup(args):
    """Rebuild a stick as an activation stick, seeded from the car's backup."""
    # The VIN is optional here but the path is not, so a lone positional can
    # only be the path -- shift it over rather than making people pad the slot.
    vin_arg, usb_path = args.vin, args.usb_path
    if usb_path is None and vin_arg is not None:
        vin_arg, usb_path = None, vin_arg
    if not usb_path:
        print("Error: --from-backup needs the USB path.", file=sys.stderr)
        return 1

    try:
        source = find_backup(usb_path, args.from_backup)
        recs = load_records(source)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    names = split_feature_names(args.add or args.remove or [])
    if names:
        if not vin_arg:
            print("Error: --add/--remove with --from-backup need the VIN, "
                  "so the new codes can be signed.", file=sys.stderr)
            return 1
        try:
            vin = validate_vin(vin_arg)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        signed_for = backup_vin_hash(recs)
        ours = f"{vin_to_number(vin):08x}"
        if signed_for and signed_for != ours:
            print(f"Error: {source} is signed for VIN hash {signed_for}, "
                  f"but {vin} hashes to {ours}. Mixing codes from two cars "
                  f"would give a file the PCM rejects.", file=sys.stderr)
            return 1

        try:
            features, _subid, _desc = features_from_args(args)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        try:
            matches = resolve_feature_names(names, features)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        recs = apply_feature_edits(recs, matches, vin, adding=bool(args.add))

    target = os.path.join(usb_path, 'PagSWAct.002')
    replacing = os.path.exists(target)
    if replacing and not args.quiet:
        print(f"\n  Note: overwriting the existing {target}")

    write_usb(usb_path, RUN_ACTIVATE, xor=not args.no_xor,
              pagswact=b''.join(bytes(r) for _s, r in recs))
    if not args.quiet:
        print(f"\n  Activation stick built from {os.path.basename(source)}")
        print(f"  {len(recs)} feature(s) -> {target}")
        print("  The backup and any diagnostic logs were left untouched.\n")
    return 0


def list_models():
    """Print the model keys accepted by --model."""
    print("\n  Available model keys for --model:\n")
    print(f"  {'Key':<18s} {'SubID':<8s} {'Description'}")
    print(f"  {'-'*18}  {'-'*6}  {'-'*40}")
    for key, (sub, desc) in MODELS.items():
        print(f"  {key:<18s} 0x{sub:04x}  {desc}")
    print("\n  For unknown variants, use: --featlevel-subid 0xNNNN\n")

def list_features():
    """Print the feature names accepted by --add/--remove/--subid."""
    print("\n  Feature names for --add / --remove:\n")
    print(f"  {'Name':<20s} {'SWID':<8s} {'Description'}")
    print(f"  {'-'*20}  {'-'*6}  {'-'*40}")
    for name, _hex, swid, _subid, desc in features_for(0x0003):
        print(f"  {name:<20s} 0x{swid:04x}  {desc}")
    print()

def parse_args(argv):
    """Parse args compatibly with old positional usage + new --model flag."""
    # Support old positional style: VIN [USB_PATH]
    # New style: VIN [USB_PATH] [--model KEY] [--featlevel-subid HEX]
    p = argparse.ArgumentParser(
        description='Generate Porsche PCM 3.1 activation codes',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    p.add_argument('vin', nargs='?', help='17-character VIN')
    p.add_argument('usb_path', nargs='?', default=None,
                   help='Optional USB drive path (e.g. E:\\ on Windows)')
    p.add_argument('--model', '-m', default=None,
                   help='Vehicle model key (see --list-models). Sets the FeatureLevel SubID.')
    p.add_argument('--featlevel-subid', default=None,
                   help='Override FeatureLevel SubID directly (e.g. 0x0039). For unknown models.')
    p.add_argument('--list-models', action='store_true',
                   help='Show available model keys and exit')
    p.add_argument('--list-features', action='store_true',
                   help='Show feature names for --add/--remove and exit')
    p.add_argument('--quiet', '-q', action='store_true',
                   help='Only print activation codes, no headers')
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--add', metavar='FEATURES', action='append',
                      help='Add/replace features in an existing PagSWAct.002. '
                           'Comma-separated, and the flag may be repeated.')
    mode.add_argument('--remove', metavar='FEATURES', action='append',
                      help='Remove features from an existing PagSWAct.002. '
                           'Comma-separated, and the flag may be repeated.')
    mode.add_argument('--diag', metavar='USB_PATH',
                      help='Build a read-only diagnostic USB stick (no VIN needed)')
    mode.add_argument('--show', metavar='PATH',
                      help='Decode an existing PagSWAct.002 (file or its directory)')
    p.add_argument('--subid', action='append', metavar='NAME=HEX',
                   help='Select a non-default SubID variant, e.g. '
                        'NavDBEurope=0x0001. Repeatable.')
    p.add_argument('--from-backup', nargs='?', const='', default=None, metavar='FILE',
                   help="Build an activation stick from the car's own backup "
                        "(PagSWAct_backup_*.002). Name the file when several exist.")
    p.add_argument('--no-xor', action='store_true',
                   help='Write copie_scr.sh as plaintext (testing only; the PCM needs XOR)')
    return p.parse_args(argv)

def main(argv=None):
    """Dispatch to a mode, or list codes and optionally write a stick.

    Returns a process exit code: 0 on success, 1 for anything the user can
    fix. Argument errors below the argparse level are reported here rather
    than raised, so the CLI never shows a traceback for bad input.
    """
    args = parse_args(argv or sys.argv[1:])

    if args.list_models:
        list_models()
        return 0

    if args.list_features:
        list_features()
        return 0

    if args.from_backup is not None and (args.diag or args.show):
        print("Error: --from-backup cannot be combined with --diag or --show.",
              file=sys.stderr)
        return 1

    if args.show:
        return show_pagswact(args.show,
                             args.vin.upper() if args.vin else None)

    if args.diag:
        write_usb(args.diag, RUN_DIAG, xor=not args.no_xor)
        if not args.quiet:
            enc = 'plaintext (--no-xor)' if args.no_xor else 'XOR-encoded'
            print(f"\n  Diagnostic stick written to {args.diag}/: "
                  f"copie_scr.sh ({enc}) + run.sh")
            print("  Insert after the PCM has booted; nothing on the car is modified.\n")
        return 0

    if args.from_backup is not None:
        return build_from_backup(args)

    if not args.vin:
        print("Error: VIN required. Use --help for usage.", file=sys.stderr)
        return 1

    try:
        vin = validate_vin(args.vin)
        features, _subid, model_desc = features_from_args(args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.add or args.remove:
        names = split_feature_names(args.add or args.remove)
        if not names:
            print("Error: no feature names given.", file=sys.stderr)
            return 1
        try:
            matches = resolve_feature_names(names, features)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        if not args.usb_path:
            print("Error: --add/--remove need a USB path containing PagSWAct.002.",
                  file=sys.stderr)
            return 1
        target = os.path.join(args.usb_path, 'PagSWAct.002')
        if not os.path.exists(target):
            print(f"Error: {target} not found. Write the full feature set first.",
                  file=sys.stderr)
            return 1
        try:
            recs = load_records(target)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        recs = apply_feature_edits(recs, matches, vin, adding=bool(args.add))
        with open(target, 'wb') as f:
            for _, rec in recs:
                f.write(rec)
        if not args.quiet:
            verb = 'Added' if args.add else 'Removed'
            listing = ', '.join(m[0] for m in matches)
            print(f"\n  {verb} {listing} — {target} now holds {len(recs)} features")
        return 0

    if not args.quiet:
        print(f"\n  PCM-Forge — All 26 Activation Codes")
        print(f"  VIN:   {vin}")
        print(f"  Model: {model_desc}\n")

    for name, feat_hex, swid, subid, desc in features:
        code = generate_code(vin, feat_hex)
        if args.quiet:
            print(f"{name}:{code}")
        else:
            print(f"  {name:<22s}: {code}  {desc}")

    if args.usb_path:
        out = args.usb_path
        write_usb(out, RUN_ACTIVATE, xor=not args.no_xor,
                  pagswact=build_pagswact(vin, features))
        if not args.quiet:
            enc = 'plaintext (--no-xor)' if args.no_xor else 'XOR-encoded'
            print(f"\n  Written to {out}/: copie_scr.sh ({enc}) + run.sh + PagSWAct.002")
    else:
        # Behavior change from original: previously always wrote to "."
        # Now only writes if USB path is given. Hint at the option.
        if not args.quiet:
            print(f"\n  (Codes only; pass a USB path to write PagSWAct.002 + copie_scr.sh)")

    return 0

if __name__ == '__main__':
    sys.exit(main())
