import socket

import httpx
import pytest
import respx

from apps.integrations.fetch import FetchError, safe_get
from apps.integrations.product_page import parse_html


def fake_dns(mapping):
    def getaddrinfo(host, port, *args, **kwargs):
        ip = mapping[host]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    return getaddrinfo


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.1", "0.0.0.0"])
def test_private_addresses_are_refused(monkeypatch, settings, ip):
    settings.FETCH_ALLOW_PRIVATE_HOSTS = False
    monkeypatch.setattr(socket, "getaddrinfo", fake_dns({"evil.example": ip}))
    with pytest.raises(FetchError):
        safe_get("http://evil.example/")


def test_non_http_schemes_refused(settings):
    with pytest.raises(FetchError):
        safe_get("file:///etc/passwd")
    with pytest.raises(FetchError):
        safe_get("http://user:pw@shop.example/")


@respx.mock
def test_redirect_to_private_address_is_refused(monkeypatch, settings):
    settings.FETCH_ALLOW_PRIVATE_HOSTS = False
    monkeypatch.setattr(
        socket, "getaddrinfo", fake_dns({"shop.example": "93.184.216.34", "internal.example": "10.1.2.3"})
    )
    respx.get("http://93.184.216.34/p").mock(
        return_value=httpx.Response(302, headers={"location": "http://internal.example/admin"})
    )
    with pytest.raises(FetchError):
        safe_get("http://shop.example/p")


@respx.mock
def test_connects_to_vetted_ip_with_host_header(monkeypatch, settings):
    settings.FETCH_ALLOW_PRIVATE_HOSTS = False
    monkeypatch.setattr(socket, "getaddrinfo", fake_dns({"shop.example": "93.184.216.34"}))
    route = respx.get("http://93.184.216.34/item").mock(return_value=httpx.Response(200, text="<p>ok</p>"))
    result = safe_get("http://shop.example/item")
    assert result.status == 200 and "ok" in result.text
    assert route.calls.last.request.headers["host"] == "shop.example"


def test_parse_json_ld_product():
    html = """<html><head><title>Fallback</title>
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",
      "name":"SunShield SPF 50 Gel","description":"Lightweight gel sunscreen for oily skin.",
      "brand":{"@type":"Brand","name":"GlowLeaf"},"offers":{"@type":"Offer","price":"499","priceCurrency":"INR"}}
    </script></head><body><h1>SunShield</h1><p>No white cast.</p></body></html>"""
    page = parse_html("https://shop.example/p", html)
    assert page.title == "SunShield SPF 50 Gel"
    assert page.brand == "GlowLeaf"
    assert page.price_inr == 499.0
    assert "No white cast" in page.text
