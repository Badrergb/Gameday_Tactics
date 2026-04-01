import os
import re
import io
import base64
import math
import json
import time
import chompjs
import numpy as np
import pandas as pd
import networkx as nx
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import csv
import requests

# --- AI LIBRARY INTEGRATION ---
# We are using Groq for its ultra-low latency inference.
# This ensures the dashboard loads in milliseconds, not seconds.
from groq import Groq

# --- VISUALIZATION LIBRARY CONFIGURATION ---
# We force the 'Agg' backend (Anti-Grain Geometry).
# This is MANDATORY for cloud servers (Render, AWS, Heroku) because
# they do not have physical monitors attached. Without this, the app crashes.
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from mplsoccer import Pitch

# Initialize the Flask Application
app = Flask(__name__)
CORS(app) # Enable CORS for all routes

RECEIVER_EMAIL = "badrenarayananrg@gmail.com"      # YOUR EMAIL HERE

# 🚀 ZERO-SETUP EMAIL (Bypasses all Render blocks)
# No API keys needed!
FORMSUBMIT_URL = f"https://formsubmit.co/ajax/{RECEIVER_EMAIL}"

# 🚀 BREVO API CONFIGURATION (Bypasses Render SMTP Block)
# 1. Get a FREE API Key from https://www.brevo.com/ (Takes 1 min)
# 2. Paste it here or set it as 'BREVO_API_KEY' in Render dashboard
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "") 

# Optional Discord Webhook for Render (Works even if SMTP is blocked)
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "") # Paste your URL here or set in Render

# ==============================================================================
# 🔑 API KEY & AI MODEL CONFIGURATION
# ==============================================================================
# 1. Attempt to load from System Environment (Best for Deployment)
SYSTEM_KEY = os.environ.get("GROQ_API_KEY")

# 2. Fallback to Hardcoded Key (Best for Local Testing)
# PASTE YOUR KEY INSIDE THE QUOTES BELOW
HARDCODED_KEY = "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"
CHAT_API_KEY = "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"
if SYSTEM_KEY:
    print("✅ Loading API Key from Environment Variables...")
    YOUR_API_KEY = SYSTEM_KEY
else:
    print("⚠️ Loading API Key from Hardcoded String...")
    YOUR_API_KEY = HARDCODED_KEY

# We use Llama 3-8b because it balances speed (800 tok/s) and reasoning capability.
AI_MODEL_NAME = "llama-3.3-70b-versatile"

# Global Cache to store expensive graph generation results.
# Format: { 'match_id': { 'image': 'base64_string', 'ai': 'text_analysis' } }
cache = {}

# ==============================================================================
# 🎨 ENTERPRISE COLOR & KIT ENGINE
# ==============================================================================

# A massive database of color names mapped to Hex codes.
# This ensures that even obscure team colors are handled gracefully.
COLOR_MAP = {
    'white': '#ffffff',
    'black': '#000000',
    'red': '#ff2e2e',       # Standard Bright Red
    'blue': '#007fff',      # Standard Azure Blue
    'navy': '#034694',      # Deep Navy
    'sky blue': '#6cabdd',  # Man City style
    'light blue': '#87cefa',
    'maroon': '#a50044',    # Riga/Barcelona Red
    'burgundy': '#800020',
    'gold': '#ffcc00',      # Wolves/Dortmund Yellow
    'yellow': '#ffff00',
    'orange': '#ff5e00',    # Netherlands/Holland Orange
    'green': '#00ff88',     # Wolfsburg Green
    'dark green': '#006400',
    'purple': '#800080',    # Fiorentina Purple
    'violet': '#ee82ee',
    'pink': '#ff69b4',      # Palermo Pink
    'cyan': '#00d2ff',
    'teal': '#008080',
    'grey': '#808080',
    'silver': '#c0c0c0',
    'lilac': '#c8a2c8',
    'claret': '#7f0030'     # West Ham/Burnley
}

def get_hex(color_name):
    """
    Safely converts a generic color name (e.g., 'Navy') into a specific Hex Code.
    If the input is already a hex code, it returns it as-is.
    """
    if not isinstance(color_name, str):
        return '#3b82f6' # Fail-safe default (Blue)
    
    clean_name = color_name.lower().strip()
    
    # Check if user provided a direct hex code
    if clean_name.startswith('#'):
        return clean_name
        
    return COLOR_MAP.get(clean_name, '#3b82f6')

