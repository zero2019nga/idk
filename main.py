import os
import math
import time
import hashlib
import struct
import json as _json
import asyncio
from typing import Dict, Optional, List, Tuple

import requests
import discord
from discord import app_commands

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
BF_API = os.environ.get("BF_API", "https://bloxflip.com/api").strip()

ALLOWED_CHANNEL_ID = int(os.environ.get("ALLOWED_CHANNEL_ID", "1496136776786514094"))
ANNOUNCEMENT_CHANNEL_ID = int(os.environ.get("ANNOUNCEMENT_CHANNEL_ID", "1491470835544883230"))
OWNER_ID = int(os.environ.get("OWNER_ID", "558546183883194372"))

MAX_MINES = int(os.environ.get("MAX_MINES", "5"))
MAX_SAFE_SPOTS = int(os.environ.get("MAX_SAFE_SPOTS", "7"))
HISTORY_COUNT = int(os.environ.get("HISTORY_COUNT", "500"))

BANK_PATH = os.path.join(os.path.dirname(__file__), "x2re_layer_bank.bin")

maintenance_mode = False
maintenance_reason = ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RAM-ONLY STORES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RuntimeStore:
    """
    RAM-only token store.
    No database. No JSON file. No disk token saving.
    Users stay linked while the Railway process stays alive.
    Links reset after restart/redeploy/crash.
    """
    def __init__(self):
        self.linked_users: Dict[str, dict] = {}
        self.user_methods: Dict[str, str] = {}

    def link_user(self, discord_id: str, token: str, username: str, balance: float):
        self.linked_users[discord_id] = {
            "token": token,
            "username": username,
            "balance": balance,
            "linked_at": int(time.time()),
        }

    def unlink_user(self, discord_id: str) -> bool:
        return self.linked_users.pop(discord_id, None) is not None

    def get_link(self, discord_id: str) -> Optional[dict]:
        return self.linked_users.get(discord_id)

    def set_method(self, discord_id: str, method: str):
        self.user_methods[discord_id] = method

    def get_method(self, discord_id: str) -> Optional[str]:
        return self.user_methods.get(discord_id)

class CooldownStore:
    def __init__(self, seconds: float = 8.0):
        self.seconds = float(seconds)
        self.last = {}

    def remaining(self, key: str) -> float:
        now = time.monotonic()
        last = self.last.get(key, 0.0)
        left = self.seconds - (now - last)
        return max(0.0, left)

    def touch(self, key: str):
        self.last[key] = time.monotonic()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DISCORD EMBEDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def wrong_channel_embed(channel_id: int):
    return discord.Embed(
        description=f"sorry sir, but use on the predict channel g — <#{channel_id}>",
        color=discord.Color.red()
    )

def maintenance_embed(reason: str):
    return discord.Embed(
        description=f"🍊 **maintenance mode has started**, {reason} we are gonna be up pretty soon. please use the paid bot for now.",
        color=discord.Color.orange()
    )

def prediction_embed(safe, method, mines, bet):
    safe_set = set(safe)
    grid_lines = []
    for row in range(5):
        cells = []
        for col in range(5):
            i = row * 5 + col
            cells.append("✅" if i in safe_set else "❌")
        grid_lines.append(" ".join(cells))
    grid = "\n".join(grid_lines)

    embed = discord.Embed(title="Prediction", description=grid, color=0x1a1aff)
    embed.add_field(name="Algo", value=method, inline=False)
    embed.add_field(name="Mines", value=str(mines), inline=False)
    embed.add_field(name="Safe", value=str(len(safe)), inline=False)
    embed.add_field(name="Bet", value=f"{float(bet):.2f} FC", inline=False)
    embed.add_field(
        name="\u200b",
        value="feeling unlucky? upgrade to **limit's premium** to get more accurate predictions",
        inline=False
    )
    embed.set_footer(text="limits free")
    return embed

