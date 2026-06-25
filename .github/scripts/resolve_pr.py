#!/usr/bin/env python3
# NOTE: AI slop - generated, unreviewed.
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
FILE = "development-updates.md"
MERGE_SCRIPT = "/tmp/dev_updates.py"


def api(path):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "dev-updates-mergeable",
        },
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def run(cmd, check=True, capture=False):
    print("+ " + " ".join(cmd), flush=True)
    res = subprocess.run(cmd, check=check, text=True, capture_output=capture)
    return res.stdout.strip() if capture else ""


def git_show(ref_path):
    res = subprocess.run(["git", "show", ref_path], text=True, capture_output=True)
    return res.stdout if res.returncode == 0 else ""


def fail(msg):
    print(f"::error::{msg}")
    return 1


def main(pr_number):
    pr = api(f"/repos/{REPO}/pulls/{pr_number}")
    if pr.get("state") != "open":
        print(f"PR #{pr_number} not open; nothing to do.")
        return 0

    head_repo = pr["head"]["repo"]["full_name"]
    head_branch = pr["head"]["ref"]
    base_branch = pr["base"]["ref"]
    maintainer_can_modify = pr.get("maintainer_can_modify", False)
    owner = REPO.split("/")[0]
    same_repo = head_repo.split("/")[0] == owner

    files = api(f"/repos/{REPO}/pulls/{pr_number}/files")
    if not any(f["filename"] == FILE for f in files):
        print(f"PR #{pr_number} does not touch {FILE}; nothing to do.")
        return 0

    auth_remote = f"https://x-access-token:{TOKEN}@github.com/{head_repo}.git"

    run(["git", "fetch", "origin", base_branch], check=True)
    run(["git", "remote", "remove", "prhead"], check=False)
    run(["git", "remote", "add", "prhead", auth_remote], check=True)
    # Fetch the branch tip into a stable local ref so git show always resolves.
    run(["git", "fetch", "prhead", f"{head_branch}:_prhead"], check=True)

    head_ref = "_prhead"
    main_ref = f"origin/{base_branch}"
    merge_base = run(["git", "merge-base", head_ref, main_ref], capture=True)
    print(f"merge-base = {merge_base}")

    base_content = git_show(f"{merge_base}:{FILE}")
    ours_content = git_show(f"{head_ref}:{FILE}")
    theirs_content = git_show(f"{main_ref}:{FILE}")

    with tempfile.TemporaryDirectory() as d:
        bp, op, tp, mp = (os.path.join(d, n) for n in ("base", "ours", "theirs", "merged"))
        open(bp, "w").write(base_content)
        open(op, "w").write(ours_content)
        open(tp, "w").write(theirs_content)
        res = subprocess.run(
            [sys.executable, MERGE_SCRIPT, "merge", bp, op, tp, "--output", mp],
            text=True, capture_output=True,
        )
        print(res.stdout)
        if res.stderr:
            print(res.stderr, file=sys.stderr)
        merged = open(mp).read()

    if res.returncode != 0 or "<!-- CONFLICT" in merged:
        return fail(
            "Two changes target the same cell in development-updates.md. "
            "Resolve manually (look for '<!-- CONFLICT' markers)."
        )

    if not maintainer_can_modify and not same_repo:
        return fail(
            "This PR conflicts with development-updates.md and 'Allow edits by "
            "maintainers' is off, so the branch can't be synced automatically. "
            "Enable it and re-run this check, or run "
            "`python3 scripts/dev_updates.py format development-updates.md` locally."
        )

    # This automation only handles PRs that change development-updates.md alone.
    # Flag a genuine other-file change only when the PR head has a non-empty
    # version of another file that differs from the base tip (a real edit/add).
    # Missing/deleted files are ignored because the rebuild restores them from
    # base anyway -- so an earlier bad sync that dropped files doesn't block us.
    others = []
    for f in files:
        name = f["filename"]
        if name == FILE:
            continue
        head_ver = git_show(f"{head_ref}:{name}")
        if head_ver and head_ver != git_show(f"{main_ref}:{name}"):
            others.append(name)
    if others:
        return fail(
            "This PR changes files other than development-updates.md "
            + "(" + ", ".join(others) + "); not auto-syncing."
        )

    # Build the result tree from the BASE branch's tree, replacing only the
    # table with our semantic merge. This guarantees no other file on the base
    # branch is ever touched or dropped -- even if the PR branch forked from an
    # old base or a previous run left it in a bad state. Parents are the PR head
    # and the base tip, so merging the PR back into base is conflict-free.
    parent_pr = run(["git", "rev-parse", head_ref], capture=True)
    parent_base = run(["git", "rev-parse", main_ref], capture=True)
    base_is_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", main_ref, head_ref]
    ).returncode == 0

    if merged == theirs_content and base_is_ancestor:
        print(f"PR #{pr_number}: already in sync with {base_branch}; mergeable.")
        return 0

    run(["git", "read-tree", main_ref], check=True)
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          input=merged, text=True, capture_output=True, check=True).stdout.strip()
    run(["git", "update-index", "--cacheinfo", "100644", blob, FILE], check=True)
    tree = run(["git", "write-tree"], capture=True)
    commit = run(
        ["git", "commit-tree", tree, "-p", parent_pr, "-p", parent_base,
         "-m", "Merge base branch into PR and sync development-updates.md"],
        capture=True,
    )
    run(["git", "push", "prhead", f"{commit}:{head_branch}"], check=True)
    print(f"PR #{pr_number}: synced and pushed to {head_repo}:{head_branch}.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: resolve_pr.py <pr_number>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(int(sys.argv[1])))
