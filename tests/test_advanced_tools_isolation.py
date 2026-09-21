"""
tests/test_advanced_tools_isolation.py - guard the advanced_tools boundary.

advanced_tools.py is a set of DUMB executors: it performs no approval or sandbox
decisions. All gating lives in tools.py, which is the ONLY module allowed to
import advanced_tools. These two tests pin that boundary so a future change
doesn't silently (a) grow advanced_tools with new public executors, or (b) wire
an advanced_tools function from tools.py without it going through the guarded
handlers.
"""

import re
import importlib

import coderai.tools.advanced_tools as advanced_tools
import coderai.tools.tools as tools

# The only advanced_tools executors that tools.py is allowed to call.
EXPECTED_EXECUTORS = {
    "tool_navigate_web",
    "tool_take_screenshot",
    "tool_test_api_endpoint",
}
EXPECTED_NAMES = {"navigate_web", "take_screenshot", "test_api_endpoint"}


def test_only_expected_public_executors():
    """advanced_tools may only expose the three live executors."""
    module = importlib.import_module("coderai.tools.advanced_tools")
    public_executors = {
        name for name in dir(module) if name.startswith("tool_")
    }
    assert public_executors == EXPECTED_EXECUTORS, (
        f"Unexpected public executors in advanced_tools: "
        f"{sorted(public_executors - EXPECTED_EXECUTORS)}; "
        f"missing: {sorted(EXPECTED_EXECUTORS - public_executors)}"
    )


def test_tools_only_wires_expected_advanced_functions():
    """tools.py may only reference advanced_tools.tool_<name> for the 3 live names."""
    source = open(tools.__file__, "r", encoding="utf-8").read()
    referenced = set(re.findall(r"advanced_tools\.tool_(\w+)", source))
    assert referenced == EXPECTED_NAMES, (
        f"tools.py references unexpected advanced_tools executors: "
        f"{sorted(referenced - EXPECTED_NAMES)}; "
        f"missing expected: {sorted(EXPECTED_NAMES - referenced)}"
    )