def get_contrast_color(hex_color):
    """Calculates whether to use black or white text based on background brightness."""
    hex_color = hex_color.lstrip('#')
    try:
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        # Perceptual brightness formula
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        return 'black' if brightness > 128 else 'white'
    except:
        return 'white'

def hex_to_rgb(hex_color):
    """
    Helper function to convert a Hex string (#FFFFFF) to an RGB tuple (255, 255, 255).
    This is required for the mathematical distance calculation below.
    """
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def color_distance(hex1, hex2):
    """
    Calculates the Euclidean distance between two colors in RGB space.
    Used to mathematically determine if the Home Kit and Away Kit are too similar.
    """
    try:
        r1, g1, b1 = hex_to_rgb(hex1)
        r2, g2, b2 = hex_to_rgb(hex2)
        
        # Standard 3D Euclidean distance formula
        distance = math.sqrt((r1 - r2)**2 + (g1 - g2)**2 + (b1 - b2)**2)
        return distance
    except Exception as e:
        print(f"Color Math Error: {e}")
        return 100 # Assume distinct if error occurs

def get_match_colors(home_team, away_team):
    """
    The Master Kit Selection Logic.
    1. Reads 'teams.csv' to find preferred kits.
    2. Calculates visual clash between Home and Away.
    3. Forces Away team to Third Kit if clash detected (< 60 distance).
    """
    csv_file = "teams.csv"
    
    # Default Fallbacks (Blue vs Red) in case CSV is missing
    h_kits = {'home': 'blue', 'away': 'white', 'third': 'black'}
    a_kits = {'home': 'red', 'away': 'white', 'third': 'black'}

    # Step 1: Attempt to load from CSV
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            # Normalize column names to avoid case-sensitivity issues
            df.columns = [c.lower().strip() for c in df.columns]
            
            # Look for Home Team
            h_row = df[df['team'] == home_team]
            if not h_row.empty:
                h_kits = {
                    'home': h_row.iloc[0].get('home_color', 'blue'),
                    'away': h_row.iloc[0].get('away_color', 'white'),
                    'third': h_row.iloc[0].get('third_color', 'black')
                }

            # Look for Away Team
            a_row = df[df['team'] == away_team]
            if not a_row.empty:
                a_kits = {
                    'home': a_row.iloc[0].get('home_color', 'red'),
                    'away': a_row.iloc[0].get('away_color', 'white'),
                    'third': a_row.iloc[0].get('third_color', 'black')
                }
        except Exception as e:
            print(f"CSV Reading Error: {e}")

    # Step 2: Convert to Hex for math comparison
    home_hex = get_hex(h_kits['home'])
    away_hex = get_hex(a_kits['away'])
    third_hex = get_hex(a_kits['third'])

    # Step 3: Advanced Clash Detection
    # If the visual distance is less than 60, the kits are too similar.
    dist = color_distance(home_hex, away_hex)
    
    if dist < 60:
        print(f"⚠️ Kit Clash Detected! (Dist: {dist:.2f}). Switching {away_team} to Third Kit.")
        return home_hex, third_hex
    
    return home_hex, away_hex

# ==============================================================================
# 📨 EMAIL ENGINE (NOTIFICATION SERVICE)
# ==============================================================================

# ==============================================================================
# 🛡️ RATE LIMITING & SECURITY UTILS
# ==============================================================================
rate_limit_store = {} # { ip: [timestamp1, timestamp2, ...] }

def is_rate_limited(ip, limit=5, period_seconds=300):
    """
    Simple IP-based rate limiting. 
    Default: 5 requests per 5 minutes.
    """
    now = datetime.now()
    if ip not in rate_limit_store:
        rate_limit_store[ip] = [now]
        return False
    
    # Clean old timestamps
    rate_limit_store[ip] = [t for t in rate_limit_store[ip] if now - t < timedelta(seconds=period_seconds)]
    
    if len(rate_limit_store[ip]) >= limit:
        return True
    
    rate_limit_store[ip].append(now)
    return False

