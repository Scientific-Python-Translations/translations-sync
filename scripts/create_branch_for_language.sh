#usr/bin/env bash

# Given a GitHub repository which has been synced to Crowdin, this script
# is used to create a new branch including all and only commits from Crowdin's
# branch for a particular language of interest. It is useful because

# 1. Crowdin's branch contains commits for all languages under translation,
#    but we prefer to be able to create, review, and merge pull requests for
#    one language at a time.
#
# 2. Crowdin's branch can only be edited through the Crowdin UI (commits
#    pushed to it outside of Crowdin will be lost when the branch is synced
#    to Crowdin. There are times when translations must be edited outside of
#    Crowdin due to incorrect segmentation of the content into strings for
#    translation (e.g. html embedded within markdown documents getting
#    garbled).

# This script must be run inside of the repository of interest. At the
# end, the newly created branch will be checked out. As a side effect,
# the local source branch and the corresponding local Crowdin branch
# (e.g. main and  l10n_main respectively) will become up to date with the
# upstream remote (e.g. numpy/main and numpy/l10n_main for numpy.org).


# Clean up by aborting the rebase and deleting the new branch if there
# has been an error.
set -e

cleanup() {
    echo "Performing cleanup..."
    if git branch --list | grep -q "$new_branch"; then
        git rebase --abort || true
        git checkout "$source_branch"
        git branch -D "$new_branch"
    fi
}

trap cleanup EXIT


# Check arguments
if [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ] || [ -z "$4" ]; then
  echo "Usage: $0 <upstream_remote> <source_branch> <crowdin_branch> <language_code>"
  exit 1
fi

upstream_remote=$1
source_branch=$2
crowdin_branch=$3
language_code=$4

script_location=$(dirname "$0")

# The following lines will ensure that things are in a consistent state to be able
# to submit a PR upstream. Since we have used `set -e`, any line which causes an
# error will cause the entire script to exit.

# Make sure source branch is up to date with upstream
git checkout $source_branch
git fetch $upstream_remote
git merge --ff-only "${upstream_remote}/${source_branch}"

# Make sure the corresponding Crowdin branch is up to date
git checkout $crowdin_branch
git merge --ff-only "${upstream_remote}/${crowdin_branch}"

# Check that crowdin branch has no merge conflicts with respect to the source branch
git checkout $source_branch
merge_output=$(git merge --no-commit --no-ff $crowdin_branch)
git merge --abort

git checkout $crowdin_branch

# Generate a timestamp for use in branch name
timestamp=$(date +%Y_%m_%d_%H_%M_%S)

# Checkout a new branch for these translations
new_branch="${crowdin_branch}_${language_code}_${timestamp}"
git checkout -b $new_branch

# Perform scripted interactive rebase, taking only commits
# for the language of interest.
GIT_SEQUENCE_EDITOR="f() {
    filename=\$1
    python3 -c \"
import sys
sys.path.insert(0, '$script_location')
from git_tools import filter_commits

filter_commits('\$filename', '$language_code')
\"
}; f" git rebase -i "$source_branch"

# Remove the trap if the rebase succeeds. No clean up is necessary.
trap - EXIT

# Make script output the branch name so it can be used later if needed.
echo $new_branch
