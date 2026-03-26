#!/usr/bin/env python3
"""
infra_sync.py - systemd + cloudflared config + ss からインフラ状態を収集し infra.db に書き込む
================================================================================
cron: 5:50 毎日 (morning_briefing 6:00 の直前)
"""

import re
import sqlite3
import subprocess
import yaml
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "infra.db"
CONFIG_YML = Path("/etc/cloudflared/config.yml")


def init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            port INTEGER,
            caddy_port INTEGER,
            app_name TEXT NOT NULL,
            hostname TEXT,
            directory TEXT,
            framework TEXT,
            systemd_unit TEXT,
            status TEXT DEFAULT 'unknown',
            notes TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()


def get_systemd_services() -> list[dict]:
    """systemd の running サービスからアプリ情報を取得"""
    result = subprocess.run(
        ["systemctl", "list-units", "--type=service", "--state=running", "--no-pager", "--plain"],
        capture_output=True, text=True,
    )
    # アプリ系 unit を抽出（system系は除外）
    skip = {
        "console-getty", "containerd", "cron", "dbus", "docker", "getty@tty1",
        "nginx", "polkit", "rsyslog", "snapd", "ssh", "tailscaled",
        "unattended-upgrades", "user@1000", "wsl-pro",
    }
    units = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if not parts or not parts[0].endswith(".service"):
            continue
        unit = parts[0].removesuffix(".service")
        if unit in skip or unit.startswith("systemd"):
            continue
        units.append(unit)

    services = []
    for unit in units:
        info = subprocess.run(
            ["systemctl", "show", f"{unit}.service",
             "--property=Description,WorkingDirectory,ActiveState,ExecStart"],
            capture_output=True, text=True,
        )
        props = {}
        for line in info.stdout.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                props[k] = v

        desc = props.get("Description", "")
        workdir = props.get("WorkingDirectory", "")
        exec_start = props.get("ExecStart", "")

        # ポート番号: Description → ExecStart の順で探す
        port = None
        m = re.search(r":(\d{4,5})", desc)
        if m:
            port = int(m.group(1))
        if port is None:
            # --port XXXX, --server.port XXXX, --bind/-b x.x.x.x:XXXX
            m = re.search(r"(?:--port|--server\.port)\s+(\d{4,5})", exec_start)
            if m:
                port = int(m.group(1))
            else:
                m = re.search(r"(?:--bind|-b)\s+[\d.:]+:(\d{4,5})", exec_start)
                if m:
                    port = int(m.group(1))

        # framework を Description から推定
        framework = None
        for fw in ("Streamlit", "FastAPI", "Flask", "Gunicorn", "Caddy", "cloudflared"):
            if fw.lower() in desc.lower():
                framework = fw
                break

        services.append({
            "systemd_unit": unit,
            "app_name": unit,
            "description": desc,
            "port": port,
            "directory": workdir.replace(str(Path.home()), "~") if workdir else None,
            "framework": framework,
        })

    return services


def get_tunnel_routes() -> dict[int, str]:
    """config.yml から port → hostname マッピングを取得"""
    if not CONFIG_YML.exists():
        return {}

    with open(CONFIG_YML) as f:
        cfg = yaml.safe_load(f)

    routes = {}
    for rule in cfg.get("ingress", []):
        hostname = rule.get("hostname")
        service = rule.get("service", "")
        m = re.search(r"localhost:(\d+)", service)
        if hostname and m:
            routes[int(m.group(1))] = hostname
    return routes


def get_listening_ports() -> set[int]:
    """ss -tlnp から LISTEN 中のポートを取得"""
    result = subprocess.run(
        ["ss", "-tlnp"],
        capture_output=True, text=True,
    )
    ports = set()
    for line in result.stdout.splitlines():
        # 0.0.0.0:8505 or 127.0.0.1:8507 or [::]:8502
        for m in re.finditer(r":(\d{4,5})\s", line):
            ports.add(int(m.group(1)))
    return ports


def get_caddy_ports() -> dict[int, int]:
    """Caddy の 9xxx → 8xxx マッピングを推定 (9xxx = app_port + 1000)"""
    result = subprocess.run(
        ["ss", "-tlnp"],
        capture_output=True, text=True,
    )
    caddy_ports = set()
    for line in result.stdout.splitlines():
        if "caddy" in line:
            for m in re.finditer(r":(\d{4,5})\s", line):
                caddy_ports.add(int(m.group(1)))

    # 9531 → app_port 8531
    mapping = {}
    for cp in caddy_ports:
        if 9500 <= cp <= 9599:
            mapping[cp - 1000] = cp
    return mapping


def sync():
    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)

    now = datetime.now().isoformat()

    # 全削除して再構築（毎回最新スナップショット）
    conn.execute("DELETE FROM services")

    systemd_svcs = get_systemd_services()
    tunnel_routes = get_tunnel_routes()
    listening = get_listening_ports()
    caddy_map = get_caddy_ports()

    # systemd サービスを登録
    seen_ports = set()
    for svc in systemd_svcs:
        port = svc["port"]

        # ポートが無い systemd サービスは tunnel routes から逆引き
        if port is None:
            for p, h in tunnel_routes.items():
                # app_name が hostname に含まれるか確認
                if svc["app_name"].replace("-", "") in h.replace("-", "").replace(".", ""):
                    port = p
                    break

        hostname = tunnel_routes.get(port)
        # caddy 経由のサービスは caddy_port の hostname を確認
        caddy_port = caddy_map.get(port) if port else None
        if not hostname and caddy_port:
            hostname = tunnel_routes.get(caddy_port)

        # ポートが無いインフラ系(caddy, cloudflared等)は systemd running なら active
        if port:
            status = "active" if port in listening else "stopped"
        else:
            status = "active"

        conn.execute(
            """INSERT INTO services
               (port, caddy_port, app_name, hostname, directory, framework, systemd_unit, status, notes, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (port, caddy_port, svc["app_name"], hostname, svc["directory"],
             svc["framework"], svc["systemd_unit"], status, svc["description"], now),
        )
        if port:
            seen_ports.add(port)

    # tunnel routes にあるが systemd に無い = 手動起動 or 停止中
    for port, hostname in tunnel_routes.items():
        if port in seen_ports:
            continue
        # caddy 経由ポートはスキップ (実体は別ポート)
        if port in caddy_map.values():
            continue

        status = "active" if port in listening else "stopped"
        app_name = hostname.split(".")[0] if hostname else f"port-{port}"

        conn.execute(
            """INSERT INTO services
               (port, caddy_port, app_name, hostname, directory, framework, systemd_unit, status, notes, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (port, caddy_map.get(port), app_name, hostname, None, None, None,
             status, "config.yml記載・systemd未登録", now),
        )

    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM services").fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM services WHERE status='active'").fetchone()[0]
    stopped = conn.execute("SELECT COUNT(*) FROM services WHERE status='stopped'").fetchone()[0]
    conn.close()

    print(f"[infra_sync] {now}: {count} services ({active} active, {stopped} stopped) → {DB_PATH}")


if __name__ == "__main__":
    sync()
