import discord
from discord import app_commands
import requests
import hashlib
import asyncio
import math
import json as _json
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
BF_API = "https://bloxflip.com/api"
ALLOWED_CHANNEL_ID = int(os.environ.get("ALLOWED_CHANNEL_ID", "1496136776786514094"))
ANNOUNCEMENT_CHANNEL_ID = int(os.environ.get("ANNOUNCEMENT_CHANNEL_ID", "1491470835544883230"))
OWNER_ID = int(os.environ.get("OWNER_ID", "558546183883194372"))

maintenance_mode = False
maintenance_reason = ""


def wrong_channel_embed():
    return discord.Embed(
        description=f"sorry sir, but use on the predict channel g — <#{ALLOWED_CHANNEL_ID}>",
        color=discord.Color.red()
    )


def maintenance_embed():
    return discord.Embed(
        description=f"🍊 **maintenance mode has started**, {maintenance_reason} we are gonna be up pretty soon. please use the paid bot for now.",
        color=discord.Color.orange()
    )


class LimitsBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.linked_users = {}
        self.user_methods = {}

    async def setup_hook(self):
        await self.tree.sync()


bot = LimitsBot()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BLOXFLIP API HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def bf_headers(token):
    return {
        "x-auth-token": token,
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Referer": "https://bloxflip.com/",
    }

def bf_cookies(token):
    return {"app.at": token}