def update_embed():
    embed = discord.Embed(
        title="Latest Update — 16 May, 11:00 AM",
        description=(
            "**We rewrited Model 1 and upgraded it into x.2re.**\n\n"
            "x.2re now uses a deeper danger engine, bigger history reads, stronger least-danger ranking, "
            "and supports up to **5 bombs** with up to **7 safespots**."
        ),
        color=0x1a1aff
    )
    embed.add_field(
        name="x.2re",
        value="Upgraded multi-signal danger engine for free mines predictions.",
        inline=False
    )
    embed.set_footer(text="limits free")
    return embed

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BLOXFLIP HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def bf_headers(token):
    return {
        "x-auth-token": token,
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
            "Mobile/15E148 Safari/604.1"
        ),
        "Referer": "https://bloxflip.com/",
    }

def bf_cookies(token):
    return {"app.at": token}

def bf_get(token, path):
    try:
        r = requests.get(
            f"{BF_API}/{path}",
            headers=bf_headers(token),
            cookies=bf_cookies(token),
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def validate_token(token):
    try:
        r = requests.get(
            f"{BF_API}/user",
            headers=bf_headers(token),
            cookies=bf_cookies(token),
            timeout=10,
        )
        if r.status_code == 200:
            d = r.json()
            if d.get("success"):
                profile = d.get("profile", {})
                wallet = d.get("wallet", {})
                balances = wallet.get("balances", {})
                return {
                    "valid": True,
                    "username": profile.get("username") or d.get("username", "unknown"),
                    "balance": balances.get("FLIPCOINS", 0.0),
                }
        return {"valid": False}
    except Exception:
        return {"valid": False}

def get_active_game(token):
    game_res = bf_get(token, "games/mines")
    if not game_res or not game_res.get("hasGame"):
        return None
    game = game_res.get("game") or {}
    return {
        "round_id": str(game.get("id") or game.get("_id") or ""),
        "mines": game.get("minesAmount") or game.get("minesCount") or game.get("mines") or 3,
        "bet": game.get("betAmount", 0),
        "revealed": game.get("revealedTiles") or game.get("revealed") or [],
        "nonce": game.get("nonce", 0),
    }

def get_history(token, count=HISTORY_COUNT):
    games = []
    ids = set()
    for page in range(30):
        d = bf_get(token, f"games/mines/history?page={page}&size=50")
        if not d:
            break
        history = d if isinstance(d, list) else d.get("data") or d.get("games") or d.get("history") or []
        if not history:
            break
        for g in history:
            if not isinstance(g, dict):
                continue
            gid = g.get("_id") or g.get("id") or ""
            if isinstance(gid, dict):
                gid = _json.dumps(gid, sort_keys=True)
            gid = str(gid)
            if not gid or gid in ids:
                continue

            bombs = (
                g.get("mineLocations")
                or g.get("mines_locations")
                or g.get("bombLocations")
                or g.get("bombs")
                or []
            )

            if isinstance(bombs, list) and len(bombs) > 0:
                games.append({
                    "_id": gid,
                    "bombs": bombs,
                    "mc": g.get("minesAmount") or g.get("minesCount") or len(bombs),
                })
                ids.add(gid)

        if len(games) >= count:
            break

    return games[:count]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# x.2re ALGO HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def sha256hex(d):
    return hashlib.sha256(d.encode() if isinstance(d, str) else d).hexdigest()

def sha256bytes(d):
    return hashlib.sha256(d.encode() if isinstance(d, str) else d).digest()

def _bombs(g):
    return [b for b in g.get("bombs", []) if isinstance(b, int) and 0 <= b < 25]

def _safe_norm(vals: List[float]) -> List[float]:
    mn = min(vals)
    mx = max(vals)
    rg = mx - mn
    if abs(rg) < 1e-12:
        return [0.0 for _ in vals]
    return [(v - mn) / rg for v in vals]

def _freq(games):
    out = [0.0] * 25
    if not games:
        return out
    for g in games:
        for b in _bombs(g):
            out[b] += 1.0
    return _safe_norm(out)

def _recency(games, strength=3.2):
    out = [0.0] * 25
    n = len(games)
    if n == 0:
        return out
    for gi, g in enumerate(games):
        w = math.exp(-strength * (1 - (gi + 1) / n))
        for b in _bombs(g):
            out[b] += w
    return _safe_norm(out)

def _same_mc(games, mc):
    same = [g for g in games if int(g.get("mc") or 0) == int(mc)]
    if len(same) < 4:
        return [0.0] * 25
    return _freq(same[-180:])

def _row_pressure(base):
    out = [0.0] * 25
    for r in range(5):
        val = sum(base[r * 5 + c] for c in range(5)) / 5
        for c in range(5):
            out[r * 5 + c] = val
    return _safe_norm(out)

def _col_pressure(base):
    out = [0.0] * 25
    for c in range(5):
        val = sum(base[r * 5 + c] for r in range(5)) / 5
        for r in range(5):
            out[r * 5 + c] = val
    return _safe_norm(out)

def _diag_pressure(base):
    out = [0.0] * 25
    for i in range(25):
        r, c = divmod(i, 5)
        vals = []
        for j in range(25):
            rr, cc = divmod(j, 5)
            if rr - cc == r - c or rr + cc == r + c:
                vals.append(base[j])
        out[i] = sum(vals) / max(1, len(vals))
    return _safe_norm(out)

def _neighbor_pressure(base, radius=1):
    out = [0.0] * 25
    for i in range(25):
        r, c = divmod(i, 5)
        vals = []
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < 5 and 0 <= nc < 5:
                    vals.append(base[nr * 5 + nc])
        out[i] = sum(vals) / max(1, len(vals))
    return _safe_norm(out)

def _streak_reversal(games):
    out = [0.0] * 25
    n = len(games)
    if n == 0:
        return out
    for tile in range(25):
        miss_run = 0
        hit_run = 0
        for gi in range(n - 1, -1, -1):
            bs = _bombs(games[gi])
            if tile in bs:
                hit_run += 1
                if miss_run:
                    break
            else:
                miss_run += 1
                if hit_run:
                    break
        out[tile] = max(0.0, (miss_run - 10) * 0.04) + hit_run * 0.18
    return _safe_norm(out)

def _volatility(games, windows=(8, 16, 32, 64)):
    if len(games) < 16:
        return [0.0] * 25
    samples = []
    for w in windows:
        if len(games) >= w:
            samples.append(_freq(games[-w:]))
    out = [0.0] * 25
    for tile in range(25):
        vals = [s[tile] for s in samples]
        mean = sum(vals) / len(vals)
        out[tile] = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))
    return _safe_norm(out)

