from typing import Dict, Literal

from pydantic import BaseModel


FrequencyType = Literal[
    "local-hourly", "hourly", "daily", "weekly", "monthly", "quarterly", "annual"
]


class FrequencyInfo(BaseModel):
    id: FrequencyType
    description: str
    query: Literal["LH", "H", "D", "W", "M", "Q", "A"]
    format: str


class FacetOption(BaseModel):
    id: str
    name: str
    alias: str | None


class FacetInfo(BaseModel):
    id: str
    description: str


class DataInfo(BaseModel):
    alias: str | None
    units: str | None


class SeriesInfo(BaseModel):
    id: str
    description: str
    frequency: list[FrequencyInfo]
    facets: list[FacetInfo]
    facet_options: Dict[str, list[FacetOption]] | None
    data: Dict[str, DataInfo]
    startPeriod: str
    endPeriod: str
    defaultDateFormat: str
    defaultFrequency: FrequencyType


class RouteInfo(BaseModel):
    id: str
    name: str
    description: str | None


class DatasetInfo(BaseModel):
    id: str
    name: str
    description: str
    routes: list[RouteInfo]
