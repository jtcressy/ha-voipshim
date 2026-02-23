# ha-voipshim

A minimal SIP bridge that lets SIP handsets call Home Assistant's VOIP integration. Built for Unifi Talk, but probably easy to make work with other SIP servers (codecs might not work well). _This is not an addon or component for HA, it is a standalone Docker container that connects to HA's built-in VOIP integration._

**Pick up a UniFi Talk handset, dial the "Home Assistant" contact, Assist answers.**

This was built using Claude Code (Opus 4.6), with a fairly detailed prompt. It's such a weird project, I can't imagine anyone else building it. In any case, use at your own risk! Okay, now here comes the extremely AI-looking readme...

## How It Works

The shim is a tiny **SIP Back-to-Back User Agent (B2BUA)** built on PJSIP. It registers with UniFi Talk as a standard SIP extension, then bridges every incoming call to Home Assistant.

```
UniFi Talk server              voipshim                 Home Assistant
 (SIP registrar)             (SIP B2BUA)              (VOIP integration)
       │                          │                          │
       │◄── SIP REGISTER ─────────│                          │
       │    (ext. 200)            │                          │
       │                          │                          │
 user dials ext 200               │                          │
       │                          │                          │
       │──── SIP INVITE ─────────►│                          │
       │                          │───── SIP INVITE ────────►│
       │◄─── 180 Ringing ─────────│                          │
       │                          │◄──── 200 OK ─────────────│
       │◄─── 200 OK ──────────────│                          │
       │──── ACK ────────────────►│──── ACK ────────────────►│
       │                          │                          │
       │◄════ RTP audio ══════════►│◄═════ RTP audio ═══════►│
       │       (bridged via PJSIP conference bridge)         │
       │                          │                          │
       │──── BYE ────────────────►│──── BYE ────────────────►│
       │                          │                          │
```

Key details:
- **Codec negotiation** is handled by PJSIP automatically. PJSIP and HA negotiate compatible codecs (PCMU, PCMA, or Opus) via SDP. The conference bridge transcodes between legs if needed.
- **Audio bridging** uses PJSIP's built-in conference bridge — no manual RTP forwarding.
- **Registration** is maintained automatically with periodic re-REGISTER messages.

## Prerequisites