def _transition(games):
    out = [0.0] * 25
    n = len(games)
    if n < 20:
        return out
    trans = [[0.0] * 25 for _ in range(25)]
    for gi in range(1, n):
        prev = _bombs(games[gi - 1])
        cur = _bombs(games[gi])
        for p in prev:
            for c in cur:
                trans[p][c] += 1.0
    for p in range(25):
        row_sum = sum(trans[p]) or 1.0
        for c in range(25):
            trans[p][c] /= row_sum
    for lb in _bombs(games[-1]):
        for i in range(25):
            out[i] += trans[lb][i]
    return _safe_norm(out)

def _pair_cluster(games):
    out = [0.0] * 25
    if len(games) < 30:
        return out
    pairs = {}
    for g in games[-200:]:
        bs = _bombs(g)
        for a_i in range(len(bs)):
            for b_i in range(a_i + 1, len(bs)):
                a, b = sorted((bs[a_i], bs[b_i]))
                pairs[(a, b)] = pairs.get((a, b), 0.0) + 1.0
    for (a, b), cnt in sorted(pairs.items(), key=lambda x: -x[1])[:80]:
        out[a] += cnt
        out[b] += cnt
    return _safe_norm(out)

def _shape_pressure(base):
    masks = [
        [0,4,20,24],
        [1,2,3,5,9,10,14,15,19,21,22,23],
        [6,7,8,11,12,13,16,17,18],
        [2,7,10,11,12,13,14,17,22],
        [0,2,4,10,12,14,20,22,24],
        [0,1,2,3,4],
        [20,21,22,23,24],
        [0,5,10,15,20],
        [4,9,14,19,24],
        [0,6,12,18,24],
        [4,8,12,16,20],
        [i for i in range(25) if i % 2 == 0],
        [i for i in range(25) if i % 2 == 1],
    ]
    out = [0.0] * 25
    for mask in masks:
        val = sum(base[i] for i in mask) / len(mask)
        for i in mask:
            out[i] += val
    return _safe_norm(out)

