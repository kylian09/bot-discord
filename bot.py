import discord
from discord.ext import commands
import time
import json
import discord
from discord.ext import commands

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Récupère le token sécurisé depuis Render ou les variables d'environnement
TOKEN = os.getenv("DISCORD_TOKEN")
# Configuration des permissions (Intents)
intents = discord.Intents.default()
intents.voice_states = True  # Indispensable pour détecter les mouvements vocaux
intents.members = True       # Pour récupérer les noms des membres
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

FICHIER_DATA = "temps_vocal.json"
sessions_actives = {} # Stocke l'heure d'arrivée en vocal : {user_id: timestamp}

# --- Fonctions de sauvegarde ---
def charger_donnees():
    if os.path.exists(FICHIER_DATA):
        with open(FICHIER_DATA, "r") as f:
            return json.load(f)
    return {}

def sauvegarder_donnees(donnees):
    with open(FICHIER_DATA, "w") as f:
        json.dump(donnees, f, indent=4)

def formater_temps(secondes):
    heures = int(secondes // 3600)
    minutes = int((secondes % 3600) // 60)
    sec = int(secondes % 60)
    return f"{heures}h {minutes}m {sec}s"

# --- Événements du bot ---
@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user}")
    # Si le bot démarre alors que des gens sont déjà en vocal, on lance leur chrono
    for guild in bot.guilds:
        for channel in guild.voice_channels:
            for member in channel.members:
                if not member.bot:
                    sessions_actives[str(member.id)] = time.time()

@bot.event
async def on_voice_state_update(member, before, after):
    # On ignore les autres bots
    if member.bot:
        return

    user_id = str(member.id)
    maintenant = time.time()

    # Cas 1 : L'utilisateur rejoint un salon vocal (il n'était dans aucun salon avant)
    if before.channel is None and after.channel is not None:
        sessions_actives[user_id] = maintenant

    # Cas 2 : L'utilisateur quitte un salon vocal (il n'est plus dans aucun salon après)
    elif before.channel is not None and after.channel is None:
        if user_id in sessions_actives:
            temps_passe = maintenant - sessions_actives.pop(user_id)
            
            donnees = charger_donnees()
            donnees[user_id] = donnees.get(user_id, 0) + temps_passe
            sauvegarder_donnees(donnees)

# --- Commandes Discord ---
@bot.command(name="temps")
async def voir_temps(ctx, membre: discord.Member = None):
    """Affiche le temps vocal d'un membre (ou de soi-même si personne n'est mentionné)"""
    membre = membre or ctx.author
    user_id = str(membre.id)
    
    donnees = charger_donnees()
    total_secondes = donnees.get(user_id, 0)

    # Si l'utilisateur est actuellement en vocal, on ajoute le temps de sa session en cours
    if user_id in sessions_actives:
        total_secondes += time.time() - sessions_actives[user_id]

    await ctx.send(f"🎙️ **{membre.display_name}** a passé **{formater_temps(total_secondes)}** en vocal.")

@bot.command(name="topvocal")
async def classement_vocal(ctx):
    """Affiche le top 10 des utilisateurs les plus actifs en vocal"""
    donnees = charger_donnees()
    maintenant = time.time()

    # On met à jour temporairement avec ceux qui sont actuellement connectés
    for user_id, debut in sessions_actives.items():
        donnees[user_id] = donnees.get(user_id, 0) + (maintenant - debut)

    if not donnees:
        await ctx.send("Aucune donnée vocale enregistrée pour le moment.")
        return

    # Tri du plus grand au plus petit
    classement = sorted(donnees.items(), key=lambda x: x[1], reverse=True)[:10]
    
    message = "🏆 **Classement du temps passé en vocal :**\n\n"
    for index, (user_id, secondes) in enumerate(classement, start=1):
        membre = ctx.guild.get_member(int(user_id))
        nom = membre.display_name if membre else f"Utilisateur inconnu ({user_id})"
        message += f"**{index}.** {nom} — `{formater_temps(secondes)}`\n"

    await ctx.send(message)

# Lancement du bot
bot.run(TOKEN)
