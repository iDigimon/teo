"""Retain real EdgeOne SDK DTOs, replacing only the network boundary."""

import json
import traceback
from unittest.mock import Mock

import pytest
from certbot import errors
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.teo.v20220901 import models

from certbot_dns_teo.teo_client import EdgeOneDNSClient, Zone

NAME = "_acme-challenge.example.com"


def dto(cls, data):
    result = cls()
    result.from_json_string(json.dumps(data))
    return result


def zone(id_, name="example.com", type_="full", status="active"):
    return {"ZoneId": id_, "ZoneName": name, "Type": type_, "Status": status}


def zones(items, total):
    return dto(models.DescribeZonesResponse, {"TotalCount": total, "Zones": items})


def record(id_, **changes):
    result = {
        "ZoneId": "zone-com",
        "RecordId": id_,
        "Name": NAME,
        "Type": "TXT",
        "Content": "token",
        "Location": "Default",
        "Status": "enable",
        "TTL": 600,
    }
    result.update(changes)
    return result


def records(items, total):
    return dto(models.DescribeDnsRecordsResponse, {"TotalCount": total, "DnsRecords": items})


def request_map(request):
    return {
        key: value
        for key, value in json.loads(request.to_json_string()).items()
        if value is not None
    }


def test_sdk_credentials_endpoint_timeout_and_no_retries(monkeypatch):
    factory = Mock()
    monkeypatch.setattr("certbot_dns_teo.teo_client.teo_client.TeoClient", factory)
    EdgeOneDNSClient("id", "secret", token="session")
    credentials, region, profile = factory.call_args.args
    assert credentials.secret_id == "id"
    assert credentials.secret_key == "secret"
    assert credentials.token == "session"
    assert region == ""
    assert profile.httpProfile.endpoint == "teo.tencentcloudapi.com"
    assert profile.httpProfile.reqTimeout == 30
    assert profile.retryer is None
    assert profile.disable_region_breaker is True


def test_all_zone_pages(client):
    call = client.client.DescribeZones
    call.side_effect = [
        zones([zone("zone-com"), zone("zone-uk", "example.co.uk")], 3),
        zones([zone("zone-sub", "sub.example.co.uk")], 3),
    ]
    assert client.list_zones() == [
        Zone("zone-com", "example.com"),
        Zone("zone-uk", "example.co.uk"),
        Zone("zone-sub", "sub.example.co.uk"),
    ]
    for offset, item in zip([0, 2], call.call_args_list):
        assert request_map(item.args[0]) == {
            "Offset": offset,
            "Limit": 2,
            "Filters": [
                {"Name": "zone-type", "Values": ["full"], "Fuzzy": False},
                {"Name": "status", "Values": ["active"], "Fuzzy": False},
            ],
        }


@pytest.mark.parametrize(
    "item",
    [
        zone("id", type_="partial"),
        zone("id", status="pending"),
        zone("id", type_="dnsPodAccess"),
        zone("id", status="moved"),
    ],
)
def test_non_authoritative_zones_ignored(client, item):
    client.client.DescribeZones.return_value = zones([item], 1)
    assert client.list_zones() == []


@pytest.mark.parametrize("item", [zone(None), zone("id", name=None)])
def test_malformed_zone_fails(client, item):
    client.client.DescribeZones.return_value = zones([item], 1)
    with pytest.raises(errors.PluginError, match="invalid zone"):
        client.list_zones()


def test_all_record_pages_and_exact_name_filter(client):
    call = client.client.DescribeDnsRecords
    call.side_effect = [
        records([record("r-1"), record("r-2", Name="other." + NAME)], 3),
        records([record("r-3", Content="second-value")], 3),
    ]
    assert client.get_records("zone-com", NAME) == [
        {"record_id": "r-1", "value": "token"},
        {"record_id": "r-3", "value": "second-value"},
    ]
    assert request_map(call.call_args.args[0]) == {
        "ZoneId": "zone-com",
        "Offset": 2,
        "Limit": 2,
        "Match": "all",
        "Filters": [
            {"Name": "name", "Values": [NAME], "Fuzzy": False},
            {"Name": "type", "Values": ["TXT"], "Fuzzy": False},
        ],
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"Status": "disable"},
        {"Type": "CNAME"},
        {"Location": "CN.BJ"},
        {"ZoneId": "other-zone"},
        {"Name": None},
        {"Name": NAME + ".other.com"},
    ],
)
def test_unusable_records_not_reused(client, changes):
    client.client.DescribeDnsRecords.return_value = records([record("r-1", **changes)], 1)
    assert client.get_records("zone-com", NAME) == []


