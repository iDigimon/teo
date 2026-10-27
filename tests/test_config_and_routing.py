from unittest.mock import Mock

import pytest
from certbot import errors
from certbot.compat import filesystem

from certbot_dns_teo.dns_teo import _normalize_name
from certbot_dns_teo.teo_client import Zone


def test_zone_label_boundary(helper):
    with pytest.raises(errors.PluginError, match="No managed"):
        helper._get_zone("notexample.com")


def test_zone_apex(helper):
    assert helper._get_zone("EXAMPLE.COM.") == Zone("zone-com", "example.com")


def test_longest_managed_zone_and_cached_discovery(helper):
    assert helper._get_zone("_acme-challenge.sub.example.co.uk") == Zone(
        "zone-sub", "sub.example.co.uk"
    )
    assert helper._get_zone("_acme-challenge.other.example.co.uk") == Zone(
        "zone-uk", "example.co.uk"
    )
    helper.client.list_zones.assert_called_once()


def test_failed_discovery_can_be_retried(helper):
    helper.client.list_zones.side_effect = [
        errors.PluginError("denied"),
        [Zone("zone-com", "example.com")],
    ]
    with pytest.raises(errors.PluginError):
        helper._get_zone("_acme-challenge.example.com")
    assert helper._zones is None
    assert helper._get_zone("_acme-challenge.example.com") == Zone("zone-com", "example.com")


def test_unicode_name():
    assert _normalize_name("例子.公司.cn.") == "xn--fsqu00a.xn--55qx5d.cn"


@pytest.mark.parametrize("name", ["", "*.example.com", "a..com"])
def test_invalid_name(name):
    with pytest.raises(errors.PluginError):
        _normalize_name(name)


def write_credentials(tmp_path, authenticator, text):
    path = tmp_path / "teo.ini"
    path.write_text(text, encoding="utf-8")
    filesystem.chmod(str(path), 0o600)
    authenticator.config.dns_teo_credentials = str(path)
    authenticator._helper = None
    return path


def test_real_credentials_and_client_reuse(tmp_path, authenticator, monkeypatch):
    factory = Mock()
    monkeypatch.setattr("certbot_dns_teo.dns_teo.EdgeOneDNSClient", factory)
    path = write_credentials(
        tmp_path,
        authenticator,
        """
dns_teo_secret_id = id
dns_teo_secret_key = secret
dns_teo_token = session
""",
    )
    authenticator._setup_credentials()
    saved = authenticator._get_teo_client()
    authenticator._setup_credentials()
    assert authenticator._get_teo_client() is saved
    assert authenticator.credentials.conf("secret_id") == "id"
    assert authenticator.conf("credentials") == str(path)
    factory.assert_called_once_with("id", "secret", token="session")
    factory.return_value.list_zones.return_value = [
        Zone("zone-uk", "Example.co.uk."),
        Zone("zone-sub", "sub.example.co.uk"),
    ]
    assert saved._get_zone("_acme-challenge.sub.example.co.uk") == Zone(
        "zone-sub", "sub.example.co.uk"
    )
    factory.return_value.list_zones.assert_called_once()


def test_credentials_defaults(tmp_path, authenticator, monkeypatch):
    factory = Mock()
    monkeypatch.setattr("certbot_dns_teo.dns_teo.EdgeOneDNSClient", factory)
    write_credentials(
        tmp_path,
        authenticator,
        """
dns_teo_secret_id = id
dns_teo_secret_key = secret
""",
    )
    authenticator._setup_credentials()
    factory.assert_called_once_with("id", "secret", token=None)
    assert authenticator._helper._zones is None


