"""Use real plugin configuration and mock only the external SDK boundary."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from certbot_dns_teo.dns_teo import Authenticator, _EdgeOneDNSHelper
from certbot_dns_teo.teo_client import EdgeOneDNSClient, Zone


@pytest.fixture
def client(monkeypatch):
    sdk = Mock()
    monkeypatch.setattr("certbot_dns_teo.teo_client.teo_client.TeoClient", Mock(return_value=sdk))
    result = EdgeOneDNSClient("id", "secret", token="session")
    result.page_size = 2
    return result


@pytest.fixture
def helper(monkeypatch):
    cloud = Mock(spec=EdgeOneDNSClient)
    cloud.list_zones.return_value = [
        Zone("zone-com", "example.com"),
        Zone("zone-uk", "example.co.uk"),
        Zone("zone-sub", "sub.example.co.uk"),
    ]
    cloud.get_records.return_value = []
    cloud.create_txt_record.side_effect = ["101", "102", "103"]
    monkeypatch.setattr("certbot_dns_teo.dns_teo.EdgeOneDNSClient", Mock(return_value=cloud))
    return _EdgeOneDNSHelper("id", "secret", 600)


@pytest.fixture
def authenticator(helper):
    config = SimpleNamespace(
        dns_teo_credentials=None,
        dns_teo_ttl=600,
        dns_teo_propagation_seconds=0,
        noninteractive_mode=True,
    )
    result = Authenticator(config, "dns-teo")
    result._helper = helper
    return result
