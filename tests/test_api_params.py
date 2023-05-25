from eia.client import APIParams, FacetDefinition, SortDirective


def test_api_params():
    params = APIParams(
        frequency="weekly",
    )
    assert params.query_str == "frequency=weekly&offset=0&length=5000"

    params = APIParams(
        frequency="weekly",
        data=["price", "volume"],
        sort=[
            SortDirective(column="date", direction="desc"),
            SortDirective(column="stateid", direction="asc"),
        ],
        facets=[FacetDefinition(id="stateid", values=["AK", "AL"])],
        offset=10,
        length=100,
        start="2020-01-01",
        end="2020-01-31",
    )
    assert (
        params.query_str
        == "frequency=weekly&offset=10&length=100&start=2020-01-01&end=2020-01-31"
        "&facets[stateid][0]=AK&facets[stateid][1]=AL&data[0]=price&data[1]=volume"
        "&sort[0][column]=date&sort[0][direction]=desc&sort[1][column]=stateid&"
        "sort[1][direction]=asc"
    )
