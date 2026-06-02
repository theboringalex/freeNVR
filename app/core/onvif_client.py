"""
ONVIF client — raw SOAP over aiohttp, no WSDL dependency.

Supports:
  - WS-Discovery (find cameras on LAN)
  - GetDeviceInformation / GetStreamUri
  - CreatePullPointSubscription + PullMessages (motion events)

WS-Security uses PasswordDigest as required by most cameras incl. Reolink.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import re
import socket
import struct
import uuid
from datetime import datetime, UTC
from typing import Optional

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

# ─── WS-Security ──────────────────────────────────────────────────────────────

def _ws_security(username: str, password: str) -> str:
    nonce_raw = os.urandom(20)
    created = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    digest = base64.b64encode(
        hashlib.sha1(nonce_raw + created.encode() + password.encode()).digest()
    ).decode()
    nonce_b64 = base64.b64encode(nonce_raw).decode()
    return f"""<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
                              xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
    <wsse:UsernameToken>
      <wsse:Username>{username}</wsse:Username>
      <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</wsse:Password>
      <wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_b64}</wsse:Nonce>
      <wsu:Created>{created}</wsu:Created>
    </wsse:UsernameToken>
  </wsse:Security>"""


def _envelope(body: str, username: str = "", password: str = "") -> str:
    security = _ws_security(username, password) if username else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
            xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
            xmlns:tev="http://www.onvif.org/ver10/events/wsdl"
            xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"
            xmlns:tns1="http://www.onvif.org/ver10/topics"
            xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <s:Header>{security}</s:Header>
  <s:Body>{body}</s:Body>
</s:Envelope>"""


# ─── XML helpers ──────────────────────────────────────────────────────────────

def _find(xml: str, tag: str) -> Optional[str]:
    """Extract first inner text of a tag (strips namespace prefix)."""
    pattern = rf"<(?:[^:>]+:)?{re.escape(tag)}[^>]*>(.*?)</(?:[^:>]+:)?{re.escape(tag)}>"
    m = re.search(pattern, xml, re.DOTALL)
    return m.group(1).strip() if m else None


def _find_attr(xml: str, tag: str, attr: str) -> Optional[str]:
    pattern = rf"<(?:[^:>]+:)?{re.escape(tag)}[^>]*\s{re.escape(attr)}=['\"]([^'\"]*)['\"]"
    m = re.search(pattern, xml)
    return m.group(1) if m else None


def _find_all(xml: str, tag: str) -> list[str]:
    pattern = rf"<(?:[^:>]+:)?{re.escape(tag)}[^>]*>(.*?)</(?:[^:>]+:)?{re.escape(tag)}>"
    return [m.group(1).strip() for m in re.finditer(pattern, xml, re.DOTALL)]


# ─── ONVIF HTTP client ────────────────────────────────────────────────────────

