"""Guards that each service still exposes the methods its router calls.

A refactor once moved ReportService.heatmap inside a module-level function,
leaving /api/reports/heatmap raising AttributeError at runtime while every unit
test still passed. These assertions are cheap and catch that whole class of
error.
"""
import inspect

from hali.services.alerts import AlertService
from hali.services.reports import ReportService
from hali.services.spatial import SpatialService


def _assert_async_methods(cls, names):
    for name in names:
        method = getattr(cls, name, None)
        assert method is not None, f"{cls.__name__}.{name} is missing"
        assert inspect.iscoroutinefunction(method), f"{cls.__name__}.{name} must be async"


def test_report_service_surface():
    _assert_async_methods(ReportService, ["create", "heatmap"])
    assert callable(getattr(ReportService, "schedule_classification", None))


def test_alert_service_surface():
    _assert_async_methods(AlertService, ["list_alerts", "geojson", "action_card"])


def test_spatial_service_surface():
    _assert_async_methods(SpatialService, ["compound_risk", "emerging_hotspots", "analyse"])


def test_no_methods_orphaned_outside_their_class():
    """Every public service method should belong to the service class."""
    for cls in (ReportService, AlertService, SpatialService):
        module = inspect.getmodule(cls)
        for name, obj in vars(module).items():
            if name.startswith("_") or not inspect.isfunction(obj):
                continue
            # A function taking `self` at module level is an orphaned method.
            params = list(inspect.signature(obj).parameters)
            assert params[:1] != ["self"], f"{module.__name__}.{name} looks like an orphaned method"