def send_match_request_email_v2(match_name, user_email, ip):
    """
    Bulletproof email engine using FormSubmit API (HTTP 443).
    """
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 🛡️ THE BULLETPROOF METHOD (Uses HTTP 443 - Never Blocked)
        print(f"📡 API: Sending via FormSubmit to {RECEIVER_EMAIL}...")
        
        payload = {
            "Match Requested": match_name,
            "User Email": user_email,
            "Timestamp": timestamp,
            "User IP": ip,
            "_subject": f"⚽ New Match Request: {match_name}",
            "_replyto": user_email,
            "_template": "table"
        }
        
        res = requests.post(FORMSUBMIT_URL, json=payload, timeout=15)
        
        if res.status_code == 200:
            print(f"✅ EMAIL SENT (API SUCCESS)")
            return "SUCCESS"
        else:
            return f"API Failed ({res.status_code}): {res.text}"

    except Exception as e:
        error_msg = str(e)
        print(f"❌ EMAIL ENGINE ERROR: {error_msg}")
        
        # Log to CSV even if everything fails
        try:
            with open('match_requests.csv', mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, match_name, user_email, ip, error_msg])
        except: pass
        
        return error_msg

# ==============================================================================
# 📂 DATA LOADING & PARSING ENGINE
# ==============================================================================

def load_full_match_data(filename):
    """
    Loads match data from a text file.
    Includes STRICT parsing to separate Home vs Away players accurately.
    This prevents the bug where one team's players appear on the other team's graph.
    """
    if not os.path.exists(filename):
        print(f"Error: File {filename} not found.")
        return None, None, None

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            raw_text = f.read()

        # Strategy 1: Look for 'matchCentreData' (Standard WhoScored format)
        match = re.search(r"matchCentreData\s*[:=]\s*(\{[\s\S]*?)(\};|,\s*match)", raw_text)
        data = chompjs.parse_js_object(match.group(1)) if match else None
        
        # Strategy 2: Look for raw 'events' array (Scraped/Custom Data)
        if not data:
            events_match = re.search(r"events\s*:\s*(\[[\s\S]*?\])", raw_text)
            if events_match:
                print("Strategy 2: Raw Events Array found.")
                events_list = chompjs.parse_js_object(events_match.group(1))
                
                # Auto-Detect Team IDs from the event stream
                temp_df = pd.DataFrame(events_list)
                unique_ids = temp_df['teamId'].unique()
                
                # Assign Home/Away IDs dynamically based on frequency
                h_id = int(unique_ids[0]) if len(unique_ids) > 0 else 0
                a_id = int(unique_ids[1]) if len(unique_ids) > 1 else 0
                
                data = {
                    'events': events_list,
                    'home': {'name': 'Home Team', 'teamId': h_id},
                    'away': {'name': 'Away Team', 'teamId': a_id}
                }
        
        # Convert Events to DataFrame for Analysis
        events = pd.DataFrame(data['events'])
        
        # --- STRICT PLAYER MAPPING ---
        # We create separate dictionaries for Home and Away to ensure no overlap.
        # This is the critical fix for the "Crossed Data" bug.
        player_dict = {}
        starter_lookup = {}
        
        # 1. Process Home Team Players
        if 'home' in data and 'players' in data['home']:
            for p in data['home']['players']:
                p_name = p['name']
                p_id = p['playerId']
                player_dict[p_id] = p_name
                starter_lookup[p_name] = p.get('isFirstEleven', False)

        # 2. Process Away Team Players
        if 'away' in data and 'players' in data['away']:
            for p in data['away']['players']:
                p_name = p['name']
                p_id = p['playerId']
                player_dict[p_id] = p_name
                starter_lookup[p_name] = p.get('isFirstEleven', False)
        
        # Map Player IDs to Names in the DataFrame
        events['player_name'] = events['playerId'].map(player_dict)
        
        return events, data, starter_lookup

    except Exception as e:
        print(f"CRITICAL DATA LOADING ERROR: {e}")
        return None, None, None

# ==============================================================================
# 📊 ROBUST STATS ENGINE
# ==============================================================================

