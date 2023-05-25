from typing import List, Dict
import pytest
from unittest.mock import MagicMock

import urllib.parse

import requests

from eia import Client
from eia.api_models import DataInfo, DatasetInfo, FacetInfo, FrequencyInfo, SeriesInfo


def mock_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data: Dict, status_code: int):
            self.json_data = json_data
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code != 200:
                raise requests.HTTPError("failed raise for status")

        def json(self):
            return self.json_data

    parsed = urllib.parse.urlparse(args[0])
    path = parsed.path
    if path == "/v2/test_series":
        return MockResponse(
            {
                "response": SeriesInfo(
                    id="test_series",
                    description="Test Series",
                    frequency=[
                        FrequencyInfo(
                            id="weekly",
                            description="Weekly",
                            query="W",
                            format="YYYY-MM-DD",
                        )
                    ],
                    facets=[FacetInfo(id="facetid", description="basic_facet")],
                    facet_options=None,
                    data={"value": DataInfo(alias=None, units=None)},
                    startPeriod="2023-05-24",
                    endPeriod="2023-05-24",
                    defaultDateFormat="YYYY-MM-DD",
                    defaultFrequency="weekly",
                ).dict()
            },
            200,
        )

    elif path == "/v2/test_series/facet/facetid":
        return MockResponse(
            {"response": {"facets": [{"id": "facetid", "name": "test_facet"}]}}, 200
        )

    elif path == "/v2/test_series/data/":
        return MockResponse({"response": {"data": []}}, 200)

    elif path == "/v2/test_dataset":
        return MockResponse(
            {
                "response": DatasetInfo(
                    id="test_dataset",
                    name="test_dataset",
                    description="test_dataset",
                    routes=[],
                ).dict()
            },
            200,
        )

    else:
        return MockResponse({"response": [], "error": "unrecognized path"}, 404)


@pytest.fixture
def mock_client():
    client = Client()
    client._session.get = MagicMock(side_effect=mock_get)
    return client


def _get_request_path(*, args: List[str], kwargs: Dict[str, str]) -> str:
    if "url" in kwargs:
        url = kwargs["url"]
    else:
        url = args[0]
    parsed = urllib.parse.urlparse(url)
    return parsed.path


def test_get_data_no_fetch_facets(mock_client):
    client = mock_client
    client.get("test_series", frequency="weekly", data=["value"])
    paths_requested = [
        _get_request_path(args=call_info[0], kwargs=call_info[1])
        for call_info in client._session.get.call_args_list
    ]
    assert len(paths_requested) == 2
    assert "/v2/test_series" in paths_requested
    assert "/v2/test_series/facets/facetid" not in paths_requested
    assert "/v2/test_series/data/" in paths_requested


def test_get_series_info_fetch_facets(mock_client):
    client = mock_client
    client.series_info("test_series")
    paths_requested = [
        _get_request_path(args=call_info[0], kwargs=call_info[1])
        for call_info in client._session.get.call_args_list
    ]
    assert len(paths_requested) == 2
    assert "/v2/test_series" in paths_requested
    assert "/v2/test_series/facet/facetid" in paths_requested


def test_invalid_path(mock_client):
    client = mock_client
    with pytest.raises(requests.HTTPError) as e:
        client.get("invalid_path", frequency="weekly", data=["value"])
    assert "unrecognized path" in str(e.value)
