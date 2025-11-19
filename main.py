import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from datetime import datetime, timedelta
import re
from flask import Flask
from threading import Thread

with open("cooldowns.json", "r") as f:
    try:
        json.load(f)
    except json.JSONDecodeError:
        print("❌ cooldowns.json defekt, erstelle Backup")
        import shutil
        shutil.copy("cooldowns.json", "cooldowns.json.bak")
        open("cooldowns.json", "w").write("{}")


app = Flask("")

@app.route("/")
def home():
    return "Bot läuft!"

def run():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
def keep_alive():
    t = Thread(target=run)
    t.daemon = True  # wichtig, sonst blockiert Thread
    t.start()
    
t = Thread(target=run)
t.start()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

CONFIG_FILE = "config.json"
COOLDOWNS_FILE = "cooldowns.json"

def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"❌ Fehler beim Laden von {filename}: {e}")
            print(f"Erstelle Backup und verwende leeres Dictionary...")
            try:
                backup_name = f"{filename}.backup"
                if os.path.exists(filename):
                    os.rename(filename, backup_name)
                    print(f"Backup erstellt: {backup_name}")
            except Exception as backup_error:
                print(f"Konnte kein Backup erstellen: {backup_error}")
            return {}
    return {}

def save_json(filename, data):
    try:
        temp_filename = f"{filename}.tmp"
        with open(temp_filename, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(temp_filename, filename)
    except (IOError, OSError) as e:
        print(f"❌ Fehler beim Speichern von {filename}: {e}")

def parse_interval(interval_str):
    match = re.match(r'(\d+)([dhm])', interval_str.lower())
    if not match:
        return None
    
    amount, unit = match.groups()
    amount = int(amount)
    
    if unit == 'd':
        return timedelta(days=amount)
    elif unit == 'h':
        return timedelta(hours=amount)
    elif unit == 'm':
        return timedelta(minutes=amount)
    return None

def format_timedelta(td):
    total_seconds = int(td.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    parts = []
    if days > 0:
        parts.append(f"{days} Tag{'e' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} Stunde{'n' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} Minute{'n' if minutes != 1 else ''}")
    if seconds > 0 and not parts:
        parts.append(f"{seconds} Sekunde{'n' if seconds != 1 else ''}")
    
    return ", ".join(parts) if parts else "0 Sekunden"

@bot.event
async def on_ready():
    print(f'{bot.user} ist online und bereit!')
    try:
        synced = await bot.tree.sync()
        print(f'{len(synced)} Slash-Commands synchronisiert')
    except Exception as e:
        print(f'Fehler beim Synchronisieren der Commands: {e}')

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ Du brauchst die **Server verwalten** Berechtigung, um diesen Command zu nutzen!",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"❌ Ein Fehler ist aufgetreten: {str(error)}",
            ephemeral=True
        )

@bot.tree.command(name="set-window", description="Setze ein Message-Cooldown-Fenster für eine Rolle in einem Channel")
@app_commands.describe(
    role="Die Rolle, für die das Cooldown gelten soll",
    channel="Der Channel, in dem das Cooldown aktiv ist",
    interval="Das Cooldown-Intervall (z.B. 3d, 7d, 12h, 30m)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def set_window(interaction: discord.Interaction, role: discord.Role, channel: discord.TextChannel, interval: str):
    parsed_interval = parse_interval(interval)
    
    if parsed_interval is None:
        await interaction.response.send_message(
            "❌ Ungültiges Intervall-Format! Nutze z.B.: `3d` (3 Tage), `12h` (12 Stunden), `30m` (30 Minuten)",
            ephemeral=True
        )
        return
    
    config = load_json(CONFIG_FILE)
    
    key = f"{interaction.guild_id}_{channel.id}_{role.id}"
    config[key] = {
        "guild_id": interaction.guild_id,
        "channel_id": channel.id,
        "role_id": role.id,
        "interval": interval,
        "interval_seconds": int(parsed_interval.total_seconds())
    }
    
    save_json(CONFIG_FILE, config)
    
    await interaction.response.send_message(
        f"✅ **Cooldown-Fenster erstellt!**\n"
        f"📍 **Channel:** {channel.mention}\n"
        f"👥 **Rolle:** {role.mention}\n"
        f"⏱️ **Intervall:** {interval} ({format_timedelta(parsed_interval)})\n\n"
        f"User mit dieser Rolle können nur alle **{format_timedelta(parsed_interval)}** eine Nachricht senden.",
        ephemeral=True
    )

@bot.event
async def on_message(message):
    try:
async def on_message(message):
    if message.author.bot:
        return
    
    await bot.process_commands(message)
    
    if not message.guild:
        return
    
    config = load_json(CONFIG_FILE)
    cooldowns = load_json(COOLDOWNS_FILE)
    
    # Alle Regeln im aktuellen Channel für aktuelle Guild
    applicable_rules = [
        rule for key, rule in config.items()
        if rule["channel_id"] == message.channel.id and rule["guild_id"] == message.guild.id
    ]
    
    # Sammle alle Rollen des Users, die eine Regel haben
    user_roles_with_rules = [
        rule for rule in applicable_rules
        if any(r.id == rule["role_id"] for r in message.author.roles)
    ]
    
    if not user_roles_with_rules:
        return  # keine Regel für diese Rollen
    
    # Wähle die Rolle mit dem KÜRZESTEN Cooldown
    rule_to_apply = min(user_roles_with_rules, key=lambda r: r["interval_seconds"])
    role_id = rule_to_apply["role_id"]
    
    # user_key jetzt rollenabhängig
    user_key = f"{message.guild.id}_{message.channel.id}_{role_id}_{message.author.id}"
    
    # Prüfen, ob Cooldown aktiv ist
    if user_key in cooldowns:
        try:
            last_message_time = datetime.fromisoformat(cooldowns[user_key])
            interval_seconds = rule_to_apply["interval_seconds"]
            time_passed = (datetime.now() - last_message_time).total_seconds()
            
            if time_passed < interval_seconds:
                remaining = timedelta(seconds=interval_seconds - time_passed)
                
                try:
                    await message.delete()
                    warning = await message.channel.send(
                        f"⏳ {message.author.mention}, du kannst erst in **{format_timedelta(remaining)}** wieder schreiben!"
                    )
                    await warning.delete(delay=5)
                except discord.Forbidden:
                    print(f"Keine Berechtigung, Nachricht von {message.author} zu löschen")
                
                return
        except (ValueError, KeyError) as e:
            print(f"❌ Fehler beim Parsen des Cooldown-Zeitstempels für {user_key}: {e}")
            del cooldowns[user_key]
    
    # Cooldown starten / aktualisieren
    cooldowns[user_key] = datetime.now().isoformat()
    save_json(COOLDOWNS_FILE, cooldowns)
    except Exception as e:
        print(f"❌ Fehler in on_message: {e}")

token = os.getenv('DISCORD_BOT_TOKEN')
if not token:
    print("❌ FEHLER: DISCORD_BOT_TOKEN nicht gefunden!")
else:
    keep_alive()
    bot.run(token)




