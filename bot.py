import discord
from discord import app_commands
from discord.ext import commands
import json
import time
import os
from flask import Flask
from threading import Thread

# --- SERVEUR WEB POUR RENDER (24/7) ---
app = Flask('')

@app.route('/')
def home():
    return "Le bot est en ligne !"

def run():
    app.run(host='0.0.0.0', port=8080)

def garder_en_vie():
    t = Thread(target=run)
    t.start()

# --- CONFIGURATION DU BOT ---
intents = discord.Intents.default()
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

FICHIER_STATS = "stats_vocal.json"

# Tes 4 rôles autorisés pour les commandes staff/admin
ROLES_AUTORISES = [
    1548727369693401158,
    1548727368338645243,
    1548732386009817309,
    1548727366128509048
]

# Fonction de vérification des permissions
def a_la_permission(member: discord.Member) -> bool:
    return any(role.id in ROLES_AUTORISES for role in member.roles)

# --- GESTION DES DONNÉES VOCALES ---
sessions_actives = {}  # {user_id: timestamp_debut}

def charger_stats():
    if os.path.exists(FICHIER_STATS):
        with open(FICHIER_STATS, "r") as f:
            return json.load(f)
    return {}

def sauvegarder_stats(stats):
    with open(FICHIER_STATS, "w") as f:
        json.dump(stats, f, indent=4)

def formater_temps(secondes):
    secondes = int(secondes)
    heures, reste = divmod(secondes, 3600)
    minutes, sec = divmod(reste, 60)
    return f"{heures}h {minutes}m {sec}s"

# --- ÉVÉNEMENTS ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Connecté en tant que {bot.user}")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    user_id = str(member.id)
    maintenant = time.time()
    stats = charger_stats()

    # Rejoint un vocal ou se démute
    if after.channel is not None and not after.self_mute and not after.mute:
        if user_id not in sessions_actives:
            sessions_actives[user_id] = maintenant

    # Quitte le vocal ou se mute
    elif after.channel is None or after.self_mute or after.mute:
        if user_id in sessions_actives:
            duree = maintenant - sessions_actives.pop(user_id)
            stats[user_id] = stats.get(user_id, 0) + duree
            sauvegarder_stats(stats)

# --- COMMANDES SLASH ---

# 1. /topvocal (Accessible à TOUT LE MONDE - aucune restriction)
@bot.tree.command(name="topvocal", description="Affiche le classement des 10 membres les plus actifs en vocal")
async def topvocal_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    stats = charger_stats()
    maintenant = time.time()

    # Ajoute le temps des sessions en cours sans écraser le fichier
    temps_totaux = stats.copy()
    for uid, debut in sessions_actives.items():
        temps_totaux[uid] = temps_totaux.get(uid, 0) + (maintenant - debut)

    if not temps_totaux:
        await interaction.followup.send("Aucune donnée vocale enregistrée pour le moment.")
        return

    classement = sorted(temps_totaux.items(), key=lambda x: x[1], reverse=True)[:10]

    embed = discord.Embed(title="🏆 Top 10 Activité Vocale", color=discord.Color.gold())
    description = ""
    for index, (uid, total_sec) in enumerate(classement, start=1):
        description += f"**{index}.** <@{uid}> — `{formater_temps(total_sec)}`\n"

    embed.description = description
    await interaction.followup.send(embed=embed)

# 2. /time (Accessible à TOUT LE MONDE)
@bot.tree.command(name="time", description="Affiche ton temps vocal ou celui d'un membre")
async def time_cmd(interaction: discord.Interaction, membre: discord.Member = None):
    await interaction.response.defer()

    cible = membre or interaction.user
    uid = str(cible.id)
    stats = charger_stats()
    total = stats.get(uid, 0)

    if uid in sessions_actives:
        total += time.time() - sessions_actives[uid]

    await interaction.followup.send(f"⏱️ Temps vocal de **{cible.display_name}** : `{formater_temps(total)}`")

# 3. /all (RESTREINT aux 4 rôles)
@bot.tree.command(name="all", description="Affiche le temps vocal de tous les membres enregistrés")
async def all_cmd(interaction: discord.Interaction):
    if not a_la_permission(interaction.user):
        await interaction.response.send_message("❌ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True)
        return

    await interaction.response.defer()
    stats = charger_stats()
    maintenant = time.time()

    temps_totaux = stats.copy()
    for uid, debut in sessions_actives.items():
        temps_totaux[uid] = temps_totaux.get(uid, 0) + (maintenant - debut)

    if not temps_totaux:
        await interaction.followup.send("Aucune donnée enregistrée.")
        return

    classement = sorted(temps_totaux.items(), key=lambda x: x[1], reverse=True)
    lignes = [f"<@{uid}> : `{formater_temps(sec)}`" for uid, sec in classement]
    
    embed = discord.Embed(title="📊 Temps vocal de tous les membres", description="\n".join(lignes[:25]), color=discord.Color.blue())
    await interaction.followup.send(embed=embed)

# 4. /ajt (RESTREINT aux 4 rôles)
@bot.tree.command(name="ajt", description="Ajoute ou retire des minutes à un membre")
async def ajt_cmd(interaction: discord.Interaction, membre: discord.Member, minutes: int):
    if not a_la_permission(interaction.user):
        await interaction.response.send_message("❌ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True)
        return

    await interaction.response.defer()
    stats = charger_stats()
    uid = str(membre.id)
    stats[uid] = max(0, stats.get(uid, 0) + (minutes * 60))
    sauvegarder_stats(stats)

    await interaction.followup.send(f"✅ **{minutes} minutes** modifiées pour **{membre.display_name}**. Nouveau total : `{formater_temps(stats[uid])}`")

# 5. /clear (RESTREINT aux 4 rôles)
@bot.tree.command(name="clear", description="Réinitialise toutes les statistiques vocales")
async def clear_cmd(interaction: discord.Interaction):
    if not a_la_permission(interaction.user):
        await interaction.response.send_message("❌ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True)
        return

    await interaction.response.defer()
    sessions_actives.clear()
    sauvegarder_stats({})
    await interaction.followup.send("🗑️ Toutes les statistiques vocales ont été remises à zéro.")

# --- LANCEMENT ---
garder_en_vie()
bot.run(os.environ["DISCORD_TOKEN"])
