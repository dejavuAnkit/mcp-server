import subprocess
import json
import os
import shutil
from unittest import result

from importlib_metadata import files


WORKSPACE = "/tmp/mcp_workspace"
SCAN_MARKER = ".mcp_scan_done"


def get_repo_path(repo_name: str) -> str:
    return os.path.join(WORKSPACE, repo_name.split("/")[-1])


def get_all_files(repo_path: str) -> list:
    print(f"Getting all JavaScript/TypeScript files in {repo_path}...")
    result = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
    files = [
            f for f in result.stdout.splitlines()
            if f.endswith((".js", ".ts", ".tsx"))
        ]
    return files

def get_changed_files(repo_path: str) -> list:
   print(f"Getting changed files in {repo_path}...")
   result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
   
   files = [
        f for f in result.stdout.splitlines()
        if f.endswith((".js", ".ts", ".tsx"))
    ]
   
   return files

def is_first_scan(repo_path: str) -> bool:
    print(f"Checking for scan marker at {os.path.join(repo_path, SCAN_MARKER)}")
    return not os.path.exists(os.path.join(repo_path, SCAN_MARKER))

def mark_scan_complete(repo_path: str):
    open(os.path.join(repo_path, SCAN_MARKER), "w").close()


def run_eslint(repo_name: str, files: list):
    if not files:
        return []

    result = subprocess.run(
        [
            "npx",
            "eslint",
            *files,
            "--format",
            "json",
            "--cache"
        ],
        cwd=repo_name,
        capture_output=True,
        text=True
     )
 
    
    if result.returncode not in (0, 1):
        raise Exception(f"ESLint failed: {result.stderr}")

    return json.loads(result.stdout or "[]")
    

def eslint_scan(repo_name: str):
    """
    Run ESLint on a specified repository and return the issues found.

    IMPORTANT:
    - repo_name must be ONLY the repository name (e.g., "problem-nextjs")
    - DO NOT include owner or organization (e.g., "user/repo" is invalid)
    """

    repo_path = get_repo_path(repo_name)

    if not os.path.exists(repo_path):
        raise Exception(f"Repository path {repo_path} does not exist. Please clone the repository first.")  
    
    if is_first_scan(repo_path):
        print("Performing first scan (full scan)...")
        files = get_all_files(repo_path)
        scan_type = "full"
        mark_scan_complete(repo_path)
    else:
        print("Performing incremental scan (changed files only)...")
        files = get_changed_files(repo_path)

    if not files:
        return ["No JavaScript/TypeScript files found to scan.", repo_name]
    
 
    results = run_eslint(repo_path, files)



        # Normalize output (important for downstream PR/Jira)
    issues = []
    for file_result in results:
        for msg in file_result.get("messages", []):
            issues.append({
                "file": normalize_path(file_result.get("filePath")  or ""),
                "rule": msg.get("ruleId"),
                "severity": msg.get("severity"),
                "message": msg.get("message"),
                "line": msg.get("line"),
                "column": msg.get("column")
            })

    return issues


def normalize_path(path: str) -> str:
    return path.replace("/private/tmp/", "/tmp/")


# if __name__ == "__main__":
#     file_path = "problem-nextjs"
#     issues = eslint_scan(file_path)
#     print(json.dumps(issues, indent=2))