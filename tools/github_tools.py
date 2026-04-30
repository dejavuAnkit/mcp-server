from github import Github
import os
import subprocess
from loguru import logger
from dotenv import load_dotenv

load_dotenv()
g= Github(os.getenv("GITHUB_TOKEN"))

def get_repo(repo_name: str):
    try:
        repo = g.get_repo(repo_name)
        logger.info(f"Fetched repository: {repo.full_name}")
        return repo
    except Exception as e:
        logger.error(f"Error fetching repository: {e}")
        return None
    
def list_repo_files(repo_name: str, path: str = ""):
    repo = get_repo(repo_name)
    if not repo:
        return []
    
    try:
        contents = repo.get_contents(path)
        files = []
        for content in contents:
            if content.type == "file":
                files.append(content.path)
            elif content.type == "dir":
                files.extend(list_repo_files(repo_name, content.path))
        return files
    except Exception as e:
        logger.error(f"Error listing repository files: {e}")
        return []
    
def get_file_content(repo_name: str, file_path: str):
    repo = get_repo(repo_name)
    if not repo:
        return None
    
    try:
        file_content = repo.get_contents(file_path)
        return file_content.decoded_content.decode("utf-8")
    except Exception as e:
        logger.error(f"Error fetching file content: {e}")
        return None

def clone_repo(repo_name: str, local_path: str):
    repo = get_repo(repo_name)
    if not repo:
        return False
    
    try:
        if os.path.exists(local_path):
            logger.warning(f"Local path {local_path} already exists. Skipping clone.")
            return pull_repo(local_path)
        subprocess.run(["git", "clone", repo.clone_url, local_path])
        logger.info(f"Cloned repository to {local_path}")
        return True
    except Exception as e:
        logger.error(f"Error cloning repository: {e}")
        return False
    
def pull_repo(local_path: str):
    try:
        if not os.path.exists(local_path):
            logger.warning(f"Local path {local_path} does not exist. Cannot pull.")
            return False
        subprocess.run(["git", "pull"], cwd=local_path)
        logger.info(f"Pulled latest changes in {local_path}")
        return True
    except Exception as e:
        logger.error(f"Error pulling repository: {e}")
        return False