def _load_bank_bytes():
    try:
        with open(BANK_PATH, "rb") as f:
            return f.read()
    except Exception:
        return b""

def _bank_value(bank: bytes, offset: int) -> float:
    if not bank or len(bank) < 8:
        h = sha256bytes(f"x2re-bank-fallback:{offset}")
        return int.from_bytes(h[:4], "big") / 0xFFFFFFFF
    o = offset % (len(bank) - 4)
    return struct.unpack_from(">I", bank, o)[0] / 0xFFFFFFFF

def _micro_ensemble(games, num_bombs, round_id, nonce, feature_stack, layer_count=1024):
    """
    x.2re 1024 micro-layer bank.

    Each micro-layer is a deterministic weak danger scorer over 25 tiles.
    It blends feature maps with transforms and a calibration value from x2re_layer_bank.bin.
    """
    bank = _load_bank_bytes()
    out = [0.0] * 25
    fs_len = len(feature_stack)
    if fs_len == 0:
        return out

    seed = sha256hex(f"{round_id}:{nonce}:{num_bombs}:x2re-micro")
    seed_int = int(seed[:16], 16)

    for layer in range(layer_count):
        f_idx = int(_bank_value(bank, layer * 17) * fs_len) % fs_len
        base = feature_stack[f_idx]
        mode = int(_bank_value(bank, layer * 31) * 9) % 9
        gain = 0.35 + _bank_value(bank, layer * 43) * 1.65
        bias = (_bank_value(bank, layer * 59) - 0.5) * 0.06

        for tile in range(25):
            r, c = divmod(tile, 5)
            val = base[tile]

            if mode == 1:
                val = (val + base[r * 5 + ((c + 1) % 5)]) / 2
            elif mode == 2:
                val = (val + base[((r + 1) % 5) * 5 + c]) / 2
            elif mode == 3:
                mirror = r * 5 + (4 - c)
                val = (val + base[mirror]) / 2
            elif mode == 4:
                mirror = (4 - r) * 5 + c
                val = (val + base[mirror]) / 2
            elif mode == 5:
                diag = c * 5 + r
                val = (val + base[diag]) / 2
            elif mode == 6:
                val = val * (1.0 + (abs(r - 2) + abs(c - 2)) * 0.04)
            elif mode == 7:
                val = val * (1.0 - max(0, 2 - (abs(r - 2) + abs(c - 2))) * 0.04)
            elif mode == 8:
                salt = sha256hex(f"{seed_int}:{layer}:{tile}")
                val = val + (int(salt[:4], 16) / 0xFFFF - 0.5) * 0.015

            out[tile] += val * gain + bias

    return _safe_norm(out)

def pick_spread(scores, safe_count, round_id="", nonce=0, exclude=None):
    exclude = set(exclude or [])
    valid = [(i, scores[i]) for i in range(25) if i not in exclude]
    valid.sort(key=lambda x: x[1])

    if not valid:
        return []

    pool_size = min(len(valid), max(safe_count * 5, 14))
    pool = [i for i, _ in valid[:pool_size]]

    seed_hex = sha256hex(f"{round_id}:{nonce}:x2re-pick")
    weighted = []
    for idx, tile in enumerate(pool):
        slot = (tile * 7 + idx * 11) % 58
        rng_val = int(seed_hex[slot:slot + 4], 16) / 0xFFFF
        rank_weight = 1.0 - (idx / max(1, pool_size)) * 0.45
        priority = rng_val * 0.18 + rank_weight * 0.82
        weighted.append((tile, priority))
    weighted.sort(key=lambda x: -x[1])
    shuffled = [t for t, _ in weighted]

    for min_dist in [3, 2, 1]:
        picked = []
        for tile in shuffled:
            if len(picked) >= safe_count:
                break
            if not picked:
                picked.append(tile)
                continue
            tr, tc = divmod(tile, 5)
            cheb = min(max(abs(tr - pr), abs(tc - pc)) for pr, pc in (divmod(p, 5) for p in picked))
            if cheb >= min_dist:
                picked.append(tile)
        if len(picked) >= safe_count:
            return picked[:safe_count]

    return shuffled[:safe_count]

