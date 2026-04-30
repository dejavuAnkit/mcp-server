from fastmcp import FastMCP
from tools.github_tools import list_repo_files, get_file_content, clone_repo, pull_repo

mcp = FastMCP("My MCP Server")

@mcp.tool()
def list_files(repo_name: str) -> list:
    """List all files in a GitHub repository."""
    files = list_repo_files(repo_name)
    if not files:
        return ["No files found or error fetching repository.", repo_name]
    return files


@mcp.tool()
def read_file(repo_name: str, file_path: str) -> str:
    """Read the content of a file from a GitHub repository."""
    content = get_file_content(repo_name, file_path)
    if content is None:
        return "Error fetching file content."
    return content

@mcp.tool()
def clone_repository(repo_name: str, local_path: str) -> str:
    """Clone a GitHub repository to a local path."""
    success = clone_repo(repo_name, local_path)
    if success:
        return f"Repository cloned successfully to {local_path}."
    else:
        return "Error cloning repository."



if __name__ == "__main__":
    mcp.run()




