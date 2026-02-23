#!/usr/bin/env python3
"""
s9t-voipshim — UniFi Talk ↔ Home Assistant VOIP bridge.

Registers as a SIP extension on a UniFi Talk server, auto-answers
incoming calls, and bridges audio to Home Assistant's VOIP integration
using PJSIP's conference bridge.

Call flow:
  1. UniFi Talk sends SIP INVITE → shim answers with 180 Ringing
  2. Shim dials Home Assistant (SIP INVITE)
  3. HA answers → shim answers UniFi Talk side (200 OK)
  4. PJSIP conference bridge connects audio from both legs
  5. Either side hangs up → shim tears down both legs
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading

import pjsua2 as pj

# ── Configuration ──────────────────────────────────────────────────────────


def _require(name: str) -> str:
    """Return env var or exit with a clear message."""
    val = os.environ.get(name)
    if not val:
        print(f"FATAL: environment variable {name} is required", file=sys.stderr)
        sys.exit(1)
    return val


UNIFI_HOST = _require("UNIFI_SIP_SERVER")
UNIFI_PORT = int(os.environ.get("UNIFI_SIP_PORT", "5060"))
UNIFI_USER = _require("UNIFI_SIP_USER")
UNIFI_PASS = _require("UNIFI_SIP_PASS")

HA_HOST = _require("HA_HOST")
HA_PORT = int(os.environ.get("HA_SIP_PORT", "5060"))

LOCAL_SIP_PORT = int(os.environ.get("LOCAL_SIP_PORT", "5080"))
RTP_PORT_START = int(os.environ.get("RTP_PORT_START", "10000"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
PJSIP_LOG_LEVEL = int(os.environ.get("PJSIP_LOG_LEVEL", "3"))
MAX_CALLS = int(os.environ.get("MAX_CALLS", "4"))

HEALTH_FILE = "/tmp/voipshim-healthy"

log = logging.getLogger("voipshim")

# ── Helpers ────────────────────────────────────────────────────────────────


def _active_audio(call: pj.Call) -> pj.AudioMedia | None:
    """Return the first active AudioMedia for *call*, or None."""
    try:
        ci = call.getInfo()
        for i in range(ci.media.size()):
            mi = ci.media[i]
            if (
                mi.type == pj.PJMEDIA_TYPE_AUDIO
                and mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE
            ):
                return pj.AudioMedia.typecastFromMedia(call.getMedia(i))
    except Exception:
        pass
    return None


def _hangup(call: pj.Call, code: int = 0) -> None:
    """Hang up *call* unless already disconnected."""
    try:
        ci = call.getInfo()
        if ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            return
        prm = pj.CallOpParam()
        if code > 0:
            prm.statusCode = code
        call.hangup(prm)
    except Exception:
        pass


# ── Call legs ──────────────────────────────────────────────────────────────


class HACall(pj.Call):
    """Outbound call leg: shim → Home Assistant VOIP."""

    def __init__(self, acc: pj.Account, unifi_call: UniFiCall) -> None:
        pj.Call.__init__(self, acc)
        self.unifi_call = unifi_call
        self._bridged = False

    def onCallState(self, prm: pj.OnCallStateParam) -> None:
        ci = self.getInfo()
        log.info("HA   leg: %s  (code %d)", ci.stateText, ci.lastStatusCode)

        if ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
            # HA answered — now answer the UniFi Talk side
            log.info("HA answered -> answering UniFi side")
            ans = pj.CallOpParam()
            ans.statusCode = 200
            try:
                self.unifi_call.answer(ans)
            except Exception:
                log.exception("Cannot answer UniFi side")

        elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            log.info("HA leg disconnected")
            _hangup(self.unifi_call, 503)

    def onCallMediaState(self, prm: pj.OnCallMediaStateParam) -> None:
        self._try_bridge()

    def _try_bridge(self) -> None:
        if self._bridged:
            return
        ha_aud = _active_audio(self)
        uni_aud = _active_audio(self.unifi_call)
        if ha_aud is None or uni_aud is None:
            log.debug("Audio not ready on both legs yet")
            return
        try:
            ha_aud.startTransmit(uni_aud)
            uni_aud.startTransmit(ha_aud)
            self._bridged = True
            log.info("Audio bridged: UniFi <-> HA")
        except Exception:
            log.exception("Bridge failed")


class UniFiCall(pj.Call):
    """Inbound call leg: UniFi Talk → shim."""

    def __init__(
        self, acc: pj.Account, ha_account: pj.Account, call_id: int
    ) -> None:
        pj.Call.__init__(self, acc, call_id)
        self.ha_account = ha_account
        self.ha_call: HACall | None = None

    def onCallState(self, prm: pj.OnCallStateParam) -> None:
        ci = self.getInfo()
        log.info("UniFi leg: %s  (code %d)", ci.stateText, ci.lastStatusCode)

        if ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            log.info("UniFi leg disconnected")
            if self.ha_call is not None:
                _hangup(self.ha_call)

    def onCallMediaState(self, prm: pj.OnCallMediaStateParam) -> None:
        if self.ha_call is not None:
            self.ha_call._try_bridge()

    def dial_ha(self) -> None:
        """Place outgoing call to Home Assistant."""
        uri = f"sip:ha@{HA_HOST}:{HA_PORT}"
        log.info("Dialling Home Assistant at %s", uri)
        self.ha_call = HACall(self.ha_account, self)
        prm = pj.CallOpParam(True)
        try:
            self.ha_call.makeCall(uri, prm)
        except Exception:
            log.exception("Failed to dial HA")
            _hangup(self, 503)


# ── Accounts ───────────────────────────────────────────────────────────────


class UniFiAccount(pj.Account):
    """SIP account registered with UniFi Talk.

    Every incoming call is auto-answered and bridged to Home Assistant.
    """

    def __init__(self, ha_account: pj.Account) -> None:
        pj.Account.__init__(self)
        self.ha_account = ha_account

    def onRegState(self, prm: pj.OnRegStateParam) -> None:
        ai = self.getInfo()
        log.info(
            "SIP registration: %s  (code %d, active=%s)",
            ai.regStatusText,
            ai.regStatus,
            ai.regIsActive,
        )
        try:
            if ai.regIsActive:
                with open(HEALTH_FILE, "w") as fh:
                    fh.write("ok\n")
            else:
                os.remove(HEALTH_FILE)
        except OSError:
            pass

    def onIncomingCall(self, prm: pj.OnIncomingCallParam) -> None:
        call = UniFiCall(self, self.ha_account, prm.callId)
        ci = call.getInfo()
        log.info("Incoming call from %s", ci.remoteUri)

        # Tell caller we're ringing
        ring = pj.CallOpParam()
        ring.statusCode = 180
        try:
            call.answer(ring)
        except Exception:
            log.exception("Cannot send 180 Ringing")
            return

        # Dial HA — when HA answers, HACall.onCallState answers UniFi side
        call.dial_ha()


class HALocalAccount(pj.Account):
    """Un-registered local account used only to place calls to HA."""

    def onRegState(self, prm: pj.OnRegStateParam) -> None:
        pass  # never registered


# ── Entry point ────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    log.info("voipshim starting")
    log.info("  UniFi Talk : %s:%d  user=%s", UNIFI_HOST, UNIFI_PORT, UNIFI_USER)
    log.info("  Home Asst  : %s:%d", HA_HOST, HA_PORT)
    log.info("  Local SIP  : port %d", LOCAL_SIP_PORT)

    # ── PJSUA2 endpoint ──────────────────────────────────────────────

    ep = pj.Endpoint()
    ep.libCreate()

    ep_cfg = pj.EpConfig()
    ep_cfg.logConfig.level = PJSIP_LOG_LEVEL
    ep_cfg.logConfig.consoleLevel = PJSIP_LOG_LEVEL
    ep_cfg.uaConfig.maxCalls = MAX_CALLS
    ep_cfg.uaConfig.userAgent = "s9t-voipshim/1.0"
    # Single worker thread — callbacks are simple and non-blocking
    ep_cfg.uaConfig.threadCnt = 1
    # No echo cancellation or VAD needed for a call bridge
    ep_cfg.medConfig.noVad = True
    ep_cfg.medConfig.ecTailLen = 0
    # RTP port range — avoid low ports that may conflict
    ep_cfg.medConfig.portRange = 200

    ep.libInit(ep_cfg)

    # UDP transport for SIP
    tp_cfg = pj.TransportConfig()
    tp_cfg.port = LOCAL_SIP_PORT
    tp_cfg.portRange = 0  # exact port, no fallback
    tp_id = ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, tp_cfg)
    log.info("UDP transport created on port %d (id=%d)", LOCAL_SIP_PORT, tp_id)

    ep.libStart()

    # No sound device in Docker — use null audio
    ep.audDevManager().setNullDev()
    log.info("PJSIP started (null audio device)")

    # ── HA account (local, no registration) ──────────────────────────

    ha_cfg = pj.AccountConfig()
    ha_cfg.idUri = f"sip:voipshim@{HA_HOST}"
    ha_cfg.regConfig.registerOnAdd = False
    # Bind to our UDP transport so outgoing INVITEs use it
    ha_cfg.sipConfig.transportId = tp_id
    # Use high RTP ports to avoid conflicts
    ha_cfg.mediaConfig.transportConfig.port = RTP_PORT_START
    ha_cfg.mediaConfig.transportConfig.portRange = 200
    ha_acc = HALocalAccount()
    ha_acc.create(ha_cfg)

    # ── UniFi Talk account (registered) ──────────────────────────────

    uni_cfg = pj.AccountConfig()
    uni_cfg.idUri = f"sip:{UNIFI_USER}@{UNIFI_HOST}"
    uni_cfg.regConfig.registrarUri = f"sip:{UNIFI_HOST}:{UNIFI_PORT}"
    uni_cfg.regConfig.timeoutSec = 300
    uni_cfg.regConfig.retryIntervalSec = 30
    # Use high RTP ports to avoid conflicts
    uni_cfg.mediaConfig.transportConfig.port = RTP_PORT_START
    uni_cfg.mediaConfig.transportConfig.portRange = 200

    cred = pj.AuthCredInfo("digest", "*", UNIFI_USER, 0, UNIFI_PASS)
    uni_cfg.sipConfig.authCreds.append(cred)

    uni_acc = UniFiAccount(ha_acc)
    uni_acc.create(uni_cfg)

    log.info("Registered with UniFi Talk - waiting for calls")

    # ── Graceful shutdown ────────────────────────────────────────────

    stop = threading.Event()

    def _on_signal(signum: int, _frame: object) -> None:
        log.info("Signal %d received - shutting down", signum)
        stop.set()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    try:
        while not stop.is_set():
            stop.wait(1.0)
    except KeyboardInterrupt:
        pass

    log.info("Shutting down")
    try:
        os.remove(HEALTH_FILE)
    except OSError:
        pass
    ep.libDestroy()
    log.info("voipshim stopped")


if __name__ == "__main__":
    main()
