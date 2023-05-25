from typing import Dict, Literal, Union
import logging
from pydantic import BaseModel, ValidationError
import os

import pandas
from ratelimit import sleep_and_retry, limits
import requests

from eia.api_models import DatasetInfo, FacetOption, FrequencyType, SeriesInfo

logger = logging.getLogger(__name__)


class SortDirective(BaseModel):
    column: str
    direction: Literal["asc", "desc"] = "desc"


class FacetDefinition(BaseModel):
    id: str
    values: list[str]


class APIParams(BaseModel):
    frequency: FrequencyType
    data: list[str] = []
    facets: list[FacetDefinition] = []
    sort: list[SortDirective] = []
    offset: int = 0
    length: int = 5000
    start: Union[str, None] = None
    end: Union[str, None] = None

    @property
    def query_str(self) -> str:
        facets = []
        for facet in self.facets:
            for idx, val in enumerate(facet.values):
                if len(facet.values) == 1:
                    idx = ""
                facets.append(f"facets[{facet.id}][{idx}]={val}")
        facet_str = "&".join(facets)

        data_req = []
        for idx, val in enumerate(self.data):
            data_req.append(f"data[{idx}]={val}")
        data_str = "&".join(data_req)

        sort_strs = []
        for idx, sort_directive in enumerate(self.sort):
            sort_strs.append(
                f"sort[{idx}][column]={sort_directive.column}&sort[{idx}][direction]={sort_directive.direction}"
            )
        sort_str = "&".join(sort_strs)

        params_str = (
            f"frequency={self.frequency}&offset={self.offset}&length={self.length}"
        )

        if self.start:
            params_str += f"&start={self.start}"
        if self.end:
            params_str += f"&end={self.end}"

        if len(facet_str) > 0:
            params_str += f"&{facet_str}"

        if len(data_str) > 0:
            params_str += f"&{data_str}"

        if len(sort_str) > 0:
            params_str += f"&{sort_str}"

        return params_str


class SessionManager:
    def __init__(self):
        self._init_session()

    def _init_session(self):
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    @sleep_and_retry
    @limits(calls=20, period=60)
    @limits(calls=900, period=900)
    def get(self, *args, **kwargs) -> requests.Response:
        retries = 0
        while retries < 3:
            try:
                return self._session.get(*args, **kwargs)
            except requests.exceptions.ConnectionError:
                self._init_session()
                retries += 1
        raise requests.exceptions.ConnectionError(
            "Could not connect to EIA API after 3 retries"
        )