def x2re_prediction(token, num_bombs, safe_count, round_id, nonce, revealed) -> Tuple[List[int], int]:
    games = get_history(token, 500)
    n = len(games)
    if n < 25:
        return None, n

    G = games[-350:] if len(games) > 350 else games

    long_f = _freq(G)
    f250 = _freq(G[-250:])
    f150 = _freq(G[-150:])
    f75 = _freq(G[-75:])
    f40 = _freq(G[-40:])
    f20 = _freq(G[-20:])
    f10 = _freq(G[-10:])

    rec_a = _recency(G, 2.4)
    rec_b = _recency(G, 4.0)
    same = _same_mc(G, num_bombs)
    row = _row_pressure(long_f)
    col = _col_pressure(long_f)
    diag = _diag_pressure(long_f)
    neigh1 = _neighbor_pressure(long_f, 1)
    neigh2 = _neighbor_pressure(long_f, 2)
    streak = _streak_reversal(G)
    vol = _volatility(G)
    trans = _transition(G)
    pair = _pair_cluster(G)
    shape = _shape_pressure(long_f)

    feature_stack = [
        long_f, f250, f150, f75, f40, f20, f10,
        rec_a, rec_b, same, row, col, diag, neigh1, neigh2,
        streak, vol, trans, pair, shape,
    ]

    micro = _micro_ensemble(G, num_bombs, round_id, nonce, feature_stack, layer_count=1024)

    final = [0.0] * 25
    weighted_features = [
        (long_f, 1.10),
        (f250, 0.90),
        (f150, 1.05),
        (f75, 1.20),
        (f40, 1.25),
        (f20, 0.95),
        (rec_a, 1.10),
        (rec_b, 1.05),
        (same, 1.40),
        (row, 0.35),
        (col, 0.35),
        (diag, 0.25),
        (neigh1, 0.55),
        (neigh2, 0.35),
        (streak, 0.40),
        (vol, 0.30),
        (trans, 0.45),
        (pair, 0.35),
        (shape, 0.20),
        (micro, 1.65),
    ]

    total_w = sum(w for _, w in weighted_features)
    for feat, w in weighted_features:
        for i in range(25):
            final[i] += feat[i] * w
    final = [v / total_w for v in final]

    exclude = set()
    for x in revealed or []:
        try:
            x = int(x)
            if 0 <= x < 25:
                exclude.add(x)
        except Exception:
            continue

    tie = sha256hex(f"{round_id}:{nonce}:x2re-final")
    for i in range(25):
        jitter = int(tie[(i * 2) % 60:((i * 2) % 60) + 2], 16) / 255
        final[i] += (jitter - 0.5) * 0.006

    safe = pick_spread(final, safe_count, round_id=round_id, nonce=nonce, exclude=exclude)
    return safe, n

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DISCORD BOT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class LimitsBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.runtime = RuntimeStore()
        self.cooldowns = CooldownStore(seconds=8)

    async def setup_hook(self):
        await self.tree.sync()

bot = LimitsBot()