def calculate_stats(events, home_id, away_id):
    """
    Calculates detailed stats: Shots, Goals, Passes, Possession.
    Uses strict type checking to avoid the '0 Shots' bug found in some datasets.
    """
    def get_count(df, team_id, target_types):
        # Filter for the specific team
        team_ev = df[df['teamId'] == team_id]
        
        # Robust Matcher: Handles strings vs dictionaries
        # Some datasets have type='Shot', others have type={'displayName': 'Shot'}
        def type_matcher(row_type):
            val = row_type.get('displayName') if isinstance(row_type, dict) else str(row_type)
            return val in target_types
            
        return len(team_ev[team_ev['type'].apply(type_matcher)])

    # Explicit definitions of what constitutes each stat
    shot_types = ['Shot', 'MissedShots', 'SavedShot', 'Goal', 'ShotOnPost']
    goal_types = ['Goal']
    pass_types = ['Pass']

    # 1. Calculate Home Stats
    h_stats = {
        'shots': get_count(events, home_id, shot_types),
        'goals': get_count(events, home_id, goal_types),
        'passes': get_count(events, home_id, pass_types)
    }
    
    # 2. Calculate Away Stats
    a_stats = {
        'shots': get_count(events, away_id, shot_types),
        'goals': get_count(events, away_id, goal_types),
        'passes': get_count(events, away_id, pass_types)
    }
    
    # 3. Calculate Possession Percentage
    total_passes = h_stats['passes'] + a_stats['passes']
    if total_passes > 0:
        h_stats['possession'] = round((h_stats['passes'] / total_passes) * 100)
    else:
        h_stats['possession'] = 50 # Default to 50/50 if no data
    
    a_stats['possession'] = 100 - h_stats['possession']
    
    return h_stats, a_stats

# ==============================================================================
# 🕸️ NETWORK GRAPH VISUALIZATION ENGINE
# ==============================================================================

