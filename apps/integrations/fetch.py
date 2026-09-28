"""SSRF-safe HTTP fetching for user-supplied URLs (product pages).

A brand could submit a URL pointing at our own servers or cloud metadata (e.g. 169.254.169.254).
We resolve the hostname ourselves, refuse private/loopback/link-local/reserved addresses, and
then connect to the vetted IP directly (with the original Host header and TLS SNI), so a DNS
answer can't change between the check and the connection. Redirects are followed manually and
each hop is checked again.
"""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from django.conf import settings

MAX_BYTES = 3 * 1024 * 1024
MAX_REDIRECTS = 4
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
USER_AGENT = "Mozilla/5.0 (compatible; CreatorBridgeBot/1.0; +product-brief)"


class FetchError(Exception):
    pass


@dataclass
class FetchResult:
    url: str
    status: int
    content_type: str
    text: str


def _is_public(ip):
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


def resolve_public_ip(host, port):
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError(f"Couldn't find the website {host}.") from exc
    ips = [info[4][0] for info in infos]
    public = bool(ips) and all(_is_public(ip) for ip in ips)
    if not public and not settings.FETCH_ALLOW_PRIVATE_HOSTS:
        raise FetchError("That address isn't a public website.")
    return ips[0]


def _pinned_request(client, url):
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("Only http(s) links are supported.")
    if parts.username or parts.password:
        raise FetchError("Links with usernames or passwords aren't supported.")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    ip = resolve_public_ip(parts.hostname, port)
    ip_host = f"[{ip}]" if ":" in ip else ip
    netloc = f"{ip_host}:{parts.port}" if parts.port else ip_host
    pinned = urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))
    host_header = parts.hostname + (f":{parts.port}" if parts.port else "")
    return client.stream(
        "GET",
        pinned,
        headers={
            "Host": host_header,
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
        },
        extensions={"sni_hostname": parts.hostname},
    )


def safe_get(url):
    # trust_env=False: never route user-supplied URLs through ambient proxies.
    with httpx.Client(timeout=TIMEOUT, follow_redirects=False, trust_env=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                with _pinned_request(client, url) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise FetchError("The page redirected without a destination.")
                        url = urljoin(url, location)
                        continue
                    body = bytearray()
                    for chunk in resp.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            break
                    encoding = resp.encoding or "utf-8"
                    return FetchResult(
                        url=url,
                        status=resp.status_code,
                        content_type=resp.headers.get("content-type", ""),
                        text=bytes(body[:MAX_BYTES]).decode(encoding, errors="replace"),
                    )
            except httpx.HTTPError as exc:
                raise FetchError(f"Couldn't load the page ({exc.__class__.__name__}).") from exc
        raise FetchError("Too many redirects.")