@pytest.mark.parametrize(
    "text",
    [
        "",
        "dns_teo_secret_id=id",
        "dns_teo_secret_id=id\ndns_teo_secret_key=",
        "dns_teo_secret_id=\ndns_teo_secret_key=secret",
    ],
)
def test_invalid_credentials(tmp_path, authenticator, text):
    write_credentials(tmp_path, authenticator, text)
    with pytest.raises(errors.PluginError):
        authenticator._setup_credentials()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("dns_teo_ttl", 0),
        ("dns_teo_ttl", -1),
        ("dns_teo_ttl", 59),
        ("dns_teo_ttl", 86401),
        ("dns_teo_propagation_seconds", -1),
    ],
)
def test_invalid_options(authenticator, key, value):
    setattr(authenticator.config, key, value)
    with pytest.raises(errors.PluginError):
        authenticator._setup_credentials()


def test_unconfigured_authenticator(authenticator):
    authenticator._helper = None
    with pytest.raises(errors.PluginError, match="not been configured"):
        authenticator._perform("example.com", "_acme-challenge.example.com", "token")
    authenticator._cleanup("example.com", "_acme-challenge.example.com", "token")


def test_parser_defaults_and_plugin_info(authenticator):
    import argparse

    from certbot_dns_teo.dns_teo import Authenticator

    parser = argparse.ArgumentParser()

    def add(name, **kwargs):
        parser.add_argument("--" + name, **kwargs)

    Authenticator.add_parser_arguments(add)
    options = parser.parse_args([])
    assert options.propagation_seconds == 30
    assert options.ttl == 600
    assert options.credentials is None
    assert "TXT" in authenticator.more_info()


def test_invalid_idna_name():
    with pytest.raises(errors.PluginError, match="Invalid DNS"):
        _normalize_name("a" * 64 + ".com")


def test_ambiguous_zone_requires_explicit_id(helper):
    helper.client.list_zones.return_value = [
        Zone("zone-a", "example.com"),
        Zone("zone-b", "example.com"),
    ]
    with pytest.raises(errors.PluginError, match="Multiple.*dns_teo_zone_id"):
        helper.add_txt_record("_acme-challenge.example.com", "token")
    helper.client.create_txt_record.assert_not_called()
    helper.zone_id = "zone-b"
    helper.add_txt_record("_acme-challenge.example.com", "token")
    helper.client.create_txt_record.assert_called_once_with(
        "zone-b", "_acme-challenge.example.com", "token", 600
    )


@pytest.mark.parametrize("zone_id", ["zone-unknown", "zone-uk"])
def test_explicit_zone_must_exist_and_contain_name(helper, zone_id):
    helper.zone_id = zone_id
    with pytest.raises(errors.PluginError, match="No managed"):
        helper.add_txt_record("_acme-challenge.example.com", "token")
    helper.client.create_txt_record.assert_not_called()


def test_unicode_zone_and_record(helper):
    helper.client.list_zones.return_value = [Zone("zone-idn", "例子.公司.cn.")]
    helper.add_txt_record("_acme-challenge.例子.公司.cn.", "token")
    helper.client.create_txt_record.assert_called_once_with(
        "zone-idn", "_acme-challenge.xn--fsqu00a.xn--55qx5d.cn", "token", 600
    )


def test_zone_id_credentials(tmp_path, authenticator, monkeypatch):
    monkeypatch.setattr("certbot_dns_teo.dns_teo.EdgeOneDNSClient", Mock())
    write_credentials(
        tmp_path,
        authenticator,
        "dns_teo_secret_id=id\ndns_teo_secret_key=secret\ndns_teo_zone_id=zone-com",
    )
    authenticator._setup_credentials()
    assert authenticator._helper.zone_id == "zone-com"


@pytest.mark.parametrize("ttl", [60, 86400])
def test_valid_ttl_boundaries(tmp_path, authenticator, monkeypatch, ttl):
    monkeypatch.setattr("certbot_dns_teo.dns_teo.EdgeOneDNSClient", Mock())
    write_credentials(tmp_path, authenticator, "dns_teo_secret_id=id\ndns_teo_secret_key=secret")
    authenticator.config.dns_teo_ttl = ttl
    authenticator._setup_credentials()
    assert authenticator._helper.ttl == ttl
