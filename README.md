# eia-client

The client exposes a simple interface to the EIA API.

## Installation

```bash
pip install eia-client
```

## Examples

Get information on the available "petroleum" datasets.

```python
client.dataset_info("petroleum")
```

Get information on operational and power data, including generation.
```python
# Series Info includes data series with specific data elements and facets
operational = client.series_info("electricity/electric-power-operational-data")
operational.data
```

See examples in the [examples](examples) directory.

Note: the client does not manage rate limits. See the [EIA API documentation](https://www.eia.gov/opendata/qb.php?category=371) for more information.