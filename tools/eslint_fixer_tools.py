from random import random
import re
import subprocess
import os
import json
import tempfile
import time
import random   
from collections import defaultdict
from anthropic import Anthropic
from dotenv import load_dotenv
import requests


load_dotenv()  # Load environment variables from .env file

WORKSPACE = "/tmp/mcp_workspace"

JIRA_TICKET_PREFIX = "DIG2022"
JIRA_TICKET_POSTFIX = "AUTOFIX"

# Initialize client once (reuse)
client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY")
)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Config (tune as needed)
MODEL = "claude-haiku-4-5"
MAX_TOKENS = 2000
TEMPERATURE = 0.2
MAX_RETRIES = 3
TIMEOUT = 30



class AIFixService:

    def fix(self, repo_name: str, issues: list) -> list:
        repo_name = repo_name.split("/")[-1]  # Extract repo name from full path
        repo_path = os.path.join(WORKSPACE, repo_name)

        if not os.path.exists(repo_path):
            raise Exception(f"Repository path {repo_path} does not exist. Please clone the repository first.")
        
        file_map = self.group_by_file(issues)
        results = []
        for file, file_issues in file_map.items():
            result = self._fix_file(repo_path, file, file_issues)
            results.append(result)
        return results

    def group_by_file(self, issues: list) -> dict:
        file_map = defaultdict(list)
        for issue in issues:
            file_map[issue["file"]].append(issue)
        return file_map
    

    def _fix_file(self, repo_path: str, file: str, issues: list) -> str:
        full_path = os.path.join(repo_path, file)

        if not os.path.exists(full_path):
            raise Exception(f"File {full_path} does not exist. Cannot apply fixes.")
        
        with open(full_path, "r") as f:
            code = f.read()
        snippets = self.extract_snippets(code, issues)
       
        try:
            fixed_code = generate_fixed_code(file, snippets, issues)
            patch = generate_patch_from_code(code, fixed_code, file, repo_path)
            if not patch:
                return f"No valid patch generated for {file}."
            
            result = apply_patch(repo_path, patch)

            if result:
                messages = generate_message(issues)
                commit_changes(repo_path, messages)
                return {"file": file, "status": "fixed"}
        
        except Exception as e:
            return f"Error generating patch for {file}: {str(e)}"


    def extract_snippets(self, code: str, issues: list, window=20) -> list:
        lines = code.splitlines()
        ranges = []
        for issue in issues:
            line= issue.get("line", 0)
            start = max(0, line - window)
            end = min(len(lines), line + window)
            ranges.append((start, end ))

        ranges.sort()
        merged = []

        for start, end in ranges:
            if not merged:
                merged.append((start, end))
            else:
                last_start, last_end = merged[-1]
                if start <= last_end:
                    merged[-1] = (last_start, max(last_end, end))
                else:
                    merged.append((start, end))
        
        snippets = []
        for start, end in merged:
            snippets.append({
                "start_line": start,
                "end_line": end,
                "code": "\n".join(lines[start:end])
            })

        return snippets
    

def call_claude(prompt: str) -> str:
    """
    Call Claude to generate patch (robust version)
    """

    if not prompt or len(prompt.strip()) == 0:
        raise ValueError("Prompt cannot be empty")

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                system=(
                    "You are a precise code-fixing assistant. "
                    "Return ONLY the corrected code. "
                    "Do NOT return a diff. "
                    "Do NOT include explanations or markdown."
                ),
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
            )

            # Extract text safely
            content = response.content

            if not content:
                raise Exception("Empty response from Claude")

            # Claude returns list of blocks
            output = "".join(
                block.text for block in content if hasattr(block, "text")
            ).strip()

            output = clean_code_output(output)

            if not output:
                raise Exception("No text in Claude response")

            return output

        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise Exception(f"Claude API failed: {str(e)}")

            # Exponential backoff
            time.sleep(2 ** attempt)

    return None


def generate_fixed_code(file_path: str, snippets: list, issues: list) -> str:
    """
    Ask Claude to return ONLY fixed code (no diff)
    """

    prompt = f"""
You are a senior TypeScript + React engineer.

Fix ONLY the ESLint issues listed below.

STRICT RULES:
- Modify ONLY the provided snippets
- Do NOT rewrite unrelated parts
- Do NOT change logic unnecessarily
- Keep changes minimal
- Preserve formatting
- Do NOT add unnecessary imports

OUTPUT RULES:
- Return ONLY the corrected code
- Do NOT return a diff
- Do NOT include explanations
- Do NOT include markdown

Snippets:
{json.dumps(snippets, indent=2)}

Issues:
{json.dumps(issues, indent=2)}
"""

    response = call_claude(prompt)

    if not response or len(response.strip()) == 0:
        return None

    return response.strip()

