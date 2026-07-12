#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# WARNOX_CHAT_PUBLIC.py - Chat public accessible depuis Internet
# Pour iSH / Alpine / tout serveur Linux
# Permet à n'importe qui en France (ou ailleurs) de se connecter

import socket
import threading
import json
import os
import sys
import time

# ========== COULEURS ==========
R = '\033[91m'
G = '\033[92m'
Y = '\033[93m'
C = '\033[96m'
M = '\033[95m'
W = '\033[97m'
B = '\033[1m'
N = '\033[0m'

# ========== CONFIGURATION ==========
# ⚠️ SUR iSH : UTILISEZ L'IP DE VOTRE RÉSEAU LOCAL (192.168.x.x) OU UN TUNNEL
# Pour exposer sur Internet, utilisez ngrok ou serveo (voir plus bas)
HOST = '0.0.0.0'  # Écoute sur toutes les interfaces (local + réseau)
PORT = int(os.getenv("PORT", 5000))
DATA_FILE = "warnox_data.json"
BUFFER = 4096

# ========== DONNÉES PARTAGÉES ==========
users = {}
groups = {}
pending_requests = {}
server_running = True

# ========== SERVEUR ==========
def load_data():
    global users, groups
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                users = data.get("users", {})
                groups = data.get("groups", {})
                for u in users:
                    users[u]["online"] = False
                    users[u]["conn"] = None
        except:
            users = {}
            groups = {}

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump({"users": users, "groups": groups}, f, indent=4)

def notify_user(username, message):
    if username in users and users[username]["conn"]:
        try:
            users[username]["conn"].send(f"NOTIF:{message}".encode())
        except:
            pass

def send_private(sender, target, message):
    if target in users and users[target]["conn"]:
        try:
            users[target]["conn"].send(f"MSG:{sender}:{message}".encode())
            return True
        except:
            pass
    return False

def broadcast_group(group_name, sender, message):
    if group_name not in groups:
        return
    for member in groups[group_name]["members"]:
        if member != sender and member in users and users[member]["conn"]:
            try:
                users[member]["conn"].send(f"GRP:{group_name}:{sender}:{message}".encode())
            except:
                pass

def process_cmd(username, raw):
    try:
        cmd = json.loads(raw)
        action = cmd.get("action")

        if action == "add_friend":
            target = cmd.get("target")
            if target not in users:
                send_private(username, username, "Utilisateur introuvable.")
                return
            if target == username:
                send_private(username, username, "Impossible de s'ajouter soi-même.")
                return
            if target in users[username]["friends"]:
                send_private(username, username, "Déjà ami.")
                return
            if target not in pending_requests:
                pending_requests[target] = []
            pending_requests[target].append({"from": username})
            notify_user(target, f"DEMANDE_AMI:{username}")
            send_private(username, username, f"Demande envoyée à {target}.")

        elif action == "accept_friend":
            sender = cmd.get("from")
            if username not in pending_requests:
                return
            for req in pending_requests[username]:
                if req["from"] == sender:
                    pending_requests[username].remove(req)
                    users[username]["friends"].append(sender)
                    users[sender]["friends"].append(username)
                    save_data()
                    notify_user(sender, f"ACCEPTED:{username}")
                    send_private(username, username, f"Demande de {sender} acceptée.")
                    break

        elif action == "decline_friend":
            sender = cmd.get("from")
            if username not in pending_requests:
                return
            for req in pending_requests[username]:
                if req["from"] == sender:
                    pending_requests[username].remove(req)
                    send_private(username, username, f"Demande de {sender} refusée.")
                    break

        elif action == "send_private":
            target = cmd.get("target")
            message = cmd.get("message")
            if target not in users:
                send_private(username, username, "Utilisateur introuvable.")
                return
            if target not in users[username]["friends"]:
                send_private(username, username, "Vous n'êtes pas amis.")
                return
            if send_private(username, target, message):
                send_private(username, username, f"[Vous -> {target}] {message}")
            else:
                send_private(username, username, f"{target} est hors ligne.")

        elif action == "send_group":
            group = cmd.get("group")
            message = cmd.get("message")
            if group not in groups:
                send_private(username, username, "Groupe introuvable.")
                return
            if username not in groups[group]["members"]:
                send_private(username, username, "Vous n'êtes pas membre.")
                return
            broadcast_group(group, username, message)
            send_private(username, username, f"[Groupe {group}] {message}")

        elif action == "create_group":
            group_name = cmd.get("name")
            if group_name in groups:
                send_private(username, username, "Ce nom existe déjà.")
                return
            groups[group_name] = {"members": [username], "admins": [username], "messages": []}
            users[username]["groups"].append(group_name)
            save_data()
            send_private(username, username, f"Groupe {group_name} créé !")

        elif action == "add_to_group":
            group = cmd.get("group")
            target = cmd.get("target")
            if group not in groups:
                send_private(username, username, "Groupe introuvable.")
                return
            if username not in groups[group]["admins"]:
                send_private(username, username, "Seul l'admin peut ajouter.")
                return
            if target not in users:
                send_private(username, username, "Utilisateur introuvable.")
                return
            if target in groups[group]["members"]:
                send_private(username, username, "Déjà membre.")
                return
            groups[group]["members"].append(target)
            users[target]["groups"].append(group)
            save_data()
            notify_user(target, f"ADDED_TO_GROUP:{group}")
            send_private(username, username, f"{target} ajouté à {group}.")

        elif action == "list_friends":
            friends = users[username]["friends"]
            if not friends:
                send_private(username, username, "Aucun ami.")
            else:
                status = [f"{f} ({'🟢' if f in users and users[f]['online'] else '🔴'})" for f in friends]
                send_private(username, username, "Amis : " + ", ".join(status))

        elif action == "list_groups":
            grps = users[username]["groups"]
            if not grps:
                send_private(username, username, "Aucun groupe.")
            else:
                send_private(username, username, "Groupes : " + ", ".join(grps))

        elif action == "list_pending":
            if username not in pending_requests or not pending_requests[username]:
                send_private(username, username, "Aucune demande.")
            else:
                reqs = [r["from"] for r in pending_requests[username]]
                send_private(username, username, "Demandes : " + ", ".join(reqs))

    except Exception as e:
        send_private(username, username, f"Erreur: {e}")

