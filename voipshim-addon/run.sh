#!/usr/bin/with-contenv bash
set -euo pipefail

CONFIG_PATH=/data/options.json

export UNIFI_SIP_SERVER
UNIFI_SIP_SERVER="$(jq -r '.unifi_sip_server' "$CONFIG_PATH")"
export UNIFI_SIP_USER
UNIFI_SIP_USER="$(jq -r '.unifi_sip_user' "$CONFIG_PATH")"
export UNIFI_SIP_PASS
UNIFI_SIP_PASS="$(jq -r '.unifi_sip_pass' "$CONFIG_PATH")"
export HA_HOST
HA_HOST="$(jq -r '.ha_host' "$CONFIG_PATH")"

export UNIFI_SIP_PORT
UNIFI_SIP_PORT="$(jq -r '.unifi_sip_port // 5060' "$CONFIG_PATH")"
export HA_SIP_PORT
HA_SIP_PORT="$(jq -r '.ha_sip_port // 5060' "$CONFIG_PATH")"
export LOCAL_SIP_PORT
LOCAL_SIP_PORT="$(jq -r '.local_sip_port // 5080' "$CONFIG_PATH")"
export RTP_PORT_START
RTP_PORT_START="$(jq -r '.rtp_port_start // 10000' "$CONFIG_PATH")"
export LOG_LEVEL
LOG_LEVEL="$(jq -r '.log_level // "INFO"' "$CONFIG_PATH")"
export PJSIP_LOG_LEVEL
PJSIP_LOG_LEVEL="$(jq -r '.pjsip_log_level // 3' "$CONFIG_PATH")"
export MAX_CALLS
MAX_CALLS="$(jq -r '.max_calls // 4' "$CONFIG_PATH")"

DEBUG="$(jq -r '.debug // false' "$CONFIG_PATH")"
if [[ "$DEBUG" == "true" ]]; then
  export LOG_LEVEL="DEBUG"
  export PJSIP_LOG_LEVEL="5"
fi

echo "voipshim add-on starting"
echo "  UniFi Talk : ${UNIFI_SIP_SERVER}:${UNIFI_SIP_PORT} user=${UNIFI_SIP_USER}"
echo "  Home Asst  : ${HA_HOST}:${HA_SIP_PORT}"
echo "  Local SIP  : ${LOCAL_SIP_PORT}"

echo "Launching shim (password hidden)"
exec python3 -u /app/shim.py