- **UniFi Talk server** with admin access (to create a SIP extension)
- **Home Assistant** with the [VOIP integration](https://www.home-assistant.io/integrations/voip) enabled
- **Docker** on a machine on the same LAN as both systems

## Setup

### 1. Create a SIP Extension on UniFi Talk

You need to create an extension that the shim will register as. The exact steps depend on your UniFi Talk version, but generally:

1. Open the UniFi Talk settings (typically at `https://<controller>/talk`).
2. Go to **Extensions** and create a new extension.
3. Choose a **Third-Party** or **Generic SIP Device** type (this allows external SIP clients to register).
4. Assign to aa new person named "Home Assistant" or whatever you'dl like to name the contact. 
5. Note the **extension number** (e.g., `200`) — this is `UNIFI_SIP_USER`.
6. Set a **SIP password** — this is `UNIFI_SIP_PASS`.
7. Save the extension.

### 2. Enable Home Assistant VOIP Integration

1. In Home Assistant, go to **Settings → Devices & Services → Add Integration → Voice over IP**.
2. The integration listens on UDP port **5060** by default.
3. Configure an **Assist pipeline** with STT and TTS engines (so HA can understand speech and respond).

### 3. Deploy the Shim

1. Create a Docker compose file like the below.

```yaml
services:
  voipshim:
    image: ghcr.io/zacs/ha-voipshim:latest
    container_name: voipshim
    restart: unless-stopped
    network_mode: host     # Required — SIP/RTP needs direct network access
    environment:
      # UniFi Talk server address (IP or hostname)
      UNIFI_SIP_SERVER: "192.168.x.y"
      # SIP extension credentials created on UniFi Talk
      UNIFI_SIP_USER: "0001"
      UNIFI_SIP_PASS: "yourPasswordHere"
      # Home Assistant address (IP or hostname)
      HA_HOST: "192.168.z.t"
```

2. Start it up:

```
docker compose up -d && docker compose logs -f
```

3. You should see:

```
voipshim starting
  UniFi Talk : 192.168.1.1:5060  user=200
  Home Asst  : 192.168.1.100:5060
SIP registration: OK  (code 200, active=True)
Registered with UniFi Talk - waiting for calls
```

### 4. Test a Call

1. Pick up a UniFi Talk handset.
2. Dial the "Home Assistant" contact (or the extension number directly).
3. You should hear HA's Assist pipeline respond.

## Configuration

All settings are environment variables in `docker-compose.yml`:

| Variable | Required | Default | Description |
|---|---|---|---|
| `UNIFI_SIP_SERVER` | **Yes** | — | UniFi Talk server IP or hostname |
| `UNIFI_SIP_USER` | **Yes** | — | SIP extension username/number |
| `UNIFI_SIP_PASS` | **Yes** | — | SIP extension password |
| `HA_HOST` | **Yes** | — | Home Assistant IP or hostname |
| `UNIFI_SIP_PORT` | No | `5060` | UniFi Talk SIP port |
| `HA_SIP_PORT` | No | `5060` | Home Assistant VOIP SIP port |
| `LOCAL_SIP_PORT` | No | `5080` | Local SIP port the shim binds to |
| `LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `PJSIP_LOG_LEVEL` | No | `3` | PJSIP internal log level (0–6) |
| `MAX_CALLS` | No | `4` | Maximum concurrent bridged calls |

### Port Conflicts

If the shim runs on the **same host** as Home Assistant, their SIP ports must differ. The shim defaults to port `5080`; HA defaults to `5060`. No change needed in the default configuration.

## Verifying Audio Flow

1. Set `LOG_LEVEL: "DEBUG"` and `PJSIP_LOG_LEVEL: "5"` in docker-compose.yml, then restart.
2. Call from a UniFi Talk handset.
3. Watch the logs:

```bash
docker compose logs -f voipshim
```

You should see:
```
Incoming call from sip:...
Dialling Home Assistant at sip:ha@192.168.1.100:5060
HA   leg: CONFIRMED  (code 200)
HA answered -> answering UniFi side
Audio bridged: UniFi <-> HA
```

At `PJSIP_LOG_LEVEL: "5"`, you'll also see raw SIP messages and RTP statistics.

## Docker Health Check

The container writes `/tmp/voipshim-healthy` when SIP registration is active. Docker's built-in `HEALTHCHECK` monitors this:

```bash
docker inspect --format='{{.State.Health.Status}}' voipshim
# "healthy" when registered, "unhealthy" otherwise
```

## Architecture Notes

- **Single Python file** (`shim.py`, ~230 lines) built on PJSIP/pjsua2.
- **PJSIP** handles all SIP signaling, codec negotiation, RTP transport, and audio bridging.
- **Opus + G.711** codecs are built-in — PJSIP negotiates the best match with each peer.
- **Null audio device** — no sound hardware needed; the conference bridge operates entirely in software.
- **Host networking** — SIP and RTP require direct network access (no NAT/port-mapping complexity).
- **No config files, no UI, no cloud dependencies.**

## Troubleshooting

| Symptom | Likely Cause |
|---|---|
| `SIP registration: ... (code 401)` | Wrong `UNIFI_SIP_USER` or `UNIFI_SIP_PASS` |
| `SIP registration: ... (code 403)` | Extension not configured for third-party SIP |
| Registration loops / never succeeds | Wrong `UNIFI_SIP_SERVER` or port; check network connectivity |
| `Failed to dial HA` | Wrong `HA_HOST` or `HA_SIP_PORT`; HA VOIP integration not enabled |
| One-way audio | Firewall blocking RTP ports; ensure both peers can reach the shim host |
| No audio at all | Codec mismatch (unlikely with PJSIP); check `PJSIP_LOG_LEVEL: "5"` for SDP details |
| `Audio not ready on both legs yet` | Transient — should resolve in <1 second as media negotiation completes |

## Non-Goals

This project does **not**:

- Replace Home Assistant's VOIP logic
- Perform speech-to-text or intent parsing
- Support PSTN, voicemail, or call routing
- Require cloud services

It is infrastructure glue — nothing more.

## License

MIT
