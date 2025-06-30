import urllib.parse
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional, Type, TypeVar, Union

import httpx
from autogen_core import CancellationToken, Component
from autogen_core.tools import BaseTool as BaseCoreTool
from pydantic import BaseModel, Field


class Config(BaseModel):
    """Base configuration for all Prometheus tools"""

    description: Optional[str] = Field(default="Prometheus monitoring tool", description="A description of the tool")
    base_url: str = Field(default="http://localhost:9090/api/v1", description="The base URL of the Prometheus API")
    username: str = Field(default="", description="Username for basic auth")
    password: str = Field(default="", description="Password for basic auth")


def _format_time(time: Union[datetime, float]) -> str:
    """Format time as a string"""
    if isinstance(time, datetime):
        return time.isoformat()
    else:
        return str(time)


def get_http_client(config: Config, cancellation_token: CancellationToken) -> httpx.AsyncClient:
    """Create an HTTP client for the API"""
    if config.username and config.password:
        auth = httpx.BasicAuth(config.username, config.password)
        return httpx.AsyncClient(base_url=config.base_url, auth=auth)
    else:
        return httpx.AsyncClient(base_url=config.base_url)


ArgsT = TypeVar("ArgsT", bound=BaseModel, contravariant=True)


class BaseTool(BaseCoreTool[ArgsT, BaseModel], Component[Config]):
    """Base class for all Prometheus tools"""

    component_type = "tool"
    component_config_schema = Config

    @property
    def component_provider_override(self) -> str:
        """Build the component provider path from the class name"""
        return f"kagent.tools.prometheus.{self.__class__.__name__}"

    def __init__(
        self,
        config: Config,
        input_model: Type[ArgsT],
        description: str,
    ) -> None:
        super().__init__(input_model, BaseModel, self.__class__.__name__, description)
        self.config = config

    def _to_config(self) -> Config:
        """Convert to config object"""
        return self.config.model_copy()

    @classmethod
    def _from_config(cls, config: Config) -> "BaseTool":
        """Create instance from config"""
        raise NotImplementedError("Use specific tool implementations")


class QueryInput(BaseModel):
    query: str = Field(description="Prometheus expression query string")
    time: Optional[Union[datetime, float]] = Field(
        default=None, description="Evaluation timestamp in RFC3339 or unix timestamp format"
    )
    timeout: Optional[str] = Field(default=None, description="Evaluation timeout")


