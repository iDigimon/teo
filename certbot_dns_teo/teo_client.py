"""Tencent Cloud EdgeOne API v20220901 adapter using the official SDK."""

from dataclasses import dataclass
from typing import Any, Optional

from certbot import errors
from tencentcloud.common.credential import Credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.teo.v20220901 import models, teo_client


@dataclass(frozen=True)
class Zone:
    id: str
    name: str


class EdgeOneDNSClient:
    """Manage individual records without replacing existing TXT RRsets."""

    page_size = 100

    def __init__(self, secret_id: str, secret_key: str, *, token: Optional[str] = None) -> None:
        http = HttpProfile(endpoint="teo.tencentcloudapi.com", reqTimeout=30)
        # retryer=None uses NoopRetryer: do not retry ambiguous writes.
        self.client = teo_client.TeoClient(
            Credential(secret_id, secret_key, token), "", ClientProfile(httpProfile=http)
        )

    def _call(self, operation: str, request: Any) -> Any:
        try:
            response = getattr(self.client, operation)(request)
        except TencentCloudSDKException as exc:
            # Provider messages may contain credentials or TXT content.
            raise errors.PluginError(
                f"Tencent EdgeOne {operation} failed ({exc.get_code()})"
            ) from None
        except OSError:
            raise errors.PluginError(
                f"Tencent EdgeOne {operation} failed (network error)"
            ) from None
        if response is None:
            raise errors.PluginError(f"Tencent EdgeOne {operation} returned an empty response")
        return response

    @staticmethod
    def _filter(name: str, value: str) -> models.AdvancedFilter:
        result = models.AdvancedFilter()
        result.Name = name
        result.Values = [value]
        result.Fuzzy = False
        return result

    @staticmethod
    def _page_complete(offset: int, count: int, total: Optional[int], kind: str) -> bool:
        if total is None or total < offset or (count == 0 and offset < total):
            raise errors.PluginError(f"Tencent EdgeOne returned an incomplete {kind} list")
        return offset == total

    def list_zones(self) -> list[Zone]:
        """Return active NS zones, reading all pages before selecting a site."""
        zones = []
        offset = 0
        while True:
            request = models.DescribeZonesRequest()
            request.Offset = offset
            request.Limit = self.page_size
            request.Filters = [self._filter("zone-type", "full"), self._filter("status", "active")]
            body = self._call("DescribeZones", request)
            items = body.Zones or []
            for item in items:
                # Validate locally too, rather than trusting server-side filters.
                if item.Type != "full" or item.Status != "active":
                    continue
                if not item.ZoneId or not item.ZoneName:
                    raise errors.PluginError("Tencent EdgeOne returned an invalid zone")
                zones.append(Zone(item.ZoneId, item.ZoneName))
            offset += len(items)
            if self._page_complete(offset, len(items), body.TotalCount, "zone"):
                return zones

    def get_records(self, zone_id: str, name: str) -> list[dict[str, str]]:
        """Return exact enabled TXT records; Name is a fully qualified DNS name."""
        records = []
        offset = 0
        while True:
            request = models.DescribeDnsRecordsRequest()
            request.ZoneId = zone_id
            request.Offset = offset
            request.Limit = self.page_size
            request.Filters = [self._filter("name", name), self._filter("type", "TXT")]
            request.Match = "all"
            body = self._call("DescribeDnsRecords", request)
            items = body.DnsRecords or []
            for item in items:
                if (
                    item.Type == "TXT"
                    and (item.Name or "").rstrip(".").lower() == name.rstrip(".").lower()
                    and item.Status == "enable"
                    and item.Location == "Default"
                    and item.ZoneId == zone_id
                ):
                    if not item.RecordId or item.Content is None:
                        raise errors.PluginError("Tencent EdgeOne returned an invalid DNS record")
                    records.append({"record_id": item.RecordId, "value": item.Content})
            offset += len(items)
            if self._page_complete(offset, len(items), body.TotalCount, "record"):
                return records

    def create_txt_record(self, zone_id: str, name: str, value: str, ttl: int = 600) -> str:
        request = models.CreateDnsRecordRequest()
        request.ZoneId = zone_id
        request.Name = name
        request.Type = "TXT"
        request.Content = value
        request.TTL = ttl
        # Location/Weight are only configurable for A/AAAA/CNAME. TXT uses defaults.
        body = self._call("CreateDnsRecord", request)
        if not body.RecordId:
            raise errors.PluginError("Tencent EdgeOne did not return a new record ID")
        return body.RecordId

    def delete_record(self, zone_id: str, record_id: str) -> None:
        request = models.DeleteDnsRecordsRequest()
        request.ZoneId = zone_id
        request.RecordIds = [record_id]
        self._call("DeleteDnsRecords", request)
