import os
import json
import time
import logging
from threading import Thread
from flask import Flask
import discord
from discord.ext import commands
from discord import app_commands

# --- SERVEUR WEB FLASK (POUR RENDER 24/7) ---
app = Flask('')

# Masque les warnings du serveur de développement dans les logs Render
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/')
def home():
    return "Le bot vocal est en ligne !"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# --- CONFIGURATION DU BOT DISCORD ---
intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

FICHIER_STATS = "stats_vocal.json"
sessions_actives = {}

# --- FONCTIONS DE GESTION DES DONNÉES ---
def charger_donnees():
    if os.path.exists(FICHIER_STATS):
        try:
            with open(FICHIER_STATS, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def sauvegarder_donnees(donnees):
    with open(FICHIER_STATS, "w", encoding="utf-8") as f:
        json.dump(donnees, f, indent=4)

def formater_temps(secondes):
    secondes = int(secondes)
    heures, reste = divmod(secondes, 3600)
    minutes, sec = divmod(reste, 60)
    if heures > 0:
        return f"{heures}h {minutes}m {sec}s"
    elif minutes > 0:
        return f"{minutes}m {sec}s"
    else:
        return f"{sec}s"

# --- ÉVÉNEMENTS DU BOT ---
@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synchronisé {len(synced)} commande(s) slash.")
    except Exception as e:
        print(f"Erreur lors de la synchronisation : {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    user_id = str(member.id)
    maintenant = time.time()

    etait_actif = before.channel is not None and not before.self_mute and not before.mute
    est_actif = after.channel is not None and not after.self_mute and not after.mute

    # Rejoint un vocal ou se démute
    if not etait_actif and est_actif:
        sessions_actives[user_id] = maintenant

    # Quitte un vocal ou se mute
    elif etait_actif and not est_actif:
        if user_id in sessions_actives:
            debut = sessions_actives.pop(user_id)
            duree = maintenant - debut
            donnees = charger_donnees()
            donnees[user_id] = donnees.get(user_id, 0) + duree
            sauvegarder_donnees(donnees)

# --- COMMANDES SLASH (/) ---
@bot.tree.command(name="time", description="Affiche le temps passé en vocal (le tien ou celui d'un autre membre)")
@app_commands.describe(membre="Le membre dont tu veux voir le temps (laisse vide pour toi)")
async def time_cmd(interaction: discord.Interaction, membre: discord.Member = None):
    await interaction.response.defer()
    
    cible = membre or interaction.user
    user_id_str = str(cible.id)
    
    donnees = charger_donnees()
    maintenant = time.time()

    total_secondes = donnees.get(user_id_str, 0)

    if user_id_str in sessions_actives:
        debut = sessions_actives[user_id_str]
        total_secondes += (maintenant - debut)

    if total_secondes == 0:
        await interaction.followup.send(f"⏱️ **{cible.display_name}** n'a pas encore passé de temps en vocal.")
    else:
        await interaction.followup.send(f"⏱️ **{cible.display_name}** a passé **{formater_temps(total_secondes)}** en vocal.")

@bot.tree.command(name="topvocal", description="Affiche le top 10 des utilisateurs les plus actifs en vocal")
async def topvocal_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    
    donnees = charger_donnees()
    maintenant = time.time()

    for user_id, debut in sessions_actives.items():
        donnees[user_id] = donnees.get(user_id, 0) + (maintenant - debut)

    if not donnees:
        await interaction.followup.send("Aucune donnée vocale enregistrée pour le moment.")
        return

    classement = sorted(donnees.items(), key=lambda x: x[1], reverse=True)[:10]

    message = "🏆 **Top 10 du temps passé en vocal :**\n\n"
    for index, (user_id, secondes) in enumerate(classement, start=1):
        membre = interaction.guild.get_member(int(user_id))
        nom = membre.display_name if membre else f"Utilisateur inconnu ({user_id})"
        message += f"**{index}.** {nom} – `{formater_temps(secondes)}`\n"

    await interaction.followup.send(message)

@bot.tree.command(name="all", description="Affiche le temps passé en vocal de absolument tout le monde")
async def all_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    
    donnees = charger_donnees()
    maintenant = time.time()

    # Ajoute les sessions actives en direct
    for user_id, debut in sessions_actives.items():
        donnees[user_id] = donnees.get(user_id, 0) + (maintenant - debut)

    if not donnees:
        await interaction.followup.send("Aucune donnée vocale enregistrée pour le moment.")
        return

    classement = sorted(donnees.items(), key=lambda x: x[1], reverse=True)

    lignes = ["📊 **Temps vocal de tous les membres :**\n"]
    for index, (user_id, secondes) in enumerate(classement, start=1):
        membre = interaction.guild.get_member(int(user_id))
        nom = membre.display_name if membre else f"Utilisateur inconnu ({user_id})"
        lignes.append(f"**{index}.** {nom} – `{formater_temps(secondes)}`")

    # Envoi découpé par paquets pour respecter la limite de 2000 caractères de Discord
    message_courant = ""
    for ligne in lignes:
        if len(message_courant) + len(ligne) + 1 > 1900:
            await interaction.followup.send(message_courant)
            message_courant = ligne + "\n"
        else:
            message_courant += ligne + "\n"

    if message_courant:
        await interaction.followup.send(message_courant)

@bot.tree.command(name="clear", description="Remet à 0 les heures de vocal de tout le monde")
@app_commands.default_permissions(administrator=True)
async def clear_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    # Vide le fichier JSON
    sauvegarder_donnees({})

    # Remet à zéro le chrono de ceux qui sont actuellement connectés en vocal sans casser leur suivi
    maintenant = time.time()
    for user_id in list(sessions_actives.keys()):
        sessions_actives[user_id] = maintenant

    await interaction.followup.send("🔄 **Toutes les heures de vocal ont été remises à 0 !**")

# --- LANCEMENT ---
if __name__ == "__main__":
    keep_alive()
    TOKEN = os.environ.get("DISCORD_TOKEN")
    bot.run(TOKEN)