async def _soap_post(url: str, body: str, username: str, password: str, timeout: int = 10) -> str:
    envelope = _envelope(body, username, password)
    async with aiohttp.ClientSession() as sess:
        async with sess.post(
            url,
            data=envelope.encode("utf-8"),
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            return await resp.text()


# ─── Device info & stream URI ─────────────────────────────────────────────────

async def get_device_info(host: str, port: int, username: str, password: str) -> dict:
    url = f"http://{host}:{port}/onvif/device_service"
    xml = await _soap_post(url, "<tds:GetDeviceInformation/>", username, password)
    return {
        "manufacturer": _find(xml, "Manufacturer") or "",
        "model": _find(xml, "Model") or "",
        "firmware": _find(xml, "FirmwareVersion") or "",
        "serial": _find(xml, "SerialNumber") or "",
    }


async def get_stream_uri(host: str, port: int, username: str, password: str) -> Optional[str]:
    """Returns the first RTSP stream URI from the device via ONVIF media service."""
    url = f"http://{host}:{port}/onvif/media_service"

    # Get profiles
    profiles_xml = await _soap_post(url, "<trt:GetProfiles/>", username, password)
    token_match = re.search(r'<(?:[^:>]+:)?Profiles[^>]*\stoken=[\'"]([^\'"]+)[\'"]', profiles_xml)
    if not token_match:
        # Try without attribute-style token
        token_match = re.search(r'token=[\'"]([^\'"]+)[\'"]', profiles_xml)
    if not token_match:
        logger.warning("No ONVIF profile token found at %s:%d", host, port)
        return None
    token = token_match.group(1)

    body = f"""<trt:GetStreamUri>
      <trt:StreamSetup>
        <tt:Stream xmlns:tt="http://www.onvif.org/ver10/schema">RTP-Unicast</tt:Stream>
        <tt:Transport xmlns:tt="http://www.onvif.org/ver10/schema">
          <tt:Protocol>RTSP</tt:Protocol>
        </tt:Transport>
      </trt:StreamSetup>
      <trt:ProfileToken>{token}</trt:ProfileToken>
    </trt:GetStreamUri>"""

    uri_xml = await _soap_post(url, body, username, password)
    uri = _find(uri_xml, "Uri")
    if uri and username:
        # Embed credentials into RTSP URL
        uri = _embed_credentials(uri, username, password)
    return uri


def _embed_credentials(url: str, user: str, password: str) -> str:
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        rest = rest.split("@", 1)[1]
    return f"{scheme}://{user}:{password}@{rest}"


# ─── PullPoint subscription ───────────────────────────────────────────────────

# Motion topics Reolink and other cameras use
_MOTION_TOPICS = (
    "tns1:VideoSource/MotionAlarm",
    "tns1:RuleEngine/CellMotionDetector/Motion",
    "tns1:RuleEngine/MotionRegionDetector/Motion",
    "tns1:RuleEngine/MyRuleDetector/Visitor",
)
_TOPIC_FILTER = "|".join(_MOTION_TOPICS)


async def _create_pullpoint(event_url: str, username: str, password: str) -> Optional[str]:
    """Creates a PullPoint subscription; returns the subscription address."""
    body = f"""<tev:CreatePullPointSubscription>
      <tev:Filter>
        <wsnt:TopicExpression Dialect="http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet"
          xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">{_TOPIC_FILTER}</wsnt:TopicExpression>
      </tev:Filter>
      <tev:InitialTerminationTime>PT600S</tev:InitialTerminationTime>
    </tev:CreatePullPointSubscription>"""
    try:
        xml = await _soap_post(event_url, body, username, password)
        addr = _find(xml, "Address") or _find(xml, "SubscriptionReference")
        return addr
    except Exception as e:
        logger.debug("CreatePullPointSubscription failed at %s: %s", event_url, e)
        return None


async def _pull_messages(sub_url: str, username: str, password: str) -> list[dict]:
    """Pulls pending messages from a PullPoint subscription."""
    body = """<tev:PullMessages xmlns:tev="http://www.onvif.org/ver10/events/wsdl">
      <tev:Timeout>PT2S</tev:Timeout>
      <tev:MessageLimit>100</tev:MessageLimit>
    </tev:PullMessages>"""
    try:
        xml = await _soap_post(sub_url, body, username, password, timeout=8)
        return _parse_notification_messages(xml)
    except Exception as e:
        logger.debug("PullMessages failed: %s", e)
        return []


def _parse_notification_messages(xml: str) -> list[dict]:
    """Parse NotificationMessages from PullMessages response."""
    events = []
    for msg_xml in _find_all(xml, "NotificationMessage"):
        topic = _find(msg_xml, "Topic") or ""
        topic = topic.strip()

        # Extract SimpleItem values (IsMotion, State, etc.)
        is_motion = False
        for item_xml in re.finditer(
            r'<(?:[^:>]+:)?SimpleItem[^>]*Name=[\'"]([^\'"]+)[\'"][^>]*Value=[\'"]([^\'"]+)[\'"]',
            msg_xml,
        ):
            name, value = item_xml.group(1), item_xml.group(2)
            if name.lower() in ("ismotion", "state", "motionstate", "alarm"):
                is_motion = value.lower() in ("true", "1", "motion")

        # Some cameras set PropertyOperation="Changed" with motion data
        prop_op = _find_attr(msg_xml, "Message", "PropertyOperation") or ""

        if _is_motion_topic(topic):
            events.append({"topic": topic, "is_motion": is_motion, "property_op": prop_op})
    return events


def _is_motion_topic(topic: str) -> bool:
    return any(t in topic for t in _MOTION_TOPICS) or "motion" in topic.lower() or "alarm" in topic.lower()


# ─── ONVIFEventSubscriber ─────────────────────────────────────────────────────

class ONVIFEventSubscriber:
    """
    Long-running subscriber for one camera's ONVIF PullPoint events.
    Calls `on_motion(camera_id)` when a motion event is detected.
    """

    def __init__(self, camera: dict, on_motion):
        self.camera = camera
        self.on_motion = on_motion
        self._task: asyncio.Task | None = None
        self.running = False

    def start(self):
        self.running = True
        self._task = asyncio.create_task(self._run(), name=f"onvif-{self.camera['id']}")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self):
        cam = self.camera
        host = cam.get("onvif_host") or _host_from_rtsp(cam.get("rtsp_url", ""))
        port = cam.get("onvif_port") or 8000
        user = cam.get("username") or ""
        pwd = cam.get("password") or ""
        event_url = f"http://{host}:{port}/onvif/event_service"
        cam_id = cam["id"]

        logger.info("ONVIF subscriber starting for camera %d @ %s:%d", cam_id, host, port)
        sub_url = None
        last_sub_attempt = 0.0

        while self.running:
            now = asyncio.get_event_loop().time()

            # (Re)create subscription every ~9 minutes
            if sub_url is None or (now - last_sub_attempt) > 540:
                sub_url = await _create_pullpoint(event_url, user, pwd)
                last_sub_attempt = now
                if not sub_url:
                    logger.warning("Camera %d: ONVIF PullPoint unavailable, retry in 30s", cam_id)
                    await asyncio.sleep(30)
                    continue
                logger.debug("Camera %d: PullPoint subscription at %s", cam_id, sub_url)

            messages = await _pull_messages(sub_url, user, pwd)
            for msg in messages:
                if msg["is_motion"]:
                    logger.info("Camera %d: ONVIF motion event [%s]", cam_id, msg["topic"])
                    await self.on_motion(cam_id, source="onvif", topic=msg["topic"])

            await asyncio.sleep(settings.ONVIF_PULL_INTERVAL)


