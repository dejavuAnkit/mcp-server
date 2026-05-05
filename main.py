from fastmcp import FastMCP
from tools.eslint_fixer_tools import AIFixService
from tools.github_tools import clone_repo 
from tools.scanner_tools import eslint_scan
from dotenv import load_dotenv
mcp = FastMCP("My MCP Server")

load_dotenv()  # Load environment variables from .env file

@mcp.tool()
def clone_repository(repo_name: str) -> str:
    """Clone a GitHub repository to a local path."""
    success = clone_repo(repo_name)
    if success:
        return f"Repository cloned successfully."
    else:
        return "Error cloning repository."

@mcp.tool()
def scan_eslint(repo_name: str) -> list:
    """Run ESLint on a specified repository and return the issues found. and dont append pivrate files to the list of issues"""
    from tools.scanner_tools import run_eslint
    issues = eslint_scan(repo_name)
    if not issues:
        return []
    return issues


@mcp.tool()
def fix_eslint_with_ai(repo_name: str, issues: list) -> list:
    """
    Fix ESLint issues using AI patches, commit the change and raise thr PR
    """
    service = AIFixService()
    return service.fix(repo_name, issues)


if __name__ == "__main__":
    mcp.run()