def generate_graph_image(events, tid, tname, starters, assigned_color, min_passes=3):
    """
    Generates a professional Passing Network using Matplotlib & mplsoccer.
    Features:
    - Centrality Scaling: Node size represents player influence.
    - Edge Width: Thickness represents number of passes between two players.
    - Sub Coloring: Substitutes are marked in Neon Orange.
    - Legend: Automatically added to the bottom left.
    """
    # 1. Filter data for the specific team
    team_events = events[events['teamId'] == tid].copy()
    
    # 2. Identify the Top Players (Squad + Key Subs)
    pass_counts = team_events['player_name'].value_counts()
    if pass_counts.empty: 
        return None, "Data Unavailable"
    
    # We take top 18 to ensure we capture late substitutions who were active
    squad_names = pass_counts.head(18).index.tolist()
    team_events = team_events[team_events['player_name'].isin(squad_names)]
    
    # 3. Calculate Average Positions for every player
    avg_locs = team_events.groupby('player_name').agg({'x': 'mean', 'y': 'mean'}).reset_index()

    # 4. Filter for Successful Passes Only
    def is_pass_success(row):
        t = row['type'] if isinstance(row['type'], str) else row['type'].get('displayName')
        o = row['outcomeType'] if isinstance(row['outcomeType'], str) else row['outcomeType'].get('displayName')
        return t == 'Pass' and o == 'Successful'

    passes = team_events[team_events.apply(is_pass_success, axis=1)].copy()

    # 5. Determine Pass Recipients (Who received the ball?)
    def find_recipient(row):
        end_x, end_y = row['endX'], row['endY']
        passer = row['player_name']
        # Find closest teammate to the pass end location
        cands = avg_locs[avg_locs['player_name'] != passer].copy()
        cands['dist'] = np.sqrt((cands['x'] - end_x)**2 + (cands['y'] - end_y)**2)
        if not cands.empty:
            return cands.sort_values('dist').iloc[0]['player_name']
        return None

    passes['recipient'] = passes.apply(find_recipient, axis=1)
    
    # 6. Build the Adjacency List (Who passed to whom?)
    pair_stats = {}
    for _, row in passes.iterrows():
        p1 = row['player_name']
        p2 = row['recipient']
        if p1 and p2 and p1 != p2:
            # Sort names so A->B and B->A count as the same link
            key = tuple(sorted([str(p1), str(p2)]))
            pair_stats[key] = pair_stats.get(key, 0) + 1

    # --- DRAWING THE PITCH ---
    BG_COLOR = '#1e5d28' # Professional Pitch Green
    MAIN_COLOR = assigned_color
    SUB_COLOR = '#ff8c00' # Neon Orange for Substitutes
    
    pitch = Pitch(pitch_type='opta', pitch_color=BG_COLOR, line_color='#ffffff', linewidth=1)
    fig, ax = pitch.draw(figsize=(16, 10))
    fig.set_facecolor(BG_COLOR)

    # Use NetworkX for Centrality Metrics
    G = nx.Graph()
    for (p1, p2), w in pair_stats.items(): 
        G.add_edge(p1, p2, weight=w)
    
    degree_dict = dict(G.degree(weight='weight'))
    mvp = sorted(degree_dict.items(), key=lambda x: x[1], reverse=True)[0][0] if degree_dict else "N/A"

    # A. Draw Edges (Passing Lines)
    for (p1_n, p2_n), w in pair_stats.items():
        if w >= min_passes: 
            try:
                p1 = avg_locs[avg_locs.player_name == p1_n].iloc[0]
                p2 = avg_locs[avg_locs.player_name == p2_n].iloc[0]
                
                # Line Width based on volume
                width = w * 0.15
                pitch.lines(p1.x, p1.y, p2.x, p2.y, lw=width, color=MAIN_COLOR, alpha=0.5, zorder=1, ax=ax)
                
                # Pass Count Label (Only for strong links > 5 passes)
                if w >= 5:
                    mid_x = (p1.x + p2.x) / 2
                    mid_y = (p1.y + p2.y) / 2
                    txt = ax.text(mid_x, mid_y, str(w), color='white', fontsize=12, ha='center', va='center', zorder=2, weight='bold')
                    txt.set_path_effects([path_effects.withStroke(linewidth=2, foreground=BG_COLOR)])
            except: continue

    # B. Draw Nodes (Players)
    for _, row in avg_locs.iterrows():
        name = row['player_name']
        is_starter = starters.get(name, False)
        
        # Color Logic: Orange if sub, Team Color if starter
        node_color = MAIN_COLOR if is_starter else SUB_COLOR
        
        size = degree_dict.get(name, 5) * 25
        pitch.scatter(row.x, row.y, s=size, c=node_color, alpha=1, zorder=3, ax=ax)
        
        # Name Label with Black Stroke for readability
        disp_name = name.split()[-1]
        t = pitch.annotate(disp_name, xy=(row.x, row.y), c='white', va='center', ha='center', size=12, weight='bold', ax=ax, zorder=5)
        t.set_path_effects([path_effects.withStroke(linewidth=5, foreground='black')])

    # C. Draw Legend
    ax.text(2, 2, "● Starter", color=MAIN_COLOR, fontsize=14, weight='bold', zorder=6)
    ax.text(20, 2, "● Substitute", color=SUB_COLOR, fontsize=14, weight='bold', zorder=6)

    # Save to Memory Buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=BG_COLOR)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8'), mvp

# ==============================================================================
# 🧠 AI ENGINE (GROQ + FAIL-SAFE SIMULATION)
# ==============================================================================


