#!/usr/bin/env python3
"""
cs-formatting installer
Installs CSharpier and sets up a GitHub Actions workflow pointing to
https://github.com/RadTadDev/cs-formatting
"""

import json
import subprocess
import sys
from pathlib import Path

CSHARPIER_VERSION = "1.2.6"

WORKFLOW_CONTENT = f"""\
name: Format Check

on:
  push:
  pull_request:

jobs:
  format:
    uses: RadTadDev/cs-formatting/.github/workflows/ci-format.yml@main
    with:
        csharpier-version: "{CSHARPIER_VERSION}"
"""

HOOK_CONTENT = """\
#!/bin/sh
files=$(git diff --cached --name-only --diff-filter=ACM | grep '\\.cs$')
if [ -z "$files" ]; then
  exit 0
fi
echo "Running CSharpier format check..."
echo "$files" | xargs dotnet csharpier check .
if [ $? -ne 0 ]; then
  echo "CSharpier found formatting issues. Run 'dotnet csharpier check .' to see or 'dotnet csharpier format .' to fix."
  exit 1
fi
"""


def run(args, check=True):
    print(f"  > {' '.join(args)}")
    result = subprocess.run(args, check=check)
    return result.returncode


def find_repo_root():
    path = Path.cwd()
    while path != path.parent:
        if (path / ".git").exists():
            return path
        path = path.parent
    return None


def get_gh_repo(repo_root):
    """Returns 'owner/repo' string from gh CLI, or None if unavailable."""
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return None
 
 
def gh_api(args, repo_root, input=None):
    """Run a gh api command, returning (returncode, parsed_json_or_none, stderr)."""
    result = subprocess.run(
        ["gh", "api"] + args,
        input=input,
        capture_output=True,
        text=True,
        cwd=repo_root
    )
    try:
        data = json.loads(result.stdout) if result.stdout.strip() else None
    except json.JSONDecodeError:
        data = None
    return result.returncode, data, result.stderr
 
 
def setup_branch_protection(repo_root):
    print("Setting up branch protection...")
 
    repo = get_gh_repo(repo_root)
    if not repo:
        print("  WARNING: gh CLI not found or not authenticated. Skipping branch protection.")
        print("  Install gh CLI and run 'gh auth login', then re-run this installer.\n")
        return
 
    owner, name = repo.split("/")
    endpoint = f"repos/{owner}/{name}/branches/main/protection"
 
    # Read existing protection
    returncode, existing, stderr = gh_api([endpoint], repo_root)
 
    if returncode != 0 and "Branch" in stderr and "404" in stderr:
        print("  WARNING: Branch 'main' not found. Push an initial commit first, then re-run.\n")
        return
    elif returncode != 0 and "404" in stderr:
        # 404 on the protection endpoint means no protection set yet - that's fine
        existing = None
    elif returncode != 0:
        if "403" in stderr or "Resource not accessible" in stderr:
            print("  WARNING: Insufficient permissions to read branch protection.")
            print(f"  Ask a repo admin to protect main and require the 'format' status check on {repo}.\n")
        else:
            print(f"  WARNING: Failed to read branch protection: {stderr.strip()}\n")
        return
 
    # Check if format check is already present
    existing_contexts = (
        (existing or {}).get("required_status_checks") or {}
    ).get("contexts", [])
 
    if "format" in existing_contexts:
        print("  Format check already present in branch protection, skipping.\n")
        return
 
    # Merge format check into existing contexts, preserving all other rules
    protection = {
        "required_status_checks": {
            "strict": ((existing or {}).get("required_status_checks") or {}).get("strict", True),
            "contexts": existing_contexts + ["format"]
        },
        "enforce_admins": ((existing or {}).get("enforce_admins") or {}).get("enabled", True),
        "required_pull_request_reviews": (existing or {}).get("required_pull_request_reviews"),
        "restrictions": (existing or {}).get("restrictions"),
    }
 
    returncode, _, stderr = gh_api(
        [endpoint, "--method", "PUT", "--input", "-"],
        repo_root,
        input=json.dumps(protection)
    )
 
    if returncode == 0:
        print(f"  Format check added to branch protection on {repo}/main.")
        print("  NOTE: The 'format' check won't be enforced until the workflow has run at least once.\n")
    elif "403" in stderr or "Resource not accessible" in stderr:
        print("  WARNING: Insufficient permissions to set branch protection.")
        print(f"  Ask a repo admin to protect main and require the 'format' status check on {repo}.\n")
    else:
        print(f"  WARNING: Failed to set branch protection: {stderr.strip()}\n")
 

def main():
    repo_root = find_repo_root()
    if not repo_root:
        print("Error: not inside a git repository.")
        sys.exit(1)

    print(f"Repo root: {repo_root}\n")

    # Install CSharpier
    print("Installing CSharpier...")
    result = run(["dotnet", "tool", "install", "csharpier", "--version", CSHARPIER_VERSION], check=False)
    if result == 0:
        print("  CSharpier installed.\n")
    else:
        print("  CSharpier may already be installed, continuing.\n")

    # Set up pre-commit hook
    print("Setting up pre-commit hook...")
    hooks_dir = repo_root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "pre-commit"
    hook_path.write_text(HOOK_CONTENT)
    print("  Pre-commit hook installed.\n")

    # Set up GitHub Actions workflow
    print("Setting up GitHub Actions workflow...")
    workflows_dir = repo_root / ".github" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    workflow_path = workflows_dir / "cs-format-check.yml"

    if workflow_path.exists():
        print("  cs-format-check.yml already exists, skipping.")
    else:
        workflow_path.write_text(WORKFLOW_CONTENT)
        print("  Workflow file created.\n")

    # Set up branch protection
    setup_branch_protection(repo_root)

    print("Done! Next steps:")
    print("  - Commit .config/dotnet-tools.json and .github/workflows/cs-format-check.yml")
    print("  - Run 'dotnet csharpier .' to format existing code before your first commit")


if __name__ == "__main__":
    main()