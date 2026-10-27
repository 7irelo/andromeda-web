"""
SSRF-safe OpenGraph fetcher for link previews.

The server fetches URLs chosen by users, so every hop is checked:
- only http(s) on ports 80/443, no credentials in the URL
- the hostname is resolved once and every address must be public
  (no private, loopback, link-local, multicast, reserved or metadata ranges)
- the connection is pinned to the vetted IP, so DNS rebinding can't swap it
- redirects are followed manually (max 3) and each hop is re-validated
- 5 s timeouts, HTML only, at most 512 KB read
"""
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import urllib3

MAX_BYTES = 512 * 1024
MAX_REDIRECTS = 3
TIMEOUT = urllib3.Timeout(connect=3.0, read=5.0)
USER_AGENT = 'AndromedaLinkPreview/1.0 (+https://github.com/7irelo/andromeda-web)'


class UnsafeURL(Exception):
    pass


def _public_ip(host):
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURL('DNS lookup failed') from exc
    addresses = {info[4][0] for info in infos}
    for addr in addresses:
        ip = ipaddress.ip_address(addr.split('%')[0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURL(f'{host} resolves to a non-public address')
    return sorted(addresses)[0]


def validate_url(url):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https'):
        raise UnsafeURL('Only http(s) URLs are allowed')
    if parts.username or parts.password:
        raise UnsafeURL('Credentials in URLs are not allowed')
    if not parts.hostname:
        raise UnsafeURL('Missing host')
    port = parts.port or (443 if parts.scheme == 'https' else 80)
    if port not in (80, 443):
        raise UnsafeURL('Only ports 80 and 443 are allowed')
    return parts, port, _public_ip(parts.hostname)


def _get(url):
    parts, port, ip = validate_url(url)
    path = parts.path or '/'
    if parts.query:
        path += '?' + parts.query
    headers = {'Host': parts.hostname, 'User-Agent': USER_AGENT, 'Accept': 'text/html'}
    if parts.scheme == 'https':
        pool = urllib3.HTTPSConnectionPool(
            ip, port, server_hostname=parts.hostname, assert_hostname=parts.hostname,
            cert_reqs='CERT_REQUIRED', timeout=TIMEOUT, retries=False,
        )
    else:
        pool = urllib3.HTTPConnectionPool(ip, port, timeout=TIMEOUT, retries=False)
    return pool.request('GET', path, headers=headers, redirect=False, preload_content=False)


class _OGParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self._in_title, self.title = {}, False, ''

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta':
            key = (a.get('property') or a.get('name') or '').lower()
            if key in ('og:title', 'og:description', 'og:image', 'description', 'twitter:image'):
                self.meta.setdefault(key, (a.get('content') or '').strip())
        elif tag == 'title':
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and len(self.title) < 300:
            self.title += data


def fetch_preview(url):
    """Return {'title', 'description', 'image'} or raise UnsafeURL / urllib3 errors."""
    for _ in range(MAX_REDIRECTS + 1):
        resp = _get(url)
        try:
            if resp.status in (301, 302, 303, 307, 308):
                location = resp.headers.get('Location')
                if not location:
                    raise UnsafeURL('Redirect without a location')
                url = urljoin(url, location)
                continue
            if resp.status != 200:
                raise UnsafeURL(f'Upstream returned {resp.status}')
            if 'text/html' not in resp.headers.get('Content-Type', ''):
                raise UnsafeURL('Not an HTML page')
            body = resp.read(MAX_BYTES, decode_content=True)
        finally:
            resp.release_conn()
        parser = _OGParser()
        parser.feed(body.decode('utf-8', errors='replace'))
        image = parser.meta.get('og:image') or parser.meta.get('twitter:image') or ''
        if image:
            image = urljoin(url, image)
            if urlsplit(image).scheme not in ('http', 'https'):
                image = ''
        return {
            'title': (parser.meta.get('og:title') or parser.title).strip()[:255],
            'description': (parser.meta.get('og:description') or parser.meta.get('description') or '')[:1000],
            'image': image[:200],
        }
    raise UnsafeURL('Too many redirects')
