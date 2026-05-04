# Home Assistant Add-on: VOIP Shim (UniFi Talk -> Home Assistant)

This add-on runs `ha-voipshim` inside Home Assistant OS and bridges inbound UniFi Talk SIP calls to Home Assistant's Voice over IP integration.

## Install in Home Assistant OS

1. Push this repository to your GitHub fork.
2. In Home Assistant: **Settings -> Add-ons -> Add-on Store -> ⋮ -> Repositories**.
3. Add your fork URL, for example:
   `https://github.com/<your-user>/ha-voipshim`
4. Find **VOIP Shim (UniFi Talk -> Home Assistant)** and click **Install**.
5. Configure options and start the add-on.

HA OS add-on builds currently support `aarch64` and `amd64`.

## Example add-on configuration

```yaml
unifi_sip_server: 192.168.1.10
unifi_sip_user: "200"
unifi_sip_pass: "replace-with-real-password"
ha_host: 127.0.0.1
unifi_sip_port: 5060
ha_sip_port: 5060
local_sip_port: 5080
rtp_port_start: 10000
log_level: INFO
pjsip_log_level: 3
max_calls: 4
debug: false
```

## Option mapping

Add-on options are mapped to the same environment variables used by standalone Docker:

- `unifi_sip_server` -> `UNIFI_SIP_SERVER`
- `unifi_sip_user` -> `UNIFI_SIP_USER`
- `unifi_sip_pass` -> `UNIFI_SIP_PASS`
- `ha_host` -> `HA_HOST`
- `unifi_sip_port` -> `UNIFI_SIP_PORT`
- `ha_sip_port` -> `HA_SIP_PORT`
- `local_sip_port` -> `LOCAL_SIP_PORT`
- `rtp_port_start` -> `RTP_PORT_START`
- `log_level` -> `LOG_LEVEL`
- `pjsip_log_level` -> `PJSIP_LOG_LEVEL`
- `max_calls` -> `MAX_CALLS`

## Networking / SIP port conflicts

- This add-on uses `host_network: true` because SIP/RTP is timing-sensitive and does not behave reliably behind Docker NAT/port remaps in HA OS.
- Home Assistant VoIP defaults to SIP UDP `5060`.
- Hostnames in `ha_host` are resolved to IPv4 before dialing because Home Assistant's VoIP SIP parser expects an IPv4 address in the request URI.
- For the HA OS add-on, `127.0.0.1` is recommended because the shim and Home Assistant share host networking.
- `rtp_port_start` reserves two 200-port ranges: one for the UniFi leg and one for the Home Assistant leg.
- This shim defaults to local SIP UDP `5080`, avoiding conflict when both run on the same HA host.
- UniFi Talk typically uses SIP UDP `5060` as the registrar endpoint.

## Troubleshooting checklist

1. **Registration fails (401/403):** re-check UniFi extension user/password and third-party SIP permissions.
2. **Cannot call HA:** confirm `ha_host` and `ha_sip_port`, and verify HA VoIP integration is enabled.
3. **Port conflict:** ensure no other process is bound to `local_sip_port` (default `5080`) or HA SIP `5060`.
4. **No/one-way audio:** verify firewall rules permit RTP both directions and that VLAN ACLs allow host <-> UniFi Talk <-> HA traffic.
5. **Intermittent media:** try `debug: true`, inspect add-on logs, and confirm network jitter/packet loss is low.

## Notes / limitations

- Passwords are read from add-on options and are not echoed to logs.
- UniFi Talk SIP behavior can vary by controller/firmware version.
