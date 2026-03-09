"""
Registry of Hermes rover tools: drive_rover, read_sensors, navigate_to,
check_hazards, rover_memory, generate_report.
Provides get_all_tools() and get_tool_executor(name).
"""
from . import drive_tool
from . import sensor_tool
from . import navigate_tool
from . import hazard_tool
from . import memory_tool
from . import report_tool

_TOOL_MODULES = [drive_tool, sensor_tool, navigate_tool, hazard_tool, memory_tool, report_tool]
_NAME_TO_MODULE = {m.TOOL_SCHEMA["name"]: m for m in _TOOL_MODULES}


def get_all_tools():
    """Return list of all TOOL_SCHEMA dicts."""
    return [m.TOOL_SCHEMA for m in _TOOL_MODULES]


def get_tool_executor(name):
    """Return the execute function for the tool with the given name, or None."""
    mod = _NAME_TO_MODULE.get(name)
    return getattr(mod, "execute", None) if mod else None