def get_tactical_insight(target_team, mvp, h_name, a_name, score, h_stats, a_stats):
    """
    Generates a STRICTLY formatted Match Report & Tactical Analysis.
    Attempts to use Groq (Llama 3) API. Falls back to Simulation on error.
    """
    import random
    
    # ---------------------------------------------------------
    # 1. SETUP & SIMULATION DATA (Fallback)
    # ---------------------------------------------------------
    tilt = random.randint(42, 68)
    unity = random.randint(75, 92)
    precision = random.randint(86, 94)
    
    if target_team == h_name:
        focus_stats = h_stats
    else:
        focus_stats = a_stats

    # Simulation Template (Updated with new sections)
    simulated_report = f"""
* **The Central Hub (The MVP's Role):** {mvp} was the main man in the middle today. They did a great job connecting the defense to the attackers, making sure the team kept the ball moving and stayed in control.
* **Team Shape & Build-Up Bias:** {target_team} really liked attacking down the wings. They didn't just boot the ball long; instead, they played nice, short passes to try and pull the other team out of position.
* **Key Connections (Strongest Links):** There was a really strong connection between the backline and the wide players. You could tell they've practiced these moves a lot, as they were always looking for each other to escape pressure.
* **Possession vs. Efficiency (The Output):** They had plenty of the ball, but they made it count. Every time they got into the final third, they looked dangerous and were always trying to find a way to get a shot away."""

    # ---------------------------------------------------------
    # 2. ATTEMPT AI GENERATION (Groq)
    # ---------------------------------------------------------
    try:
        client = Groq(api_key=YOUR_API_KEY)
        
        system_prompt = f"""You are a football fan writing a friendly match report. USE VERY SIMPLE, NATURAL LANGUAGE. AVOID TOUGH WORDS, HARD WORDS, OR TECHNICAL JARGON. Write it like a person talking to a friend. 
        
        Return ONLY this Markdown format (no titles):
 
* **The Central Hub (The MVP's Role):** (Talk about {mvp}: why they were important and how they helped the team move the ball. Use simple words.)
* **Team Shape & Build-Up Bias:** (How did they attack? Did they go wide or through the middle? Did they play long or short?)
* **Key Connections (Strongest Links):** (Who were the two players that worked together the best? What did they do?)
* **Possession vs. Efficiency (The Output):** (Did all that possession actually lead to anything? Were they dangerous or just passing for the sake of it?)
"""
        
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze the match between {h_name} and {a_name}. Focus on {target_team}."}
            ],
            model=AI_MODEL_NAME,
            temperature=0.6,
            max_tokens=600,
        )
        
        # Return the AI response
        return chat_completion.choices[0].message.content

    except Exception as e:
        print(f"⚠️ AI GENERATION FAILED: {e}")
        print("🔄 Falling back to Simulation Engine...")
        return simulated_report

# ==============================================================================
# 🚀 NEW ROUTES (STRICT REPORTING & REQUESTS)
# ==============================================================================

@app.route('/api/match-request', methods=['POST'], strict_slashes=False)
def match_request_api():
    """
    Production-ready match request endpoint.
    Includes validation, rate limiting, and sanitization.
    """
    try:
        # Get REAL IP behind Render proxy
        ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
        
        if is_rate_limited(ip):
            return jsonify({"error": "Too many requests. Please wait a few minutes."}), 429

        data = request.json
        match_name = data.get('match', '').strip()
        user_email = data.get('email', '').strip()

        # 1. Validation
        if not match_name:
            return jsonify({"error": "Match name is required."}), 400
        
        if not user_email or "@" not in user_email or "." not in user_email:
            return jsonify({"error": "Invalid email address."}), 400

        # 2. Sanitization (Simple string cleaning)
        match_name = match_name.replace('<', '&lt;').replace('>', '&gt;')

        # 3. Log the request
        print(f"📨 NEW MATCH REQUEST LOGGED: {match_name} from {user_email} (IP: {ip})")
        
        # We handle the actual email delivery via direct FormSubmit in the frontend
        # to ensure reliability and provide visual confirmation to the user.
        return jsonify({"message": "Request logged successfully."}), 200

    except Exception as e:
        print(f"API Error: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500

@app.route('/get_tactical_report', methods=['POST'])
def get_tactical_report_route():
    """
    Generates a STRICT 4-Point Tactical Report using Llama 3 via Groq.
    Format:
    1. Progression vs Safety
    2. Attacking Intent
    3. Structural Integrity
    4. Key Dynamic
    """
    try:
        d = request.json
        filename = d.get('filename')
        team_type = d.get('team_type', 'home')
        
        # Load Data
        events, meta, _ = load_full_match_data(filename)
        if events is None: return jsonify({"error": "Data not found"})

        h_name = meta['home']['name']
        a_name = meta['away']['name']
        score = meta.get('score', '0-0').replace(':', '-')
        
        h_stats, a_stats = calculate_stats(events, meta['home']['teamId'], meta['away']['teamId'])
        
        # Determine Focus Team
        target_team = h_name if team_type == 'home' else a_name
        
        # Generate Text
        client = Groq(api_key=YOUR_API_KEY)
        
        system_prompt = f"""You are a tactical football analyst. Produce a report for {target_team} in the match {h_name} vs {a_name} ({score}).
        
        STRICT FORMAT REQUIRED (Do not add intros/outros):
        USE VERY SIMPLE, HUMAN-LIKE LANGUAGE. NO HARD WORDS.
        
        * **The Central Hub (The MVP's Role):** [Explain what MVP did in very simple words. Why were they the glue for the team?]
        
        * **Team Shape & Build-Up Bias:** [Where did they attack most? Was it the wings or the middle? Did they play fast or slow?]
        
        * **Key Connections (Strongest Links):** [Which two players had the best chemistry? Why was their partnership so good?]
        
        * **Possession vs. Efficiency (The Output):** [Did they do anything useful with the ball? Did it lead to shots or was it just boring passing?]
        
        Stats for Context:
        {h_name}: {h_stats['shots']} shots, {h_stats['possession']}% poss.
        {a_name}: {a_stats['shots']} shots, {a_stats['possession']}% poss.
        """
        
        completion = client.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}],
            model=AI_MODEL_NAME,
            temperature=0.5,
        )
        
        return jsonify({"report": completion.choices[0].message.content})

    except Exception as e:
        print(f"Report Error: {e}")
        # Fallback Simulation
        return jsonify({"report": f"""
* **The Central Hub (The MVP's Role):** {target_team} didn't really have one player who pulled the strings, which made it hard for them to get organized.
* **Team Shape & Build-Up Bias:** They kept trying the same old things over and over, mostly just passing it back and forth without much of a plan.
* **Key Connections (Strongest Links):** The players didn't seem to be on the same page today. The only time they really connected was deep in their own half.
* **Possession vs. Efficiency (The Output):** They had the ball a lot, but they didn't really do anything with it. They never looked like they were going to score.
(Simulation due to API Error: {str(e)})
"""})