def generate_patch_from_code(original_code: str, fixed_code: str, file_path: str, root_path: str) -> str:
    """
    Generate a valid git patch using git diff
    """
    with tempfile.NamedTemporaryFile(delete=False, mode="w") as f1, \
         tempfile.NamedTemporaryFile(delete=False, mode="w") as f2:

        f1.write(original_code)
        f2.write(fixed_code)

        f1.flush()
        f2.flush()

        result = subprocess.run(
            ["git", "diff", "--no-index", f1.name, f2.name],
            capture_output=True,
            text=True,
        )

    patch = result.stdout

    if not patch:
        return None

    # Replace temp paths with actual repo paths

    relative_path = os.path.relpath(file_path, root_path)

    patch = patch.replace(f1.name, f"a/{relative_path}")
    patch = patch.replace(f2.name, f"b/{relative_path}")

    return patch

def apply_patch(repo_path: str, patch: str):
    if not patch or "diff --git" not in patch:
        raise Exception("Invalid patch format")

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(patch)
        patch_file = f.name

    # First check (safe)
    check = subprocess.run(
        ["git", "apply", "--check", patch_file],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True
    )

    if check.returncode != 0:
        return False

    # Apply
    subprocess.run(
        ["git", "apply", "--whitespace=fix", patch_file],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True
    )

    return True

def clean_code_output(text: str) -> str:
    text = text.strip()

    # Remove ```typescript or ```ts or ```
    if text.startswith("```"):
        lines = text.splitlines()

        # remove first and last line (fence)
        if len(lines) >= 2:
            lines = lines[1:-1]

        text = "\n".join(lines)

    return text.strip()


def commit_changes(repo_path, message: str):
        try:
            branch_name = create_branch(repo_path)
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True, text=True)
            subprocess.run(["git", "commit", "-m", message], cwd=repo_path, check=True, capture_output=True, text=True)
            subprocess.run(["git", "push", "origin", branch_name], cwd=repo_path, check=True, capture_output=True, text=True)

            # Create PR (not implemented here)

            result = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                cwd=repo_path,
                capture_output=True,
                text=True
            )

            repo_url = result.stdout.strip()
            repo_url = repo_url.replace(".git", "")

            parts = repo_url.split("/")
            owner = parts[-2]
            repo = parts[-1]

            if not GITHUB_TOKEN:
                return None

            url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
            
            headers = {
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json"
            }

            data = {
                "title": branch_name,
                "body": "body",
                "head": branch_name,
                "base": "main"
            }

            response = requests.post(url, json=data, headers=headers)
            if response.status_code == 201:
                pr_url = response.json()["html_url"]
                return pr_url
            else:
                return None
        except Exception as e:
            return None
def create_branch(repo_path: str):
    ticket_id = random.randint(1000, 9999)
    full_branch_name = f"{JIRA_TICKET_PREFIX}-{ticket_id}/{JIRA_TICKET_POSTFIX}"

    subprocess.run(["git", "checkout", "main"], cwd=repo_path, check=True, capture_output=True, text=True)  
    subprocess.run(["git", "pull"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "checkout", "-b", full_branch_name], cwd=repo_path, check=True, capture_output=True, text=True)    
    return full_branch_name

def generate_message(issues: list) -> str:
    if not issues:
        return "fix(eslint): automated fixes"
    rules = list(set(issue.get("rule", "unknown") for issue in issues))
    return f"fix(eslint): automated fixes for rules: {', '.join(rules)}"

 

# example_input = {
#   "repo_name": "dejavuAnkit/problem-nextjs",
#   "issues": [
#     {
#       "file": "/tmp/mcp_workspace/problem-nextjs/src/components/UnsafeComponent.tsx",
#       "rule": "@typescript-eslint/no-explicit-any",
#       "severity": 2,
#       "message": "Unexpected any. Specify a different type.",
#       "line": 2,
#       "column": 9
#     },
#     {
#       "file": "/tmp/mcp_workspace/problem-nextjs/src/pages/index.tsx",
#       "rule": "@typescript-eslint/no-explicit-any",
#       "severity": 2,
#       "message": "Unexpected any. Specify a different type.",
#       "line": 5,
#       "column": 36
#     },
#     {
#       "file": "/tmp/mcp_workspace/problem-nextjs/src/pages/index.tsx",
#       "rule": "@next/next/no-img-element",
#       "severity": 1,
#       "message": "Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element",
#       "line": 18,
#       "column": 7
#     },
#     {
#       "file": "/tmp/mcp_workspace/problem-nextjs/src/pages/index.tsx",
#       "rule": "jsx-a11y/alt-text",
#       "severity": 1,
#       "message": "img elements must have an alt prop, either with meaningful text, or an empty string for decorative images.",
#       "line": 18,
#       "column": 7
#     },
#     {
#       "file": "/tmp/mcp_workspace/problem-nextjs/src/pages/index.tsx",
#       "rule": "react/jsx-key",
#       "severity": 2,
#       "message": "Missing \"key\" prop for element in iterator",
#       "line": 35,
#       "column": 9
#     },
#     {
#       "file": "/tmp/mcp_workspace/problem-nextjs/src/utils/helper.ts",
#       "rule": "@typescript-eslint/no-unused-vars",
#       "severity": 1,
#       "message": "'temp' is assigned a value but never used.",
#       "line": 2,
#       "column": 7
#     }
#   ]
# }



# if __name__ == "__main__":
#     # For local testing
#     result = AIFixService().fix(example_input["repo_name"], example_input["issues"])
#     print(json.dumps(result, indent=2))
#     pass