from unittest import result

from github import Github
import os
import subprocess
from loguru import logger
from dotenv import load_dotenv

load_dotenv()
g= Github(os.getenv("GITHUB_TOKEN"))

WORKSPACE = "/tmp/mcp_workspace"

def clone_repo(repo_name: str):
    github_repo = g.get_repo(repo_name)
    extracted_name = github_repo.name
    local_path = os.path.join(WORKSPACE, extracted_name)
    print(f"Cloning repository {repo_name} to {local_path}...")
    if os.path.exists(local_path):
        logger.info(f"Repository {repo_name} already exists at {local_path}. Pulling latest changes.")
        result = subprocess.run(["git", "-C", local_path, "pull"], capture_output=True, text=True, check=True)
        return {
            "status": "success",
            "message": result.stdout.strip(),
            "error": "",
        }
    else: 
        logger.info(f"Cloning repository {repo_name} to {local_path}.")
        result = subprocess.run(["git", "clone", github_repo.html_url, local_path], check=True)
        prepare_workspace(local_path)
        return {
            "status": "success",
            "message": f"Repository cloned successfully to {local_path}.",
            "error": "",
        }

def prepare_workspace(repo_path: str):
    if not os.path.exists(os.path.join(repo_path, "node_modules")):
        subprocess.run(["npm", "install"], cwd=repo_path, check=True)




# if __name__ == "__main__":
#     repo_name = "dejavuAnkit/problem-nextjs"
#     local_path = clone_repo(repo_name)
#     print(f"Repository cloned to: {local_path}")