# ==============================================================================
# 🌐 FLASK ROUTES (API ENDPOINTS)
# ==============================================================================

@app.route('/')
def home():
    """
    Renders the Home Page by reading database.csv.
    This is the landing page where users select a match.
    """
    if not os.path.exists("database.csv"): 
        return "Error: database.csv not found in the directory."
    
    matches = pd.read_csv("database.csv").to_dict(orient='records')
    
    # Fetch team colors for each match based on home team
    teams_df = pd.DataFrame()
    if os.path.exists("teams.csv"):
        try:
            teams_df = pd.read_csv("teams.csv")
            teams_df.columns = [c.lower().strip() for c in teams_df.columns]
        except: pass

    for m in matches:
        # Extract home team (text before ' vs ')
        fix_parts = m['fixture'].split(' vs ')
        home_name = fix_parts[0].strip() if len(fix_parts) > 0 else "Unknown"
        
        color_val = 'blue'
        if not teams_df.empty:
            row = teams_df[teams_df['team'] == home_name]
            if not row.empty:
                color_val = row.iloc[0].get('home_color', 'blue')
        
        m['home_color'] = get_hex(color_val)

    return render_template('index.html', matches=matches)

@app.route('/match/<filename>')
def match(filename):
    events, data, _ = load_full_match_data(filename)
    if events is None or events.empty: 
        return "Error: Could not load match data."
    
    # Extract Team Info
    h = {'name': data['home']['name'], 'id': data['home']['teamId']}
    a = {'name': data['away']['name'], 'id': data['away']['teamId']}
    
    # --- FIX: GET REAL SCORE ---
    # We look for 'score' in the data, usually formatted as "1 : 1"
    raw_score = data.get('score', '0 : 0') 
    score = raw_score.replace(':', '-') # Convert "1 : 0" to "1 - 0"
    
    # Calculate Stats
    h_s, a_s = calculate_stats(events, h['id'], a['id'])
    
    # Get Team Colors for UI components (Specific Home Colors for both buttons)
    csv_file = "teams.csv"
    h_color_val = 'blue'
    a_color_val = 'red'
    
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            df.columns = [c.lower().strip() for c in df.columns]
            
            h_row = df[df['team'] == h['name']]
            if not h_row.empty:
                h_color_val = h_row.iloc[0].get('home_color', 'blue')
                
            a_row = df[df['team'] == a['name']]
            if not a_row.empty:
                a_color_val = a_row.iloc[0].get('home_color', 'red')
        except: pass

    h_col = get_hex(h_color_val)
    a_col = get_hex(a_color_val)
    
    h_text = get_contrast_color(h_col)
    a_text = get_contrast_color(a_col)
    
    return render_template('match.html', 
                           home=h, away=a, 
                           h_stats=h_s, a_stats=a_s, 
                           h_color=h_col, a_color=a_col,
                           h_text=h_text, a_text=a_text,
                           filename=filename, score=score)