class Client:
    """Client for the EIA API.

    Simplifies the process of fetching data from the EIA API by adding typed
    parameters and returning a pandas DataFrame.
    """

    def __init__(self, api_key: Union[str, None] = None):
        """Initialize the client with an API key.

        Args:
            api_key (str, optional): API key to use for requests. If no API key is
                provided, the client will attempt to use the EIA_API_KEY
                environment variable.


        Raises:
            ValueError: If no API key is provided and the EIA_API_KEY environment
                variable is not set.
        """
        if api_key is None:
            api_key = os.getenv("EIA_API_KEY")
        if not api_key:
            raise ValueError("api_key is required to use the EIA API")
        self._api_key = api_key
        self._session = SessionManager()
        self._info: Dict[str, Union[DatasetInfo, SeriesInfo]] = dict()

    def _get_data(
        self, series: str, params: APIParams, show_warnings: bool = True
    ) -> pandas.DataFrame:
        if not series.endswith("/data"):
            series += "/data"
        query_str = "&".join([f"api_key={self._api_key}", params.query_str])
        res = self._session.get(f"https://api.eia.gov/v2/{series}/?{query_str}")
        try:
            res.raise_for_status()
            if (
                show_warnings
                and "warnings" in res.json()["response"]
                and len(res.json()["response"]["warnings"]) > 0
            ):
                logger.warning(res.json()["response"]["warnings"])
            return pandas.DataFrame(res.json()["response"]["data"])
        except requests.exceptions.HTTPError:
            raise requests.exceptions.HTTPError(
                f"Error fetching data from EIA API: {res.json()['error']}"
            )

    def _make_info_request(self, dataset: Union[str, None] = None) -> Dict:
        if dataset and dataset.endswith("/data"):
            raise ValueError(
                "Series must not end with '/data' to fetch route info; consider using"
                " get_data to get data instead."
            )
        if dataset and len(dataset) > 0:
            suffix = f"/{dataset}?api_key={self._api_key}"
        else:
            suffix = f"?api_key={self._api_key}"
        res = self._session.get(f"https://api.eia.gov/v2{suffix}")
        try:
            res.raise_for_status()
            data = res.json()
        except requests.exceptions.HTTPError:
            raise requests.exceptions.HTTPError(
                f"Error fetching data from EIA API: {res.json()['error']}"
            )
        return data

    def dataset_info(self, dataset: Union[str, None] = None) -> DatasetInfo:
        """Get information about a dataset, including available series
        or child datasets.

        Args:
            dataset (str, optional): The dataset to get information about. If
                no dataset is provided, the root dataset will be returned.

        Returns:
            DatasetInfo: Information about the dataset.
        """
        if dataset is None:
            dataset_key = "__root__"
        else:
            dataset_key = dataset

        if dataset_key in self._info:
            info = self._info[dataset_key]
            if not isinstance(info, DatasetInfo):
                raise ValueError(
                    f"{dataset} is a series, not a dataset. Use series_info to get"
                    " information about a series."
                )
            return info
        data = self._make_info_request(dataset)
        try:
            info = DatasetInfo.parse_obj(data["response"])
        except ValidationError as e:
            try:
                info = SeriesInfo.parse_obj(data["response"])
                raise ValueError(
                    f"{dataset} is a series, not a dataset. Use series_info to get"
                    " information about a series."
                )
            except ValidationError:
                raise e
        self._info[dataset_key] = info
        return info

    def series_info(self, series: str, get_facet_info: bool = True) -> SeriesInfo:
        """Get information about a series, including available facets and facet options.

        Args:
            series (str): The series to get information about.
            get_facet_info (bool, optional): Whether to fetch facet
                information. Defaults to True.

        Returns:
            SeriesInfo: Information about the series.
        """
        if series in self._info:
            info = self._info[series]
            assert isinstance(info, SeriesInfo)
            if not (info.facet_options is None and get_facet_info):
                return info

        data = self._make_info_request(series)
        series_info = SeriesInfo.parse_obj(data["response"])
        if get_facet_info:
            series_info.facet_options = dict()
            for facet in series_info.facets:
                series_info.facet_options[facet.id] = self._facet_info(series, facet.id)
        self._info[series] = series_info
        return series_info

    def _facet_info(self, series: str, facet: str) -> list[FacetOption]:
        res = self._session.get(
            f"https://api.eia.gov/v2/{series}/facet/{facet}?api_key={self._api_key}"
        )
        try:
            res.raise_for_status()
            data = res.json()
            return [
                FacetOption.parse_obj(facet) for facet in data["response"]["facets"]
            ]
        except requests.exceptions.HTTPError:
            raise requests.exceptions.HTTPError(
                f"Error fetching data from EIA API: {res.json()['error']}"
            )
        except ValidationError as e:
            logger.debug(f"full EIA response: {res.json()}")
            raise ValueError(f"Error parsing response from EIA API: {e}")

    def _build_api_params(
        self,
        info: SeriesInfo,
        frequency: FrequencyType,
        data: list[str],
        facets: list[FacetDefinition],
        sort: list[SortDirective],
        offset: int,
        length: int,
        start: Union[str, None],
        end: Union[str, None],
    ) -> APIParams:
        errors = []
        if frequency not in [frequency.id for frequency in info.frequency]:
            errors.append(
                ValueError(
                    f"Frequency {frequency} not available for this dataset. Available"
                    f" frequencies: {info.frequency}"
                )
            )
        for data_element in data:
            if data_element not in info.data:
                errors.append(
                    ValueError(
                        f"Data element {data_element} not available for this dataset."
                        f" Available data elements: {info.data}"
                    )
                )
        for facet in facets:
            if facet.id not in [available_facet.id for available_facet in info.facets]:
                errors.append(
                    ValueError(
                        f"Facet {facet.id} not available for this dataset. Available"
                        f" facets: {info.facets}"
                    )
                )
                continue
            if not info.facet_options:
                continue
            for value in facet.values:
                if value not in [option.id for option in info.facet_options[facet.id]]:
                    errors.append(
                        ValueError(
                            f"Facet value {value} not available for facet {facet.id}"
                        )
                    )
        if offset < 0:
            errors.append(ValueError("Offset must be non-negative"))

        if length < 0 or length > 5000:
            errors.append(ValueError("Length must be between 0 and 5000"))

        # Note: we cannot validate sort using the info object, because the
        # API does not return sort information
        # TODO: Validate start and end dates
        if len(errors) > 0:
            raise ValueError("\n".join([str(error) for error in errors]))
        return APIParams(
            frequency=frequency,
            data=data,
            facets=facets,
            sort=sort,
            offset=offset,
            length=length,
            start=start,
            end=end,
        )

    def get(
        self,
        series: str,
        data: list[str],
        frequency: Union[FrequencyType, None] = None,
        facets: Union[list[FacetDefinition], Dict[str, list[str]], None] = None,
        sort: Union[list[SortDirective], Dict[str, str], None] = None,
        offset: int = 0,
        length: Union[int, None] = None,
        start: Union[str, None] = None,
        end: Union[str, None] = None,
    ) -> pandas.DataFrame:
        """Get data from the EIA API for a named data series.

        Args:
            series (str): The name of the series to fetch data for.
            data (list[str]): The data elements to fetch.
            frequency (FrequencyType, optional): The frequency of the data to fetch.
                If not specified, uses the default frequency.
            facets (list[FacetDefinition], optional): The facets to fetch. If not
                specified, fetches all facets.
            sort (list[SortDirective], optional): The sort directives to use. If not
                specified, uses the default sort order.
            offset (int, optional): The offset to use when fetching data.
                Defaults to 0.
            length (int, optional): The number of data points to fetch.
                Defaults to None, which will fetch all available data.
            start (str, optional): The start date to fetch data for. Defaults to None.
            end (str, optional): The end date to fetch data for. Defaults to None.

        Returns:
            pandas.DataFrame: A dataframe containing the requested data.

        Raises:
            ValueError: If any of the arguments are invalid for the given series.
            ValidationError: If the response from the EIA API is unrecognized.
        """
        if series.endswith("/data"):
            logger.debug(
                "Removing /data from series name to obtain series info. Do not use the"
                " /data suffix for getting data using this client."
            )
            series = series[:-5]
        info = self.series_info(series, get_facet_info=False)
        if frequency is None:
            frequency = info.defaultFrequency
        if facets is None:
            facets = []
        if sort is None:
            sort = []
        if isinstance(facets, dict):
            facet_list = []
            for key, value in facets.items():
                facet_list.append(
                    FacetDefinition.parse_obj({"id": key, "values": value})
                )
            facets = facet_list
        for sort_directive in sort:
            if isinstance(sort_directive, dict):
                sort_directive = SortDirective.parse_obj(sort_directive)

        if length is None:
            length = 5000
        check_for_more_results = True
        dfs = []
        while check_for_more_results:
            logger.info(f"Fetching data for {series} with offset {offset}")
            params = self._build_api_params(
                info,
                frequency,
                data,
                facets,
                sort,  # type: ignore
                offset,
                length,
                start,
                end,
            )
            df = self._get_data(series, params=params, show_warnings=False)
            if len(df) < length:
                check_for_more_results = False
            else:
                offset += len(df)
            dfs.append(df)

        return pandas.concat(dfs)
