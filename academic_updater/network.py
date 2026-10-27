"""Bounded HTTP requests, public-source validation, and plain-text extraction."""
from __future__ import annotations
import html
import ipaddress
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser


class AppError(Exception):
    def __init__(self, code, detail='', status=400):
        super().__init__(detail or code)
        self.code, self.detail, self.status = code, detail, status


def validate_url(url, local=False):
    try:
        p = urllib.parse.urlsplit(url)
        if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
            raise ValueError()
        port = p.port or (443 if p.scheme == 'https' else 80)
        addresses = {x[4][0] for x in socket.getaddrinfo(p.hostname, port, type=socket.SOCK_STREAM)}
        if not addresses:
            raise ValueError()
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if local:
                if not ip.is_loopback:
                    raise ValueError()
            elif not ip.is_global:
                raise ValueError()
        if p.scheme != 'https' and not local:
            raise ValueError()
    except (ValueError, OSError) as exc:
        raise AppError('invalid_url', 'Use a public HTTPS URL, or a loopback URL for a local model.') from exc
    return url


class RedirectPolicy(urllib.request.HTTPRedirectHandler):
    def __init__(self, local=False, allow_redirects=True):
        self.local, self.allow_redirects = local, allow_redirects

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not self.allow_redirects or req.get_header('Authorization'):
            raise AppError('redirect_rejected', 'An authenticated request attempted to redirect.')
        validate_url(newurl, self.local)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request(url, *, data=None, headers=None, local=False, timeout=35, limit=8_000_000, stream=False):
    validate_url(url, local)
    headers = {'User-Agent': 'AcademicUpdater/1.0 (personal research library)', 'Accept': 'application/json, application/atom+xml, application/rss+xml, */*', **(headers or {})}
    # No redirects for POST or credentials. Source redirects are revalidated.
    opener = urllib.request.build_opener(RedirectPolicy(local, data is None))
    req = urllib.request.Request(url, data=data, headers=headers)
    for attempt in range(3):
        try:
            response = opener.open(req, timeout=timeout)
            if stream:
                return response
            with response:
                body = response.read(limit + 1)
                if len(body) > limit:
                    raise AppError('response_too_large')
                return body
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 502, 503, 504) and data is None and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            # Never include upstream request bodies, query tokens, or raw error pages.
            error=AppError('upstream_http_error', f'{urllib.parse.urlsplit(url).hostname}: HTTP {exc.code}', 502)
            try:error.retry_after=min(300,max(0,int(exc.headers.get('Retry-After','0'))))
            except (TypeError,ValueError):error.retry_after=0
            raise error from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AppError('network_error', f'Could not connect to {urllib.parse.urlsplit(url).hostname}.', 502) from exc


def get_json(url, **kwargs):
    try:
        return json.loads(request(url, **kwargs))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppError('invalid_upstream_json', status=502) from exc


def post_json(url, payload, **kwargs):
    return get_json(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', **kwargs.pop('headers', {})}, **kwargs)


def post_form(url, payload):
    return get_json(url, data=urllib.parse.urlencode(payload).encode(), headers={'Content-Type': 'application/x-www-form-urlencoded'})


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.meta, self.title = [], {}, []
        self.meta_values={}
        self.skip = 0
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self.skip += 1
        if tag == 'title':
            self.in_title = True
        if tag == 'meta':
            key = attrs.get('name') or attrs.get('property')
            if key:
                self.meta[key.lower()] = attrs.get('content', '')
                self.meta_values.setdefault(key.lower(),[]).append(attrs.get('content',''))

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self.skip = max(0, self.skip - 1)
        if tag == 'title':
            self.in_title = False

    def handle_data(self, value):
        if not self.skip:
            self.parts.append(value)
            if self.in_title:
                self.title.append(value)


def plain(value):
    p = TextParser()
    p.feed(str(value or ''))
    return re.sub(r'\s+', ' ', html.unescape(' '.join(p.parts))).strip()


def canonical_url(url):
    p = urllib.parse.urlsplit(url.strip())
    query = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid')]
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/') or '/', urllib.parse.urlencode(sorted(query)), ''))


def doi(value):
    value = urllib.parse.unquote(str(value or '').strip())
    value = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', value, flags=re.I)
    return value.lower() if re.fullmatch(r'10\.\d{4,9}/\S+', value, flags=re.I) else ''


def arxiv_id(value):
    value = re.sub(r'^https?://(?:export\.)?arxiv\.org/(?:abs|pdf)/', '', str(value or '').strip())
    value = value.removesuffix('.pdf')
    return re.sub(r'v\d+$', '', value) if re.fullmatch(r'(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?', value) else ''