@bot.tree.command(name="freelink", description="Link your Bloxflip account to limit's free prediction")
@app_commands.describe(token="Your app.at token from Bloxflip")
async def freelink(interaction: discord.Interaction, token: str):
    if interaction.channel_id != ALLOWED_CHANNEL_ID:
        return await interaction.response.send_message(embed=wrong_channel_embed(ALLOWED_CHANNEL_ID), ephemeral=True)
    if maintenance_mode:
        return await interaction.response.send_message(embed=maintenance_embed(maintenance_reason), ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    token = token.strip()

    result = validate_token(token)
    if not result["valid"]:
        embed = discord.Embed(
            description="Token invalid or expired. Get a fresh app.at from Bloxflip.",
            color=discord.Color.red()
        )
        return await interaction.followup.send(embed=embed, ephemeral=True)

    bot.runtime.link_user(
        discord_id=str(interaction.user.id),
        token=token,
        username=result["username"],
        balance=result["balance"]
    )

    embed = discord.Embed(
        title="Successfully Linked",
        description=f"Yo, {interaction.user.mention} you have successfully linked to **limit's free prediction**",
        color=0x1a1aff
    )
    embed.add_field(name="Flipcoin", value=f"{result['balance']:,.2f}", inline=True)
    embed.add_field(name="Username", value=result["username"], inline=True)
    embed.set_thumbnail(url="https://media.tenor.com/5VW4_0Zru5YAAAAi/check-mark-check.gif")
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="freeunlink", description="Unlink your Bloxflip token from this bot session")
async def freeunlink(interaction: discord.Interaction):
    if interaction.channel_id != ALLOWED_CHANNEL_ID:
        return await interaction.response.send_message(embed=wrong_channel_embed(ALLOWED_CHANNEL_ID), ephemeral=True)
    removed = bot.runtime.unlink_user(str(interaction.user.id))
    if removed:
        msg = "Your linked token was removed from this bot session."
        color = discord.Color.green()
    else:
        msg = "You were not linked."
        color = discord.Color.red()
    await interaction.response.send_message(embed=discord.Embed(description=msg, color=color), ephemeral=True)

@bot.tree.command(name="setmethod", description="Choose prediction method")
@app_commands.describe(method="Select prediction model")
@app_commands.choices(method=[
    app_commands.Choice(name="x.2re", value="x2re")
])
async def setmethod(interaction: discord.Interaction, method: app_commands.Choice[str]):
    if interaction.channel_id != ALLOWED_CHANNEL_ID:
        return await interaction.response.send_message(embed=wrong_channel_embed(ALLOWED_CHANNEL_ID), ephemeral=True)
    if maintenance_mode:
        return await interaction.response.send_message(embed=maintenance_embed(maintenance_reason), ephemeral=True)

    bot.runtime.set_method(str(interaction.user.id), method.value)
    embed = discord.Embed(description=f"Method set to **{method.name}**", color=0x1a1aff)
    embed.set_footer(text="limits free")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="freemines", description="free mines predictor for the people on limit")