def test_name_case_and_trailing_dot(client):
    client.client.DescribeDnsRecords.return_value = records(
        [record("r-1", Name=NAME.upper() + ".")], 1
    )
    assert len(client.get_records("zone-com", NAME)) == 1


@pytest.mark.parametrize("changes", [{"RecordId": None}, {"Content": None}])
def test_malformed_record_fails(client, changes):
    client.client.DescribeDnsRecords.return_value = records([record("r-1", **changes)], 1)
    with pytest.raises(errors.PluginError, match="invalid DNS record"):
        client.get_records("zone-com", NAME)


def test_empty_lists(client):
    client.client.DescribeZones.return_value = zones([], 0)
    client.client.DescribeDnsRecords.return_value = records([], 0)
    assert client.list_zones() == []
    assert client.get_records("zone-com", NAME) == []


@pytest.mark.parametrize("kind", ["zones", "records"])
@pytest.mark.parametrize("total", [10, None, -1])
def test_incomplete_pagination_fails(client, kind, total):
    if kind == "zones":
        client.client.DescribeZones.return_value = zones([], total)
        operation = client.list_zones
    else:
        client.client.DescribeDnsRecords.return_value = records([], total)

        def operation():
            return client.get_records("zone-com", NAME)

    with pytest.raises(errors.PluginError, match="incomplete"):
        operation()


@pytest.mark.parametrize("kind", ["zones", "records"])
def test_later_empty_page_fails(client, kind):
    if kind == "zones":
        client.client.DescribeZones.side_effect = [zones([zone("zone-com")], 2), zones([], 2)]
        operation = client.list_zones
    else:
        client.client.DescribeDnsRecords.side_effect = [records([record("r-1")], 2), records([], 2)]

        def operation():
            return client.get_records("zone-com", NAME)

    with pytest.raises(errors.PluginError, match="incomplete"):
        operation()


def test_create_independent_txt_with_fqdn(client):
    call = client.client.CreateDnsRecord
    call.return_value = dto(models.CreateDnsRecordResponse, {"RecordId": "record-created"})
    assert client.create_txt_record("zone-com", NAME, "token", 60) == "record-created"
    assert request_map(call.call_args.args[0]) == {
        "ZoneId": "zone-com",
        "Name": NAME,
        "Type": "TXT",
        "Content": "token",
        "TTL": 60,
    }


def test_create_without_id_fails(client):
    client.client.CreateDnsRecord.return_value = models.CreateDnsRecordResponse()
    with pytest.raises(errors.PluginError, match="new record ID"):
        client.create_txt_record("zone-com", NAME, "token")


def test_delete_uses_string_id_and_saved_zone(client):
    call = client.client.DeleteDnsRecords
    call.return_value = models.DeleteDnsRecordsResponse()
    client.delete_record("zone-com", "record-owned")
    assert request_map(call.call_args.args[0]) == {
        "ZoneId": "zone-com",
        "RecordIds": ["record-owned"],
    }
    client.client.DescribeDnsRecords.assert_not_called()


@pytest.mark.parametrize(
    "operation", ["DescribeZones", "DescribeDnsRecords", "CreateDnsRecord", "DeleteDnsRecords"]
)
@pytest.mark.parametrize(
    "code", ["UnauthorizedOperation.CamUnauthorized", "ResourceNotFound", "InternalError"]
)
def test_cloud_errors_sanitized_and_not_swallowed(client, operation, code):
    getattr(client.client, operation).side_effect = TencentCloudSDKException(
        code, "sensitive-token"
    )
    with pytest.raises(errors.PluginError, match=code) as caught:
        client._call(operation, object())
    assert "sensitive-token" not in str(caught.value)
    assert "sensitive-token" not in "".join(
        traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__)
    )
    getattr(client.client, operation).assert_called_once()


def test_network_error_sanitized(client):
    client.client.DescribeZones.side_effect = OSError("sensitive-request")
    with pytest.raises(errors.PluginError, match="network error") as caught:
        client.list_zones()
    assert "sensitive-request" not in "".join(
        traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__)
    )


def test_empty_response_fails(client):
    client.client.DescribeZones.return_value = None
    with pytest.raises(errors.PluginError, match="empty response"):
        client.list_zones()
