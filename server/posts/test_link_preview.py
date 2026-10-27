from unittest import mock

import pytest

from posts.link_preview import UnsafeURL, validate_url
from posts.tasks import extract_mentions, extract_tags, first_url


@pytest.mark.parametrize('url', [
    'http://127.0.0.1/', 'http://localhost/', 'http://10.0.0.5/', 'http://192.168.1.1/',
    'http://169.254.169.254/latest/meta-data/', 'http://[::1]/', 'http://0.0.0.0/',
    'file:///etc/passwd', 'gopher://example.com/', 'http://user:pw@example.com/',
    'http://example.com:6379/',
])
def test_ssrf_targets_rejected(url):
    with pytest.raises(UnsafeURL):
        validate_url(url)


def test_dns_rebinding_to_private_ip_rejected():
    with mock.patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('10.1.2.3', 0))]):
        with pytest.raises(UnsafeURL):
            validate_url('https://looks-public.example/')


def test_mixed_public_and_private_answers_rejected():
    answers = [(2, 1, 6, '', ('93.184.216.34', 0)), (2, 1, 6, '', ('127.0.0.1', 0))]
    with mock.patch('socket.getaddrinfo', return_value=answers):
        with pytest.raises(UnsafeURL):
            validate_url('https://example.com/')


def test_public_url_pins_resolved_ip():
    with mock.patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('93.184.216.34', 0))]):
        parts, port, ip = validate_url('https://example.com/page')
    assert (parts.hostname, port, ip) == ('example.com', 443, '93.184.216.34')


def test_hashtags_and_mentions():
    text = 'Run club at 6 #Running #running @thandi and @sipho.n, email me@x.com #a'
    assert extract_tags(text) == ['running']
    assert extract_mentions(text) == ['thandi', 'sipho.n']


def test_first_url_strips_punctuation():
    assert first_url('see https://example.com/a?b=1).') == 'https://example.com/a?b=1'