@app_commands.describe(safespot=f"Number of safe spots, max {MAX_SAFE_SPOTS}")
async def freemines(interaction: discord.Interaction, safespot: int = 7):
    global maintenance_mode, maintenance_reason

    if interaction.channel_id != ALLOWED_CHANNEL_ID:
        return await interaction.response.send_message(embed=wrong_channel_embed(ALLOWED_CHANNEL_ID), ephemeral=True)
    if maintenance_mode:
        return await interaction.response.send_message(embed=maintenance_embed(maintenance_reason), ephemeral=True)

    user_id = str(interaction.user.id)
    cd_left = bot.cooldowns.remaining(user_id)
    if cd_left > 0:
        embed = discord.Embed(
            description=f"Slow down g. Try again in **{cd_left:.1f}s**.",
            color=discord.Color.red()
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    await interaction.response.defer(ephemeral=False)
    bot.cooldowns.touch(user_id)

    linked = bot.runtime.get_link(user_id)
    if not linked:
        embed = discord.Embed(description="You are not linked. Use `/freelink` first.", color=discord.Color.red())
        return await interaction.followup.send(embed=embed)

    method = bot.runtime.get_method(user_id)
    if not method:
        embed = discord.Embed(
            description="You haven't picked a prediction method. Run `/setmethod` first.",
            color=discord.Color.red()
        )
        embed.set_footer(text="limits free")
        return await interaction.followup.send(embed=embed)

    token = linked["token"]
    game = get_active_game(token)

    if not game:
        embed = discord.Embed(description="You do not have an active game, please start a game", color=discord.Color.red())
        embed.set_thumbnail(url="https://media.tenor.com/GI8sfHyex88AAAAi/red-cross.gif")
        embed.set_footer(text="limits free")
        return await interaction.followup.send(embed=embed)

    if int(game["mines"]) > MAX_MINES:
        embed = discord.Embed(
            description=f"Not able to analyze your game sir, maximum bombs is {MAX_MINES}",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url="https://media.tenor.com/GI8sfHyex88AAAAi/red-cross.gif")
        embed.set_footer(text="limits free")
        return await interaction.followup.send(embed=embed)

    loading = discord.Embed(description="Generating your prediction...", color=0x1a1aff)
    loading.set_footer(text="limits free")
    await interaction.followup.send(embed=loading)
    await asyncio.sleep(2)

    safespot = max(1, min(int(safespot), MAX_SAFE_SPOTS))
    safespot = min(safespot, 25 - int(game["mines"]))

    safe, games_analyzed = x2re_prediction(
        token=token,
        num_bombs=int(game["mines"]),
        safe_count=safespot,
        round_id=str(game["round_id"]),
        nonce=int(game["nonce"] or 0),
        revealed=game["revealed"],
    )

    if safe is None:
        embed = discord.Embed(
            description=f"Need at least 25 past games for x.2re. You have {games_analyzed}. Play more games first.",
            color=discord.Color.red()
        )
        embed.set_footer(text="limits free")
        return await interaction.edit_original_response(embed=embed)

    embed = prediction_embed(
        safe=safe,
        method="x.2re",
        mines=game["mines"],
        bet=game["bet"],
    )
    await interaction.edit_original_response(embed=embed)

@bot.tree.command(name="update", description="Show the latest free bot update")
async def update(interaction: discord.Interaction):
    await interaction.response.send_message(embed=update_embed(), ephemeral=False)

@bot.tree.command(name="ping", description="Check if the free bot is alive")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=discord.Embed(description=f"Online as **{bot.user}**", color=0x1a1aff),
        ephemeral=True
    )

@bot.tree.command(name="maintenancestart", description="Start maintenance mode (Owner only)")
@app_commands.describe(reason="Reason for maintenance", hours="Estimated downtime, example 2H")
async def maintenancestart(interaction: discord.Interaction, reason: str, hours: str):
    if interaction.user.id != OWNER_ID:
        embed = discord.Embed(description="You don't have permission to use this command.", color=discord.Color.red())
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    global maintenance_mode, maintenance_reason
    maintenance_mode = True
    maintenance_reason = reason

    embed = discord.Embed(
        description=f"🍊 **maintenance mode has started**, {reason} we are gonna be up pretty soon. please use the paid bot for now.",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)

    channel = bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
    if channel:
        announce_embed = discord.Embed(
            title="🍊 Maintenance Started",
            description=(
                f"**maintenance has started on free bot**, we detected an issue **({reason})**, "
                f"we are terribly sorry for this. limits dev team is gonna work on the issue as quick as possible, "
                f"we are the best on the market, buy premium for less maintenances.\n\n"
                f"**Estimated downtime:** {hours}\n\n"
                f"**Devs**\n- DHC0\n- x.2re\n- microp1to\n\n"
                f"**Media Manager**\n- xd_ekon\n\n"
                f"*our team is working on the issue.*"
            ),
            color=discord.Color.orange()
        )
        await channel.send(embed=announce_embed)

@bot.tree.command(name="maintenanceend", description="End maintenance mode (Owner only)")
async def maintenanceend(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        embed = discord.Embed(description="You don't have permission to use this command.", color=discord.Color.red())
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    global maintenance_mode, maintenance_reason
    maintenance_mode = False
    maintenance_reason = ""

    embed = discord.Embed(
        description="✅ **maintenance mode has ended**, everything is back to normal. use the free bot again.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

    channel = bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
    if channel:
        announce_embed = discord.Embed(
            title="✅ Maintenance Ended",
            description="The free bot is back online. Thank you for your patience.",
            color=discord.Color.green()
        )
        await channel.send(embed=announce_embed)

@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it in Railway Variables.")

bot.run(BOT_TOKEN)