def handle_client(conn, addr):
    username = None
    try:
        data = conn.recv(BUFFER).decode()
        if not data:
            conn.close()
            return
        auth = json.loads(data)
        action = auth.get("action")
        user = auth.get("username")
        pwd = auth.get("password")

        if action == "register":
            if user in users:
                conn.send(json.dumps({"status": "error", "msg": "Nom déjà pris"}).encode())
                conn.close()
                return
            users[user] = {"password": pwd, "friends": [], "groups": [], "pending": [], "online": False, "conn": None}
            save_data()
            conn.send(json.dumps({"status": "ok", "msg": "Compte créé !"}).encode())
            username = user
            users[username]["conn"] = conn
            users[username]["online"] = True
            print(f"[+] {username} connecté depuis {addr}")
            while True:
                msg = conn.recv(BUFFER).decode()
                if not msg:
                    break
                process_cmd(username, msg)

        elif action == "login":
            if user not in users or users[user]["password"] != pwd:
                conn.send(json.dumps({"status": "error", "msg": "Identifiants incorrects"}).encode())
                conn.close()
                return
            conn.send(json.dumps({"status": "ok", "msg": "Connecté !"}).encode())
            username = user
            users[username]["conn"] = conn
            users[username]["online"] = True
            print(f"[+] {username} connecté depuis {addr}")

            online_friends = [f for f in users[username]["friends"] if f in users and users[f]["online"]]
            if online_friends:
                conn.send(f"ONLINE:{','.join(online_friends)}".encode())

            if username in pending_requests and pending_requests[username]:
                for req in pending_requests[username]:
                    conn.send(f"REQ:{req['from']}".encode())

            while True:
                msg = conn.recv(BUFFER).decode()
                if not msg:
                    break
                process_cmd(username, msg)

    except:
        pass
    finally:
        if username and username in users:
            users[username]["online"] = False
            users[username]["conn"] = None
        conn.close()

def start_server():
    load_data()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f"{G}[+] Serveur démarré sur {HOST}:{PORT}{N}")
    print(f"{Y}[!] En attente de connexions...{N}")
    print(f"{C}[!] Pour que d'autres personnes se connectent :{N}")
    print(f"{M}    - Sur le même réseau local : utilisez l'IP locale (ex: 192.168.1.10){N}")
    print(f"{M}    - Depuis Internet : utilisez ngrok ou serveo (voir ci-dessous){N}")
    while server_running:
        try:
            conn, addr = server.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
        except:
            break

if __name__ == "__main__":
    start_server()
