"""HedgeHog's HTTPS calls trust a CA bundle even where OpenSSL finds none.

The Linux AppImage bundles Ubuntu's OpenSSL, compiled to read certificates
from /usr/lib/ssl; Fedora keeps them elsewhere, so the default context had no
CA at all and every call failed with CERTIFICATE_VERIFY_FAILED.
"""

import ssl

import certifi

from ankigammon.utils import hedgehog_client
from ankigammon.utils.hedgehog_client import HedgehogClient, ssl_context


def _empty_default_context(*args, **kwargs):
    return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def test_falls_back_to_certifi_when_openssl_finds_no_certificates(monkeypatch):
    certifi_roots = ssl.create_default_context(cafile=certifi.where()).get_ca_certs()
    monkeypatch.setattr(hedgehog_client.ssl, "create_default_context", _empty_default_context)

    context = ssl_context()

    assert len(context.get_ca_certs()) == len(certifi_roots)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname


def test_keeps_the_systems_store_when_it_has_certificates():
    system = ssl.create_default_context().get_ca_certs()
    if system:
        assert ssl_context().get_ca_certs() == system


def test_requests_use_that_context():
    session = HedgehogClient(store=object())._session()
    context = session.get_adapter("https://hedgehog-bg.com").poolmanager.connection_pool_kw["ssl_context"]

    assert isinstance(context, ssl.SSLContext)
    assert context.get_ca_certs()