def bf_get(token, path):
    try:
        r = requests.get(f"{BF_API}/{path}", headers=bf_headers(token), cookies=bf_cookies(token), timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def validate_token(token):
    try:
        r = requests.get(f"{BF_API}/user", headers=bf_headers(token), cookies=bf_cookies(token), timeout=10)
        if r.status_code == 200:
            d = r.json()
            if d.get("success"):
                profile = d.get("profile", {})
                wallet = d.get("wallet", {})
                balances = wallet.get("balances", {})
                return {
                    "valid": True,
                    "username": profile.get("username") or d.get("username", "unknown"),
                    "balance": balances.get("FLIPCOINS", 0.0)
                }
        return {"valid": False}
    except:
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

def get_history(token, count=500):
    games = []
    ids = set()
    for page in range(20):
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
            if gid and gid not in ids:
                bombs = g.get("mineLocations") or g.get("mines_locations") or g.get("bombLocations") or g.get("bombs") or []
                if isinstance(bombs, list) and len(bombs) > 0:
                    games.append({
                        "bombs": bombs,
                        "mc": g.get("minesAmount") or g.get("minesCount") or len(bombs)
                    })
                    ids.add(gid)
        if len(games) >= count:
            break
    return games[:count]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CRYPTO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def sha256hex(d):
    return hashlib.sha256(d.encode() if isinstance(d, str) else d).hexdigest()

def sha256bytes(d):
    return hashlib.sha256(d.encode() if isinstance(d, str) else d).digest()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DHC0 ALGORITHM — Dynamic Hot Cluster v2
#  7-submodel ENSEMBLE with confidence scoring
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _norm(arr):
    mn, mx = min(arr), max(arr)
    rng = mx - mn or 1
    return [(v - mn) / rng for v in arr]

def _bombs(g):
    return [b for b in g.get("bombs", []) if isinstance(b, int) and 0 <= b < 25]

def _submodel_frequency(games, num_bombs):
    d = [0.0] * 25
    n = len(games)
    if n < 1: return d
    freq = [0.0] * 25
    for g in games:
        for b in _bombs(g): freq[b] += 1
    return _norm(freq)

def _submodel_recency(games, num_bombs):
    d = [0.0] * 25
    n = len(games)
    if n < 1: return d
    for gi in range(n):
        w = math.exp(-2.5 * (1 - gi / n))
        for b in _bombs(games[gi]): d[b] += w
    return _norm(d)

def _submodel_same_mc(games, num_bombs):
    d = [0.0] * 25
    same = [g for g in games if (g.get("mc") or 3) == num_bombs]
    if len(same) < 3: return d
    for g in same:
        for b in _bombs(g): d[b] += 1
    return _norm(d)

def _submodel_transition(games, num_bombs):
    d = [0.0] * 25
    n = len(games)
    if n < 10: return d
    trans = [[0.0] * 25 for _ in range(25)]
    for gi in range(1, n):
        for p in _bombs(games[gi-1]):
            for c in _bombs(games[gi]): trans[p][c] += 1
    for p in range(25):
        t = sum(trans[p]) or 1
        for c in range(25): trans[p][c] /= t
    if n >= 2:
        for lb in _bombs(games[-1]):
            for i in range(25): d[i] += trans[lb][i]
    return _norm(d)

def _submodel_monte_carlo(games, num_bombs, round_id, nonce, sims=1500):
    n = len(games)
    if n < 5: return [0.0] * 25
    prob = [num_bombs / 25] * 25
    for gi in range(n):
        decay = math.exp(-3 * (1 - gi / n))
        for b in _bombs(games[gi]): prob[b] += decay
    t = sum(prob) or 1
    prob = [p / t for p in prob]
    for g in games[-3:]:
        for b in _bombs(g): prob[b] *= 1.25
    t = sum(prob) or 1
    prob = [p / t for p in prob]

    seed = sha256bytes(f"{round_id}:{nonce}:mc")
    s0 = int.from_bytes(seed[:8], 'big') if len(seed) >= 8 else 12345
    s1 = int.from_bytes(seed[8:16], 'big') if len(seed) >= 16 else 67890
    M = (1 << 64) - 1
    state = [s0 & M, s1 & M]

    def rng():
        x, y = state
        x ^= (x << 23) & M; x ^= (x >> 17) & M; x ^= y & M; x ^= (y >> 26) & M
        state[0] = y; state[1] = x & M
        return ((y + x) & M) / (M + 1)

    surv = [0.0] * 25
    for _ in range(sims):
        placed = set(); sf = 0
        while len(placed) < num_bombs and sf < 100:
            sf += 1
            roll = rng(); cum = 0
            for tt in range(25):
                cum += prob[tt]
                if roll <= cum and tt not in placed:
                    placed.add(tt); break
        for tt in range(25):
            if tt not in placed: surv[tt] += 1

    danger = [1 - (s / sims) for s in surv]
    return _norm(danger)

def _submodel_knn(games, num_bombs, round_id, nonce):
    d = [0.0] * 25
    n = len(games)
    if n < 10: return d
    sig = sha256hex(f"{round_id}:{nonce}:knn")
    scored = []
    for g in games:
        gid = g.get("_id", "")
        if not gid: continue
        gs = sha256hex(str(gid))
        sim = sum(1 for a, b in zip(sig, gs) if a == b) / len(sig)
        scored.append((sim, g))
    scored.sort(key=lambda x: -x[0])
    for sim, g in scored[:20]:
        for b in _bombs(g): d[b] += sim
    return _norm(d)

def _submodel_neural(games, num_bombs, round_id, nonce):
    d = [0.0] * 25
    n = len(games)
    if n < 20: return d
    finp = [0.0] * 25
    for g in games[-80:]:
        for b in _bombs(g): finp[b] += 1
    t = sum(finp) or 1
    inp = [v / t for v in finp]

    w1 = sha256bytes(f"{round_id}:{nonce}:nn:w1")
    w2 = sha256bytes(f"{round_id}:{nonce}:nn:w2")
    w3 = sha256bytes(f"{round_id}:{nonce}:nn:w3")
    def relu(x): return max(0, x)

    h1 = [relu(sum(inp[k] * (w1[(j+k) % 32] / 255 - 0.5) * 2 for k in range(25))) for j in range(40)]
    h2 = [relu(sum(h1[k] * (w2[(j+k) % 32] / 255 - 0.5) * 2 for k in range(40))) for j in range(30)]
    for i in range(25):
        d[i] = sum(h2[j] * (w3[(i+j) % 32] / 255 - 0.5) * 2 for j in range(30))
    return _norm(d)

def dhc0_prediction(token, num_bombs, safe_count, round_id, nonce, revealed):
    games = get_history(token, 500)
    n = len(games)
    if n < 20:
        return None, 0, n

    G = games[-300:] if n > 300 else games

    m1 = _submodel_frequency(G, num_bombs)
    m2 = _submodel_recency(G, num_bombs)
    m3 = _submodel_same_mc(G, num_bombs)
    m4 = _submodel_transition(G, num_bombs)
    m5 = _submodel_monte_carlo(G, num_bombs, round_id, nonce)
    m6 = _submodel_knn(G, num_bombs, round_id, nonce)
    m7 = _submodel_neural(G, num_bombs, round_id, nonce)

    total_w = 1.2 + 1.5 + 2.0 + 1.3 + 1.4 + 1.1 + 0.8

    final = [0.0] * 25
    for i in range(25):
        final[i] = (m1[i]*1.2 + m2[i]*1.5 + m3[i]*2.0 + m4[i]*1.3 + m5[i]*1.4 + m6[i]*1.1 + m7[i]*0.8) / total_w

    confidence_sum = 0
    for i in range(25):
        vals = [m1[i], m2[i], m3[i], m4[i], m5[i], m6[i], m7[i]]
        mean = sum(vals) / len(vals)
        std = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))
        confidence_sum += (1 - std)
    confidence_pct = max(0, min(100, (confidence_sum / 25) * 100))

    if len(games) >= 1:
        for b in _bombs(games[-1]):
            final[b] += 0.15

    for i in range(25):
        run = 0
        for gi in range(len(G) - 1, -1, -1):
            if i not in _bombs(G[gi]): run += 1
            else: break
        if run >= 15:
            final[i] += 0.05

    safe = pick_spread(final, safe_count, round_id=round_id, nonce=nonce, exclude=set(revealed))
    return safe, confidence_pct, n


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SPATIAL SPREAD PICKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def pick_spread(scores, safe_count, round_id="", nonce=0, exclude=None):
    exclude = exclude or set()
    valid = [(i, scores[i]) for i in range(25) if i not in exclude]
    valid.sort(key=lambda x: x[1])

    if not valid:
        return []

    pool_size = min(len(valid), max(safe_count * 4, 12))
    pool = [i for i, _ in valid[:pool_size]]

    seed_hex = sha256hex(f"{round_id}:{nonce}:pick:v3")
    weighted = []
    for idx, tile in enumerate(pool):
        slot = (tile * 4) % 60
        rng_val = int(seed_hex[slot:slot + 4], 16) / 0xFFFF
        rank_weight = 1.0 - (idx / pool_size) * 0.55
        priority = rng_val * rank_weight
        weighted.append((tile, priority))

    weighted.sort(key=lambda x: -x[1])
    shuffled = [t for t, _ in weighted]

    for current_dist in [3, 2]:
        picked = []
        for tile in shuffled:
            if len(picked) >= safe_count:
                break
            if not picked:
                picked.append(tile)
                continue
            tr, tc = divmod(tile, 5)
            cheb = min(max(abs(tr - pr), abs(tc - pc)) for pr, pc in (divmod(p, 5) for p in picked))
            if cheb >= current_dist:
                picked.append(tile)
        if len(picked) >= safe_count:
            return picked[:safe_count]

    return shuffled[:safe_count]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MODEL 1 — 14-layer past-games trained predictor
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def model1_prediction(token, num_bombs, safe_count, round_id, nonce, revealed):
    games = get_history(token, 500)
    n = len(games)
    if n < 15:
        return None, 0, n

    G = games[-200:] if n > 200 else games
    ng = len(G)
    exp = num_bombs / 25
    d = [0.0] * 25

    freq = [0.0] * 25
    for g in G:
        for b in _bombs(g): freq[b] += 1
    for i in range(25): d[i] += (freq[i] / ng - exp) * ng * 2.5

    same_mc = [g for g in G if (g.get("mc") or 3) == num_bombs]
    if len(same_mc) >= 5:
        sf = [0.0] * 25
        for g in same_mc:
            for b in _bombs(g): sf[b] += 1
        for i in range(25): d[i] += (sf[i] / len(same_mc) - exp) * len(same_mc) * 3.5

    for gi in range(ng):
        w = math.exp(-3 * (1 - gi / ng))
        for b in _bombs(G[gi]): d[b] += w * 2

    w20 = G[-20:]
    if len(w20) >= 3:
        wf = [0.0] * 25
        for g in w20:
            for b in _bombs(g): wf[b] += 1
        for i in range(25): d[i] += (wf[i] / len(w20) - exp) * len(w20) * 4

    for g in G[-5:]:
        for b in _bombs(g): d[b] += 4

    if ng >= 2:
        for b in _bombs(G[-1]): d[b] -= 3

    for i in range(25):
        a = freq[i] + 1; b = ng - freq[i] + 1
        d[i] += (a / (a + b) - exp) * ng * 2.0

    if ng >= 10:
        trans = [[0.0] * 25 for _ in range(25)]
        for gi in range(1, ng):
            for p in _bombs(G[gi-1]):
                for c in _bombs(G[gi]): trans[p][c] += 1
        for p in range(25):
            t = sum(trans[p]) or 1
            for c in range(25): trans[p][c] /= t
        if ng >= 2:
            for lb in _bombs(G[-1]):
                for i in range(25): d[i] += trans[lb][i] * 14

    pairs = {}
    for g in G[-100:]:
        bs = _bombs(g)
        for i in range(len(bs)):
            for j in range(i+1, len(bs)):
                k = (min(bs[i], bs[j]), max(bs[i], bs[j]))
                pairs[k] = pairs.get(k, 0) + 1
    for (a, b), cnt in sorted(pairs.items(), key=lambda x: -x[1])[:25]:
        d[a] += cnt * 0.5; d[b] += cnt * 0.5

    alpha = 2 / 8; ev = [0.0] * 25
    for g in G:
        cur = [0.0] * 25
        for b in _bombs(g): cur[b] = 1
        for i in range(25): ev[i] = alpha * cur[i] + (1 - alpha) * ev[i]
    for i in range(25): d[i] += ev[i] * 18

    for i in range(25):
        run = 0
        for gi in range(ng - 1, -1, -1):
            if i not in _bombs(G[gi]): run += 1
            else: break
        if run >= 8: d[i] += (run - 7) * 2.0

    quads = [
        [0,1,2,5,6,7,10,11,12], [2,3,4,7,8,9,12,13,14],
        [10,11,12,15,16,17,20,21,22], [12,13,14,17,18,19,22,23,24]
    ]
    qh = [sum(freq[t] for t in q) / len(q) for q in quads]
    qavg = sum(qh) / 4
    for qi, q in enumerate(quads):
        for t in q: d[t] += (qh[qi] - qavg) / max(qavg, 1) * 6

    for i in range(25):
        r, c = divmod(i, 5); ns = 0; nc = 0
        for dr in range(-1, 2):
            for dc in range(-1, 2):
                if dr == 0 and dc == 0: continue
                nr, ncc = r + dr, c + dc
                if 0 <= nr < 5 and 0 <= ncc < 5:
                    ns += freq[nr * 5 + ncc]; nc += 1
        if nc: d[i] += (ns / nc) / max(ng, 1) * 12

    ranked = sorted(range(25), key=lambda i: -d[i])
    for k in range(min(num_bombs, 25)): d[ranked[k]] += 8
    for k in range(num_bombs, 25): d[ranked[k]] -= 5

    if ng >= 15:
        score_std = math.sqrt(sum((v - sum(d)/25)**2 for v in d) / 25)
        confidence = max(40, min(85, score_std * 4))
    else:
        confidence = 35

    safe = pick_spread(d, safe_count, round_id=round_id, nonce=nonce, exclude=set(revealed))
    return safe, confidence, n


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@bot.tree.command(name="freelink", description="Link your Bloxflip account to limit's free prediction")
@app_commands.describe(token="Your app.at token from Bloxflip")
async def freelink(interaction: discord.Interaction, token: str):
    if interaction.channel_id != ALLOWED_CHANNEL_ID:
        return await interaction.response.send_message(embed=wrong_channel_embed(), ephemeral=True)
    if maintenance_mode:
        return await interaction.response.send_message(embed=maintenance_embed(), ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    result = validate_token(token)
    if not result["valid"]:
        embed = discord.Embed(description="Token invalid or expired. Get a fresh app.at from Bloxflip.", color=discord.Color.red())
        await interaction.followup.send(embed=embed)
        return

    bot.linked_users[str(interaction.user.id)] = {
        "token": token, "username": result["username"], "balance": result["balance"]
    }

    embed = discord.Embed(
        title="Successfully Linked",
        description=f"Yo, {interaction.user.mention} you have successfully linked to **limit's free prediction**",
        color=0x1a1aff
    )
    embed.add_field(name="Flipcoin", value=f"{result['balance']:,.2f}", inline=True)
    embed.add_field(name="Username", value=result["username"], inline=True)
    embed.set_thumbnail(url="https://media.tenor.com/5VW4_0Zru5YAAAAi/check-mark-check.gif")
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="setmethod", description="Choose prediction method")
@app_commands.describe(method="Select prediction model")
@app_commands.choices(method=[
    app_commands.Choice(name="Model 1 (Past Games Trained)", value="model1"),
    app_commands.Choice(name="DHC0 Algorithm", value="dhc0")
])
async def setmethod(interaction: discord.Interaction, method: app_commands.Choice[str]):
    if interaction.channel_id != ALLOWED_CHANNEL_ID:
        return await interaction.response.send_message(embed=wrong_channel_embed(), ephemeral=True)
    if maintenance_mode:
        return await interaction.response.send_message(embed=maintenance_embed(), ephemeral=True)
    user_id = str(interaction.user.id)
    bot.user_methods[user_id] = method.value
    embed = discord.Embed(description=f"Method set to **{method.name}**", color=0x1a1aff)
    embed.set_footer(text="limits free")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="freemines", description="free mines predictor for the people on limit")
