from mcp.server.fastmcp import FastMCP

from prowl_mcp.clients.prowlarr import make_client
from prowl_mcp.config import Settings
from prowl_mcp.tools.search import register_search_tools

mcp = FastMCP("prowl-mcp")
register_search_tools(mcp, make_client(Settings()))


@mcp.tool()
def ping() -> str:
    """Check that the ProwlMCP server is running."""
    return "test"


if __name__ == "__main__":
    mcp.run()
