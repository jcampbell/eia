import pytest

import os

from eia_client import Client, SortDirective, FacetDefinition

@pytest.fixture(scope="session")
def client() -> Client:
    return Client(api_key=os.environ["EIA_API_KEY"])


def test_data(client):
    series = "petroleum/pri/spt"
    frequency = "daily"
    data = ["value"]
    sort = [SortDirective(column="period", direction="asc")]
    facets = [
        FacetDefinition(id="duoarea", values=["Y35NY", "RGC"]),
        FacetDefinition(id="product", values=["EPMRU"]),
    ]
    start = "2020-01-01"
    end = "2020-01-31"
    df = client.get(
        series,
        frequency=frequency,
        data=data,
        sort=sort,
        facets=facets,
        start=start,
        end=end,
    )
    assert len(df) == 46
    assert df["duoarea"].unique().tolist() == ["Y35NY", "RGC"]
    assert df["product"].unique().tolist() == ["EPMRU"]


def test_dataset_info(client):
    info = client.dataset_info("petroleum")
    assert info.id == "petroleum"
    routes = [route.id for route in info.routes]
    assert "pri" in routes
    assert "cons" in routes


def test_invalid_dataset_info(client):
    with pytest.raises(ValueError) as e:
        client.dataset_info("petroleum/pri/spt")
    assert "Use series_info to get information about a series." in str(e.value)


def test_get_facet_info(client):
    info = client.series_info("petroleum/pri/spt")
    ids = list(info.facet_options.keys())
    assert len(ids) == 4
    assert "duoarea" in ids
    assert "Y35NY" in [option.id for option in info.facet_options["duoarea"]]


def test_error_info(client):
    series = "petroleum/pri/spt/data"
    # Quarterly is not a valid frequency for this series
    frequency="quarterly"
    data=["value"]
    facets=[FacetDefinition(id="duoarea", values=["Y35NY", "RGC"])]
    start="2020-01-01"
    end="2020-01-31"
    with pytest.raises(ValueError) as e:
        _ = client.get(
            series, 
            frequency=frequency, 
            data=data, 
            facets=facets, 
            start=start, 
            end=end
        )
    assert "Frequency quarterly not available for this dataset" in str(e.value)