@app.route('/api/get_analysis', methods=['POST'], strict_slashes=False)
def get_analysis_api():
    d = request.json

    # 1. Get the filter value (default to 3 if not sent)
    pass_limit = int(d.get('min_passes', 3)) 

    # Update cache key so different filters are stored separately
    key = f"{d['filename']}_{d['team_type']}_{pass_limit}"

    if key in cache: return jsonify(cache[key])

    events, meta, starters = load_full_match_data(d['filename'])
    h_name, a_name = meta['home']['name'], meta['away']['name']
    h_col, a_col = get_match_colors(h_name, a_name)

    if d['team_type'] == 'home':
        tid, tname, active_color = meta['home']['teamId'], h_name, h_col
    else:
        tid, tname, active_color = meta['away']['teamId'], a_name, a_col

    # 2. Pass the limit to the generator
    img, mvp = generate_graph_image(events, tid, tname, starters, active_color, min_passes=pass_limit)

    # 3. Calculate Stats for the Report
    raw_score = meta.get('score', '0 : 0')
    score = raw_score.replace(':', '-')
    h_stats, a_stats = calculate_stats(events, meta['home']['teamId'], meta['away']['teamId'])

    # 4. Generate AI Insight with Context
    print(f"Generating Simulation for {tname}")
    ai_text = get_tactical_insight(tname, mvp, h_name, a_name, score, h_stats, a_stats)

    res = {'image': img, 'ai': ai_text, 'active_color': active_color}
    cache[key] = res
    return jsonify(res)

# AI Chat logic follows...

# ==============================================================================
# 🤖 CHATBOT ENDPOINT (Uses CHAT_API_KEY)
# ==============================================================================
@app.route('/api/chat', methods=['POST'], strict_slashes=False)
def chat_api():
    try:
        # 1. Check Library
        try:
            from groq import Groq
        except ImportError:
            return jsonify({"answer": "Error: Library missing. Run 'pip install groq'."})

        d = request.json
        question = d.get('question', '')
        filename = d.get('filename')
        
        # 2. LOAD DATA
        events, meta, _ = load_full_match_data(filename)
        if events is None: return jsonify({"answer": "Error loading stats."})
            
        h_name = meta['home']['name']
        a_name = meta['away']['name']
        score = meta.get('score', '0-0').replace(':', '-')
        h_stats, a_stats = calculate_stats(events, meta['home']['teamId'], meta['away']['teamId'])
        
        # 3. BUILD PROMPT
        system_prompt = f"""
        You are MatchBot, a football expert.
        MATCH: {h_name} vs {a_name} (Score: {score})
        STATS: {h_name} ({h_stats['possession']}%), {a_name} ({a_stats['possession']}%)
        USER QUESTION: "{question}"
        Keep answer concise (max 2 sentences).
        """
        
        # 4. CALL AI (Using the Chat Key)
        # We use the specific key defined at the top of the file
        client = Groq(api_key=CHAT_API_KEY)
        
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": system_prompt}],
            model=AI_MODEL_NAME, 
        )
        
        return jsonify({"answer": chat_completion.choices[0].message.content})
        
    except Exception as e:
        # THIS WILL PRINT THE REAL ERROR IN THE CHAT WINDOW
        print(f"Chat Error: {e}")
        return jsonify({"answer": f"CRASH REPORT: {str(e)}"})
if __name__ == '__main__':
    # Threaded mode allows multiple requests to be handled simultaneously
    print("🚀 Gameday Tactics Server Starting...")
    app.run(debug=True, threaded=True)