@app_commands.describe(safespot="Number of safe spots (max 6)")
async def freemines(interaction: discord.Interaction, safespot: int = 6):
    if interaction.channel_id != ALLOWED_CHANNEL_ID:
        return await interaction.response.send_message(embed=wrong_channel_embed(), ephemeral=True)
    if maintenance_mode:
        return await interaction.response.send_message(embed=maintenance_embed())
    await interaction.response.defer(ephemeral=False)
    user_id = str(interaction.user.id)

    if user_id not in bot.linked_users:
        embed = discord.Embed(description="You are not linked. Use `/freelink` first.", color=discord.Color.red())
        await interaction.followup.send(embed=embed)
        return

    if user_id not in bot.user_methods:
        embed = discord.Embed(
            description="You haven't picked a prediction method. Run `/setmethod` first.",
            color=discord.Color.red()
        )
        embed.set_footer(text="limits free")
        await interaction.followup.send(embed=embed)
        return

    token = bot.linked_users[user_id]["token"]
    game = get_active_game(token)

    if not game:
        embed = discord.Embed(description="You do not have an active game, please start a game", color=discord.Color.red())
        embed.set_thumbnail(url="https://media.tenor.com/GI8sfHyex88AAAAi/red-cross.gif")
        embed.set_footer(text="limits free")
        await interaction.followup.send(embed=embed)
        return

    if game["mines"] > 4:
        embed = discord.Embed(description="Not able to analyze your game sir, maximum bombs is 4", color=discord.Color.red())
        embed.set_thumbnail(url="https://media.tenor.com/GI8sfHyex88AAAAi/red-cross.gif")
        embed.set_footer(text="limits free")
        await interaction.followup.send(embed=embed)
        return

    loading = discord.Embed(description="Generating your prediction...", color=0x1a1aff)
    loading.set_footer(text="limits free")
    await interaction.followup.send(embed=loading)
    await asyncio.sleep(2)

    method = bot.user_methods[user_id]
    safespot = max(1, min(safespot, 6))
    safespot = min(safespot, 25 - game["mines"])

    safe = []
    confidence = 0
    games_analyzed = 0
    if method == "model1":
        safe, confidence, games_analyzed = model1_prediction(
            token, game["mines"], safespot,
            game["round_id"], game["nonce"], game["revealed"]
        )
        if safe is None:
            embed = discord.Embed(
                description=f"Need at least 15 past games for Model 1. You have {games_analyzed}. Play more games first.",
                color=discord.Color.red()
            )
            embed.set_footer(text="limits free")
            await interaction.edit_original_response(embed=embed)
            return
    else:
        safe, confidence, games_analyzed = dhc0_prediction(
            token, game["mines"], safespot,
            game["round_id"], game["nonce"], game["revealed"]
        )
        if safe is None:
            embed = discord.Embed(
                description=f"Need at least 20 past games for DHC0. You have {games_analyzed}. Play more games first.",
                color=discord.Color.red()
            )
            embed.set_footer(text="limits free")
            await interaction.edit_original_response(embed=embed)
            return

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
    embed.add_field(name="Mines", value=str(game["mines"]), inline=False)
    embed.add_field(name="Safe", value=str(len(safe)), inline=False)
    embed.add_field(name="Bet", value=f"{game['bet']:.2f} FC", inline=False)
    embed.add_field(
        name="\u200b",
        value="feeling unlucky? upgrade to **limit's premium** to get more accurate predictions",
        inline=False
    )
    embed.set_footer(text="limits free")
    await interaction.edit_original_response(embed=embed)


@bot.tree.command(name="maintenancestart", description="Start maintenance mode (Owner only)")
@app_commands.describe(reason="Reason for maintenance", hours="Estimated downtime (e.g. 2H)")
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
                f"**Devs**\n"
                f"- DHC0\n"
                f"- x.2re\n"
                f"- microp1to\n\n"
                f"**Media Manager**\n"
                f"- xd_ekon\n\n"
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


bot.run(BOT_TOKEN)