class QueryTool(BaseTool):
    """Tool for executing instant Prometheus queries"""

    _description = """Executes instant queries against Prometheus to retrieve current metric values.
        Use this tool when you need to get the latest values of metrics or perform calculations on current data.
        The query must be a valid PromQL expression."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=QueryInput, description=self._description)

    async def run(self, args: QueryInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            params = {"query": args.query}
            response = await client.get("/query", params=params)
            return response.json()

    @classmethod
    def _from_config(cls, config: Config) -> "QueryTool":
        return cls(config)


class QueryRangeInput(BaseModel):
    query: str = Field(description="Prometheus expression query string")
    start: Union[datetime, float] = Field(description="Start timestamp")
    end: Union[datetime, float] = Field(description="End timestamp")
    step: Union[str, float] = Field(description="Query resolution step width")
    timeout: Optional[str] = Field(default=None, description="Evaluation timeout")


class QueryRangeTool(BaseTool):
    """Tool for executing range queries in Prometheus"""

    _description = """Executes time series queries over a specified time range in Prometheus.
        Use this tool for analyzing metric patterns, trends, and historical data.
        You can specify the time range, resolution (step), and timeout for the query."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=QueryRangeInput, description=self._description)

    async def run(self, args: QueryRangeInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            params = {
                "query": args.query,
                "start": _format_time(args.start) if args.start else None,
                "end": _format_time(args.end) if args.end else None,
                "step": str(args.step),
                "timeout": args.timeout,
            }
            response = await client.get("/query_range", params=params)
            return response.json()

    @classmethod
    def _from_config(cls, config: Config) -> "QueryRangeTool":
        return cls(config)


class SeriesInput(BaseModel):
    match: List[str] = Field(description="Series selector arguments")
    start: Optional[Union[datetime, float]] = Field(default=None, description="Start timestamp")
    end: Optional[Union[datetime, float]] = Field(default=None, description="End timestamp")
    limit: Optional[int] = Field(default=1000, description="Maximum number of returned items")


class SeriesQueryTool(BaseTool):
    """Tool for querying Prometheus series"""

    _description = """Finds time series that match certain label selectors in Prometheus.
        Use this tool to discover which metrics exist and their label combinations.
        You can specify time ranges to limit the search scope and set a maximum number of results."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=SeriesInput, description=self._description)

    async def run(self, args: SeriesInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            params = {
                "match[]": args.match,
                "start": _format_time(args.start) if args.start else None,
                "end": _format_time(args.end) if args.end else None,
                "limit": args.limit,
            }
            result = await client.get("/series", params=params)
            return result.json().get("data", [])

    @classmethod
    def _from_config(cls, config: Config) -> "SeriesQueryTool":
        return cls(config)


class LabelNamesInput(BaseModel):
    start: Optional[Union[datetime, float]] = Field(default=None, description="Start timestamp")
    end: Optional[Union[datetime, float]] = Field(default=None, description="End timestamp")
    match: Optional[List[str]] = Field(default=None, description="Series selector")
    limit: Optional[int] = Field(default=1000, description="Maximum number of returned items")


class LabelNamesTool(BaseTool):
    """Tool for getting Prometheus label names"""

    _description = """Retrieves all label names that are available in the Prometheus server.
        Use this tool to discover what dimensions are available for querying and filtering metrics.
        You can optionally filter by time range and series selectors."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=LabelNamesInput, description=self._description)

    async def run(self, args: LabelNamesInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            params = {
                "start": _format_time(args.start) if args.start else None,
                "end": _format_time(args.end) if args.end else None,
                "match[]": args.match,
                "limit": args.limit,
            }
            result = await client.get("/labels", params=params)
            return result.json().get("data", [])

    @classmethod
    def _from_config(cls, config: Config) -> "LabelNamesTool":
        return cls(config)


class LabelValuesInput(BaseModel):
    label_name: str = Field(description="Label name")
    start: Optional[Union[datetime, float]] = Field(default=None, description="Start timestamp")
    end: Optional[Union[datetime, float]] = Field(default=None, description="End timestamp")
    match: Optional[List[str]] = Field(default=None, description="Series selector")
    limit: Optional[int] = Field(default=1000, description="Maximum number of returned items")


class LabelValuesTool(BaseTool):
    """Tool for getting Prometheus label values"""

    _description = """Retrieves all possible values for a specific label name in Prometheus.
        Use this tool to understand the range of values a particular label can have.
        You can filter by time range and series selectors to narrow down the results."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=LabelValuesInput, description=self._description)

    async def run(self, args: LabelValuesInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            encoded_label = urllib.parse.quote(args.label_name)
            params = {
                "start": _format_time(args.start) if args.start else None,
                "end": _format_time(args.end) if args.end else None,
                "match[]": args.match,
                "limit": args.limit,
            }
            result = await client.get(f"/label/{encoded_label}/values", params=params)
            return result.json().get("data", [])

    @classmethod
    def _from_config(cls, config: Config) -> "LabelValuesTool":
        return cls(config)


class TargetsInput(BaseModel):
    state: Optional[str] = Field(default=None, description="Target state filter, must be one of: active, dropped, any")
    scrape_pool: Optional[str] = Field(default=None, description="Scrape pool name")


class TargetsTool(BaseTool):
    """Tool for getting Prometheus target discovery state"""

    _description = """Provides information about all Prometheus scrape targets and their current state.
        Use this tool to monitor which targets are being scraped successfully and which are failing.
        You can filter targets by state (active/dropped) and scrape pool."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=TargetsInput, description=self._description)

    async def run(self, args: TargetsInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            params = {
                "state": args.state.value if args.state else None,
                "scrape_pool": args.scrape_pool,
            }
            response = await client.get("/targets", params=params)
            return response.json()

    @classmethod
    def _from_config(cls, config: Config) -> "TargetsTool":
        return cls(config)


class RulesInput(BaseModel):
    type: Optional[str] = Field(default=None, description="Rule type filter")
    rule_name: Optional[List[str]] = Field(default=None, description="Rule names filter")
    rule_group: Optional[List[str]] = Field(default=None, description="Rule group names filter")
    file: Optional[List[str]] = Field(default=None, description="File paths filter")
    exclude_alerts: Optional[bool] = Field(default=None, description="Exclude alerts flag")
    match: Optional[List[str]] = Field(default=None, description="Label selectors")
    group_limit: Optional[int] = Field(default=None, description="Group limit")
    group_next_token: Optional[str] = Field(default=None, description="Pagination token")


class RulesTool(BaseTool):
    """Tool for getting Prometheus alerting and recording rules"""

    _description = """Retrieves information about configured alerting and recording rules in Prometheus.
        Use this tool to understand what alerts are defined and what metrics are being pre-computed.
        You can filter rules by type, name, group, and other criteria."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=RulesInput, description=self._description)

    async def run(self, args: RulesInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            params = {
                "type": args.type,
                "rule_name[]": args.rule_name,
                "rule_group[]": args.rule_group,
                "file[]": args.file,
                "exclude_alerts": "true" if args.exclude_alerts else None,
                "match[]": args.match,
                "group_limit": args.group_limit,
                "group_next_token": args.group_next_token,
            }
            response = await client.get("/rules", params=params)
            return response.json()

    @classmethod
    def _from_config(cls, config: Config) -> "RulesTool":
        return cls(config)


class AlertsInput(BaseModel):
    """Empty input model for alerts endpoint"""

    pass


class AlertsTool(BaseTool):
    """Tool for getting active Prometheus alerts"""

    _description = """Retrieves all currently firing alerts in the Prometheus server.
        Use this tool to monitor the current alert state and identify ongoing issues.
        Returns details about alert names, labels, and when they started firing."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=AlertsInput, description=self._description)

    async def run(self, args: AlertsInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            response = await client.get("/alerts")
            return response.json()

    @classmethod
    def _from_config(cls, config: Config) -> "AlertsTool":
        return cls(config)


class TargetMetadataInput(BaseModel):
    match_target: Optional[str] = Field(default=None, description="Target label selectors")
    metric: Optional[str] = Field(default=None, description="Metric name")
    limit: Optional[int] = Field(default=None, description="Maximum number of targets")


class TargetMetadataTool(BaseTool):
    """Tool for getting Prometheus target metadata"""

    _description = """Retrieves metadata about metrics exposed by specific Prometheus targets.
        Use this tool to understand metric types, help texts, and units.
        You can filter by target labels and specific metric names."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=TargetMetadataInput, description=self._description)

    async def run(self, args: TargetMetadataInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            params = {
                "match_target": args.match_target,
                "metric": args.metric,
                "limit": args.limit,
            }
            result = await client.get("/targets/metadata", params=params)
            return result.json().get("data", [])

    @classmethod
    def _from_config(cls, config: Config) -> "TargetMetadataTool":
        return cls(config)


class AlertmanagersInput(BaseModel):
    pass


class AlertmanagersTool(BaseTool):
    """Tool for getting Prometheus alertmanager discovery state"""

    _description = """Provides information about the Alertmanager instances known to Prometheus.
        Use this tool to verify the connection status between Prometheus and its Alertmanagers.
        Shows both active and dropped Alertmanager instances."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=AlertmanagersInput, description=self._description)

    async def run(self, args: AlertmanagersInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            response = await client.get("/alertmanagers")
            return response.json()

    @classmethod
    def _from_config(cls, config: Config) -> "AlertmanagersTool":
        return cls(config)


class MetadataInput(BaseModel):
    metric: Optional[str] = Field(default=None, description="Metric name")
    limit: Optional[int] = Field(default=None, description="Maximum number of metrics")
    limit_per_metric: Optional[int] = Field(default=None, description="Maximum entries per metric")


class MetadataTool(BaseTool):
    """Tool for getting Prometheus metric metadata"""

    _description = """Retrieves metadata for Prometheus metrics including help text and type information.
        Use this tool to understand what metrics mean and how they should be interpreted.
        You can filter by specific metric names and set limits on the number of results."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=MetadataInput, description=self._description)

    async def run(self, args: MetadataInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            params = {
                "metric": args.metric,
                "limit": args.limit,
                "limit_per_metric": args.limit_per_metric,
            }
            result = await client.get("/metadata", params=params)
            return result.json().get("data", {})

    @classmethod
    def _from_config(cls, config: Config) -> "MetadataTool":
        return cls(config)


class StatusConfigInput(BaseModel):
    pass


class StatusConfigTool(BaseTool):
    """Tool for getting Prometheus configuration"""

    _description = """Retrieves the current configuration of the Prometheus server.
        Use this tool to view the complete runtime configuration including scrape configs, alert rules, and other settings.
        Helps verify the current server configuration state."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=StatusConfigInput, description=self._description)

    async def run(self, args: StatusConfigInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            response = await client.get("/status/config")
            return response.json()

    @classmethod
    def _from_config(cls, config: Config) -> "StatusConfigTool":
        return cls(config)


class StatusFlagsInput(BaseModel):
    pass


class StatusFlagsTool(BaseTool):
    """Tool for getting Prometheus flag values"""

    _description = """Retrieves the current command-line flag values used by Prometheus.
        Use this tool to understand how the Prometheus server was started and what runtime options are enabled.
        Shows all configuration flags and their current values."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=StatusFlagsInput, description=self._description)

    async def run(self, args: StatusFlagsInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            response = await client.get("/status/flags")
            return response.json()

    @classmethod
    def _from_config(cls, config: Config) -> "StatusFlagsTool":
        return cls(config)


class RuntimeInfoInput(BaseModel):
    pass


class RuntimeInfoTool(BaseTool):
    """Tool for getting Prometheus runtime information"""

    _description = """Provides detailed information about the Prometheus server's runtime state.
        Use this tool to monitor server health and performance through details about garbage collection,
        memory usage, and other runtime metrics."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=RuntimeInfoInput, description=self._description)

    async def run(self, args: RuntimeInfoInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            response = await client.get("/status/runtimeinfo")
            return response.json()

    @classmethod
    def _from_config(cls, config: Config) -> "RuntimeInfoTool":
        return cls(config)


class BuildInfoInput(BaseModel):
    pass


class BuildInfoTool(BaseTool):
    """Tool for getting Prometheus build information"""

    _description = """Retrieves information about how the Prometheus server was built.
        Use this tool to verify version information, build timestamps, and other compilation details.
        Helps confirm the version and build configuration of the running server."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=BuildInfoInput, description=self._description)

    async def run(self, args: BuildInfoInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            response = await client.get("/status/buildinfo")
            return response.json()

    @classmethod
    def _from_config(cls, config: Config) -> "BuildInfoTool":
        return cls(config)


class TSDBStatusInput(BaseModel):
    limit: Optional[int] = Field(default=None, description="Number of items limit")


class TSDBStatusTool(BaseTool):
    """Tool for getting Prometheus TSDB status"""

    _description = """Provides information about the time series database (TSDB) status in Prometheus.
        Use this tool to monitor database health through details about data storage, head blocks,
        WAL status, and other TSDB metrics."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=TSDBStatusInput, description=self._description)

    async def run(self, args: TSDBStatusInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            params = {"limit": args.limit} if args.limit is not None else None
            response = await client.get("/status/tsdb", params=params)
            return response.json()

    @classmethod
    def _from_config(cls, config: Config) -> "TSDBStatusTool":
        return cls(config)


class CreateSnapshotInput(BaseModel):
    skip_head: Optional[bool] = Field(default=None, description="Skip head block flag")


class CreateSnapshotTool(BaseTool):
    """Tool for creating Prometheus snapshots"""

    _description = """Creates a snapshot of the current Prometheus TSDB data.
        Use this tool for backup purposes or creating point-in-time copies of the data.
        You can optionally skip snapshotting the head block (latest, incomplete data)."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=CreateSnapshotInput, description=self._description)

    async def run(self, args: CreateSnapshotInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            params = {"skip_head": "true" if args.skip_head else None}
            response = await client.post("/admin/tsdb/snapshot", content=params)
            return response.json()

    @classmethod
    def _from_config(cls, config: Config) -> "CreateSnapshotTool":
        return cls(config)


class DeleteSeriesInput(BaseModel):
    match: List[str] = Field(description="Series selectors")
    start: Optional[Union[datetime, float]] = Field(default=None, description="Start timestamp")
    end: Optional[Union[datetime, float]] = Field(default=None, description="End timestamp")


class DeleteSeriesTool(BaseTool):
    """Tool for deleting Prometheus series data"""

    _description = """Deletes time series data matching specific criteria in Prometheus.
        Use this tool carefully to remove obsolete data or free up storage space.
        Deleted data cannot be recovered. You can specify time ranges and series selectors."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=DeleteSeriesInput, description=self._description)

    async def run(self, args: DeleteSeriesInput, cancellation_token: CancellationToken) -> BaseModel:
        async with get_http_client(self.config, cancellation_token) as client:
            params = {
                "match[]": args.match,
                "start": _format_time(args.start) if args.start else None,
                "end": _format_time(args.end) if args.end else None,
            }
            response = await client.post("/admin/tsdb/delete_series", content=params)
            return response.json()

    @classmethod
    def _from_config(cls, config: Config) -> "DeleteSeriesTool":
        return cls(config)


class CleanTombstonesInput(BaseModel):
    pass


class CleanTombstonesTool(BaseTool):
    """Tool for cleaning Prometheus tombstones"""

    _description = """Removes tombstone files created during Prometheus data deletion operations.
        Use this tool to maintain database cleanliness and recover storage space.
        Tombstones are markers for deleted data and can be safely removed after their retention period."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=CleanTombstonesInput, description=self._description)

    async def run(self, args: CleanTombstonesInput, cancellation_token: CancellationToken) -> None:
        async with get_http_client(self.config, cancellation_token) as client:
            response = await client.post("/admin/tsdb/clean_tombstones")
            return response.json()

    @classmethod
    def _from_config(cls, config: Config) -> "CleanTombstonesTool":
        return cls(config)


class WALReplayInput(BaseModel):
    pass


class WALReplayTool(BaseTool):
    """Tool for getting Prometheus WAL replay status"""

    _description = """Retrieves the status of Write-Ahead Log (WAL) replay operations in Prometheus.
        Use this tool to monitor the progress of WAL replay during server startup or recovery.
        Helps track data durability and recovery progress."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, input_model=WALReplayInput, description=self._description)

    async def run(self, args: WALReplayInput, cancellation_token: CancellationToken) -> Any:
        async with get_http_client(self.config, cancellation_token) as client:
            response = await client.get("/status/walreplay")
            return response.json()

    @classmethod
    def _from_config(cls, config: Config) -> "WALReplayTool":
        return cls(config)