def _host_from_rtsp(rtsp_url: str) -> str:
    """Extract host from rtsp://[user:pass@]host[:port]/..."""
    m = re.search(r"rtsp://(?:[^@]+@)?([^/:]+)", rtsp_url)
    return m.group(1) if m else ""


# ─── WS-Discovery ─────────────────────────────────────────────────────────────

_WSD_PROBE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
    ' xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"'
    ' xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">'
    "<s:Header>"
    "<a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action>"
    f"<a:MessageID>uuid:{uuid.uuid4()}</a:MessageID>"
    "<a:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To>"
    "</s:Header>"
    "<s:Body>"
    '<d:Probe><d:Types xmlns:dp0="http://www.onvif.org/ver10/network/wsdl">dp0:NetworkVideoTransmitter</d:Types></d:Probe>'
    "</s:Body>"
    "</s:Envelope>"
)

_WSD_MCAST_ADDR = "239.255.255.250"
_WSD_PORT = 3702


async def discover_cameras(timeout: float = 5.0) -> list[dict]:
    """WS-Discovery broadcast; returns list of {address, name, hardware, location}."""
    results: list[dict] = []
    seen: set[str] = set()

    loop = asyncio.get_event_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
    sock.settimeout(0)

    try:
        sock.sendto(_WSD_PROBE.encode(), (_WSD_MCAST_ADDR, _WSD_PORT))
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            remaining = deadline - loop.time()
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(None, _recv_wsd, sock),
                    timeout=min(remaining, 1.0),
                )
            except (asyncio.TimeoutError, OSError):
                pass
            # Drain all available responses
            while True:
                try:
                    data, addr = sock.recvfrom(65535)
                    xml = data.decode("utf-8", errors="replace")
                    xaddrs = _find(xml, "XAddrs") or ""
                    for xaddr in xaddrs.split():
                        host_m = re.search(r"https?://([^/:]+)", xaddr)
                        if not host_m:
                            continue
                        host = host_m.group(1)
                        if host in seen:
                            continue
                        seen.add(host)
                        results.append({
                            "address": host,
                            "xaddr": xaddr,
                            "name": _find(xml, "Name") or "",
                            "hardware": _find(xml, "Hardware") or "",
                            "location": _find(xml, "Location") or "",
                        })
                except BlockingIOError:
                    break
    finally:
        sock.close()

    return results


def _recv_wsd(sock: socket.socket) -> bytes:
    data, _ = sock.recvfrom(65535)
    return data
