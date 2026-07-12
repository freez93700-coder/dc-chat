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
PORT = 5000
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

# ========== CLIENT ==========
class WarnoxClient:
    def __init__(self):
        self.sock = None
        self.username = None
        self.running = True
        self.current_chat = None

    def clear(self):
        os.system('clear' if os.name == 'posix' else 'cls')

    def banner(self):
        self.clear()
        print(f"{R}{B}")
        print("    ██╗    ██╗ █████╗ ██████╗ ███╗   ██╗ ██████╗ ██╗  ██╗")
        print("    ██║    ██║██╔══██╗██╔══██╗████╗  ██║██╔═══██╗╚██╗██╔╝")
        print("    ██║ █╗ ██║███████║██████╔╝██╔██╗ ██║██║   ██║ ╚███╔╝ ")
        print("    ██║███╗██║██╔══██║██╔══██╗██║╚██╗██║██║   ██║ ██╔██╗ ")
        print("    ╚███╔███╔╝██║  ██║██║  ██║██║ ╚████║╚██████╔╝██╔╝ ██╗")
        print("     ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝")
        print(f"{N}")
        print(f"{C}{B}          WARNOX CHAT PUBLIC{N}")
        print(f"{Y}═══════════════════════════════════════════════════════════════{N}")

    def connect(self, server_ip="127.0.0.1"):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((server_ip, 5000))
            return True
        except:
            return False

    def send(self, data):
        try:
            self.sock.send(json.dumps(data).encode())
            return True
        except:
            return False

    def receive(self):
        while self.running:
            try:
                data = self.sock.recv(BUFFER).decode()
                if not data:
                    break

                if data.startswith("MSG:"):
                    parts = data[4:].split(":", 1)
                    if len(parts) == 2:
                        sender, msg = parts
                        if self.current_chat == f"user:{sender}":
                            print(f"{C}{sender} :{N} {msg}")
                        else:
                            print(f"{Y}[{sender}] {msg}{N}")

                elif data.startswith("GRP:"):
                    parts = data[4:].split(":", 2)
                    if len(parts) == 3:
                        grp, sender, msg = parts
                        if self.current_chat == f"group:{grp}":
                            print(f"{M}[{grp}] {sender} :{N} {msg}")
                        else:
                            print(f"{Y}[Groupe {grp}] {sender} : {msg}{N}")

                elif data.startswith("ONLINE:"):
                    friends = data[7:].split(",")
                    if friends and friends[0]:
                        print(f"{G}[+] Amis en ligne : {', '.join(friends)}{N}")

                elif data.startswith("REQ:"):
                    sender = data[4:]
                    print(f"{Y}[+] Demande de {sender}{N}")
                    print(f"{C}  /accept {sender}   accepter{N}")
                    print(f"{C}  /decline {sender}  refuser{N}")

                elif data.startswith("ACCEPTED:"):
                    sender = data[9:]
                    print(f"{G}[+] {sender} a accepté !{N}")

                elif data.startswith("ADDED_TO_GROUP:"):
                    grp = data[15:]
                    print(f"{G}[+] Ajouté à {grp}{N}")

                elif data.startswith("NOTIF:"):
                    msg = data[6:]
                    if msg.startswith("DEMANDE_AMI:"):
                        sender = msg[12:]
                        print(f"{Y}[+] Demande de {sender}{N}")
                        print(f"{C}  /accept {sender}   accepter{N}")
                        print(f"{C}  /decline {sender}  refuser{N}")
                else:
                    print(f"{Y}[?] {data}{N}")

            except:
                break
        print(f"{R}[!] Déconnecté.{N}")

    def login(self):
        self.banner()
        # Demander l'IP du serveur (pour les connexions distantes)
        print(f"{C}Adresse du serveur :{N}")
        print(f"  {Y}[ENTER]{N} pour localhost (127.0.0.1)")
        print(f"  {Y}Ou l'IP publique/ngrok{ N}")
        server_ip = input(f"{C}IP > {N}").strip()
        if not server_ip:
            server_ip = "127.0.0.1"

        while True:
            print(f"{G}1. Se connecter{N}")
            print(f"{G}2. Créer un compte{N}")
            print(f"{G}3. Quitter{N}")
            choice = input(f"{C}> {N}").strip()
            if choice == "3":
                sys.exit(0)

            username = input(f"{C}Nom : {N}").strip()
            password = input(f"{C}Mot de passe : {N}").strip()
            if not username or not password:
                print(f"{R}[!] Champs vides.{N}")
                continue

            action = "register" if choice == "2" else "login"
            if not self.connect(server_ip):
                print(f"{R}[!] Serveur injoignable.{N}")
                continue

            self.send({"action": action, "username": username, "password": password})
            try:
                resp = json.loads(self.sock.recv(BUFFER).decode())
                if resp.get("status") == "ok":
                    self.username = username
                    print(f"{G}[+] {resp.get('msg')}{N}")
                    threading.Thread(target=self.receive, daemon=True).start()
                    return True
                else:
                    print(f"{R}[-] {resp.get('msg')}{N}")
                    self.sock.close()
            except:
                print(f"{R}[!] Erreur.{N}")
                self.sock.close()

    def help(self):
        print(f"{C}Commandes :{N}")
        print(f"  {G}/add <pseudo>{N}        → Ajouter un ami")
        print(f"  {G}/accept <pseudo>{N}     → Accepter")
        print(f"  {G}/decline <pseudo>{N}    → Refuser")
        print(f"  {G}/msg <p> <txt>{N}       → Message privé")
        print(f"  {G}/group <nom>{N}         → Créer un groupe")
        print(f"  {G}/addgroup <g> <p>{N}    → Ajouter au groupe")
        print(f"  {G}/send <g> <txt>{N}      → Message groupe")
        print(f"  {G}/friends{N}             → Liste amis")
        print(f"  {G}/groups{N}              → Liste groupes")
        print(f"  {G}/pending{N}             → Demandes")
        print(f"  {G}/chat user <p>{N}       → Chatter")
        print(f"  {G}/chat group <g>{N}      → Chatter groupe")
        print(f"  {G}/clear{N}               → Effacer")
        print(f"  {G}/quit{N}                → Quitter")

    def run(self):
        if not self.login():
            return
        self.banner()
        print(f"{G}[+] Connecté : {self.username}{N}")
        print(f"{Y}Tapez /help{N}\n")

        while self.running:
            try:
                cmd = input(f"{C}{self.username}> {N}").strip()
                if not cmd:
                    continue

                if cmd == "/quit":
                    self.running = False
                    break
                elif cmd == "/clear":
                    self.banner()
                    continue
                elif cmd == "/help":
                    self.help()
                elif cmd == "/friends":
                    self.send({"action": "list_friends"})
                elif cmd == "/groups":
                    self.send({"action": "list_groups"})
                elif cmd == "/pending":
                    self.send({"action": "list_pending"})
                elif cmd.startswith("/add "):
                    t = cmd[5:].strip()
                    if t:
                        self.send({"action": "add_friend", "target": t})
                elif cmd.startswith("/accept "):
                    t = cmd[8:].strip()
                    if t:
                        self.send({"action": "accept_friend", "from": t})
                elif cmd.startswith("/decline "):
                    t = cmd[9:].strip()
                    if t:
                        self.send({"action": "decline_friend", "from": t})
                elif cmd.startswith("/msg "):
                    parts = cmd[5:].split(" ", 1)
                    if len(parts) == 2:
                        self.send({"action": "send_private", "target": parts[0], "message": parts[1]})
                elif cmd.startswith("/group "):
                    n = cmd[7:].strip()
                    if n:
                        self.send({"action": "create_group", "name": n})
                elif cmd.startswith("/addgroup "):
                    parts = cmd[10:].split(" ", 1)
                    if len(parts) == 2:
                        self.send({"action": "add_to_group", "group": parts[0], "target": parts[1]})
                elif cmd.startswith("/send "):
                    parts = cmd[6:].split(" ", 1)
                    if len(parts) == 2:
                        self.send({"action": "send_group", "group": parts[0], "message": parts[1]})
                elif cmd.startswith("/chat user "):
                    t = cmd[11:].strip()
                    if t:
                        self.current_chat = f"user:{t}"
                        print(f"{G}[+] Chat avec {t}{N}")
                elif cmd.startswith("/chat group "):
                    g = cmd[12:].strip()
                    if g:
                        self.current_chat = f"group:{g}"
                        print(f"{G}[+] Chat dans {g}{N}")
                elif cmd == "/quit_chat":
                    self.current_chat = None
                    print(f"{Y}[+] Sortie du chat.{N}")
                else:
                    if self.current_chat:
                        if self.current_chat.startswith("user:"):
                            self.send({"action": "send_private", "target": self.current_chat[5:], "message": cmd})
                        elif self.current_chat.startswith("group:"):
                            self.send({"action": "send_group", "group": self.current_chat[6:], "message": cmd})
                    else:
                        print(f"{R}[!] Commande inconnue. /help{N}")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"{R}[!] {e}{N}")

        self.sock.close()
        print(f"{R}[+] Déconnecté.{N}")

# ========== LANCEMENT ==========
if __name__ == "__main__":
    # Démarrer le serveur dans un thread séparé
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    time.sleep(1)

    # Lancer le client
    client = WarnoxClient()
    client.run()
