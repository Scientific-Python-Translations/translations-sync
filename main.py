import os
import traceback
import tempfile
from datetime import datetime
from subprocess import Popen, PIPE

from crowdin_api import CrowdinClient
from github import Github, Auth


# Set the output value by writing to the outputs in the Environment File, mimicking the behavior defined here:
#  https://docs.github.com/en/actions/using-workflows/workflow-commands-for-github-actions#setting-an-output-parameter
def set_github_action_output(output_name, output_value):
    """Set the output value by writing to the outputs in the Environment File.

    Parameters
    ----------
    output_name : str
        Name of the output.
    output_value : str
        Value of the output.
    """
    f = open(os.path.abspath(os.environ["GITHUB_OUTPUT"]), "a")
    f.write(f"{output_name}={output_value}")
    f.close()


class ScientificCrowdinClient:

    def __init__(self, token, organization):
        self._token = token
        self._organization = organization
        self._client = CrowdinClient(token=token, organization=organization)

    def get_projects(self):
        result = {}
        projects = self._client.projects.with_fetch_all().list_projects()
        for project in projects["data"]:
            result[project["data"]["name"]] = project["data"]["id"]
        return result

    def get_project_status(self, project):
        results = {}
        for project_name, project_id in self.get_projects().items():
            if project != project_name:
                continue

            languages = self._client.translation_status.get_project_progress(
                project_id
            )["data"]
            for language in languages:
                language_id = language["data"]["language"]["id"]
                results[language_id] = {
                    "language_name": language["data"]["language"]["name"],
                    "progress": language["data"]["translationProgress"],
                    "approval": language["data"]["approvalProgress"],
                }
        return results

    def get_valid_languages(
        self, project_name: str, translation_percentage: int, approval_percentage: int
    ):
        """Get valid languages based on translation and approval percentage.

        Parameters
        ----------
        project_name : str
            Name of the project.
        translation_percentage : int
            Minimum translation percentage.
        approval_percentage : int
            Minimum approval percentage.

        Returns
        -------
        valid_languages : dict
            Dictionary of valid languages.
        """
        valid_languages = {}
        project_languages = self.get_project_status(project_name)
        # print(json.dumps(project_languages, sort_keys=True, indent=4))
        for language_id, data in project_languages.items():
            approval = data["approval"]
            progress = data["progress"]
            language_name = data["language_name"]
            if progress >= translation_percentage and approval >= approval_percentage:
                # print(f"\n{language_id} {language_name}:  {progress}% / {approval}%")
                valid_languages[language_id] = {
                    "language_name": language_name,
                    "progress": progress,
                    "approval": approval,
                }
        return valid_languages


def run(cmds):
    """Run a command in the shell and print output.

    Parameters
    ----------
    cmds : list
        List of commands to run.

    Returns
    -------
    out : str
        Output of the command.
    err : str
        Error of the command.
    rc : int
        Return code of the command.
    """
    p = Popen(cmds, stdout=PIPE, stderr=PIPE)
    out, err = p.communicate()
    print("\n\n\nCmd: \n" + " ".join(cmds))
    print("Out: \n", out.decode())
    print("Err: \n", err.decode())
    print("Code: \n", p.returncode)
    return out, err, p.returncode


def pr(
    username,
    token,
    source_repo,
    source_folder,
    source_ref,
    translations_repo,
    translations_folder,
    translations_ref,
    name,
    email,
):
    """Sync content from source repository to translations repository.

    Parameters
    ----------
    username : str
        Username of the source repository.
    token : str
        Personal access token of the source repository.
    source_repo : str
        Source repository name.
    source_folder : str
        Source folder name.
    source_ref : str
        Source branch name.
    translations_repo : str
        .
    translations_folder : str
        .
    translations_ref : str
        .
    name : str
        Name of the bot account.
    email : str
        Email of the bot account.


        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          git config --global user.email "actions@github.com"
          git config --global user.name "GitHub Actions"
          ../automations/scripts/create_branch_for_language.sh origin main l10n_main ${{ github.event.inputs.language_code }}
          branch_name=$(git rev-parse --abbrev-ref HEAD)
          git push -u origin $branch_name
          echo "BRANCH_NAME=$branch_name" >> $GITHUB_ENV
        working-directory: ./scipy.org-translations

    """
    # Configure git information
    run(["git", "config", "--global", "user.name", f'"{name}"'])
    run(["git", "config", "--global", "user.email", f'"{email}"'])

    if source_ref:
        cmds = [
            "git",
            "clone",
            "--single-branch",
            "-b",
            source_ref,
            f"https://{username}:{token}@github.com/{source_repo}.git",
        ]
    else:
        cmds = [
            "git",
            "clone",
            f"https://{username}:{token}@github.com/{source_repo}.git",
        ]

    run(cmds)

    if translations_ref:
        cmds = [
            "git",
            "clone",
            "-b",
            translations_ref,
            f"https://{username}:{token}@github.com/{translations_repo}.git",
        ]
    else:
        cmds = [
            "git",
            "clone",
            f"https://{username}:{token}@github.com/{translations_repo}.git",
        ]

    run(cmds)
    run(["rsync", "-av", "--delete", source_folder, translations_folder])

    date_time = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    branch_name = f"content-sync-{date_time}"
    os.chdir(translations_repo.split("/")[1])
    print("\n\ngetcwd:", os.getcwd())

    run(["git", "checkout", "-b", branch_name])
    run(["git", "add", "."])
    _out, _err, rc = run(["git", "diff", "--staged", "--quiet"])

    pr_title = "Update content"
    github_token = os.environ.get("GITHUB_TOKEN", "")
    if rc:
        run(["git", "commit", "-S", "-m", "Update content."])
        run(["git", "remote", "-v"])
        run(["git", "push", "-u", "origin", branch_name])

        os.environ["GITHUB_TOKEN"] = token
        run(
            [
                "gh",
                "pr",
                "create",
                "--base",
                "main",
                "--head",
                branch_name,
                "--title",
                pr_title,
                "--body",
                "Automated content update.",
            ]
        )
        os.environ["GITHUB_TOKEN"] = github_token

        auth = Auth.Token(token)
        g = Github(auth=auth)
        repo = g.get_repo(translations_repo)
        pulls = repo.get_pulls(state="open", sort="created", direction="desc")
        pr_branch = None
        signed_by = f"{name} <{email}>"

        for pr in pulls:
            pr_branch = pr.head.ref
            if pr.title == pr_title and pr_branch == branch_name:
                print("\n\nFound PR try to merge it!")

                # Check if commits are signed
                checks = []
                for commit in pr.get_commits():
                    print(
                        [
                            commit.commit.verification.verified,
                            signed_by,
                            commit.commit.verification.payload,
                        ]
                    )
                    checks.append(
                        commit.commit.verification.verified
                        and signed_by in commit.commit.verification.payload
                    )

                if all(checks):
                    print("\n\nAll commits are signed, auto-merging!")
                    # https://cli.github.com/manual/gh_pr_merge
                    os.environ["GITHUB_TOKEN"] = token
                    run(["gh", "pr", "merge", branch_name, "--auto", "--squash"])
                else:
                    print("\n\nNot all commits are signed, abort merge!")

                break

        g.close()
    else:
        print("\n\nNo changes to commit.")


def parse_input() -> dict:
    gh_input = {
        # Automations Bot account
        "username": "scientificpythontranslations",
        # Provided by organization secrets
        "token": os.environ["TOKEN"],
        "crowdin_token": os.environ["CROWDIN_TOKEN"],
        # Provided by user action input
        "source_repo": os.environ["INPUT_SOURCE-REPO"],
        "source_folder": os.environ["INPUT_SOURCE-FOLDER"],
        "source_ref": os.environ["INPUT_SOURCE-REF"],
        "translations_repo": os.environ["INPUT_TRANSLATIONS-REPO"],
        "translations_folder": os.environ["INPUT_TRANSLATIONS-FOLDER"],
        "translations_ref": os.environ["INPUT_TRANSLATIONS-REF"],
        "crowdin_project": os.environ["INPUT_CROWDIN-PROJECT"],
        "approval_percentage": os.environ["INPUT_APPROVAL-PERCENTAGE"],
        "translation_percentage": os.environ["INPUT_TRANSLATION-PERCENTAGE"],
        "use_precommit": os.environ["INPUT_USE-PRECOMMIT"].lower() == "true",
        # Provided by gpg action based on organization secrets
        "name": os.environ["GPG_NAME"],
        "email": os.environ["GPG_EMAIL"],
    }
    return gh_input


def filter_commits(filename: str, language: str) -> None:
    """Edits the git-rebase-todo file to pick only commits for one language

    Used in GIT_SEQUENCE_EDITOR for scripted interactive rebase.

    Parameters
    ----------
    filename : str

    language : str
        Crowdin language.
    """
    # language = language_code_map[language_code.lower()]
    # print(filename, language)
    with open(filename) as f:
        lines = [line.strip().split(maxsplit=2) for line in f.readlines()]
    lines = [
        line
        for line in lines
        if line and line[0] == "pick" and f"({language})" in line[-1]
    ]
    output = "\n".join(" ".join(line) for line in lines) + "\n"
    with open(filename, "w") as f:
        f.write(output)


def create_translations_pr(
    token,
    source_repo,
    source_folder,
    source_ref,
    translations_repo,
    translations_folder,
    translations_ref,
    name,
    email,
    language,
    language_code,
):
    """Create a pull request for translations.

    Parameters
    ----------
    username : str
        Username of the source repository.
    token : str
        Personal access token of the source repository.
    source_repo : str
        Source repository name.
    source_folder : str
        Source folder name.
    source_ref : str
        Source branch name.
    translations_repo : str
        .
    translations_folder : str
        .
    translations_ref : str
        .
    name : str
        Name of the bot account.
    email : str
        Email of the bot account.
    language : str
        Language name.

    Returns
    -------
    out : str
        Output of the command.
    """
    print(f"\n\n### Creating PR for {language}")
    upstream_remote = "origin"
    source_branch = translations_ref
    crowdin_branch = "l10n_main"

    # TODO: Change working dir to the translations repo

    # Make sure source branch is up to date with upstream
    run(["git", "checkout", source_branch])
    run(["git", "fetch", upstream_remote])
    run(["git", "merge", "--ff-only", f"{upstream_remote}/{source_branch}"])

    # Make sure the corresponding Crowdin branch is up to date
    run(["git", "checkout", crowdin_branch])
    run(["git", "merge", "--ff-only", f"{upstream_remote}/{crowdin_branch}"])

    # Check that crowdin branch has no merge conflicts with respect to the source branch
    run(["git", "checkout", source_branch])
    _, _, rc = run(["git", "merge", "--no-commit", "--no-ff", crowdin_branch])
    if rc != 0:
        raise Exception("Merge conflict between source and crowdin branch.")

    run(["git", "merge", "--abort"])
    run(["git", "checkout", crowdin_branch])

    date_time = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    branch_name = f"{crowdin_branch}_{language_code}_{date_time}"

    # Checkout a new branch for these translations
    run(["git", "checkout", "-b", branch_name])

    # Run interactive rebase and cherry-pick only the commits for the language
    _, temp_bash_script = tempfile.mkstemp(
        suffix=".sh",
    )
    print(temp_bash_script)

    content = """#!/bin/bash
GIT_SEQUENCE_EDITOR="f() {{
    filename=\\$1
    python3 -c \\"
import sys
sys.path.insert(0, '{script_location}')
from main import filter_commits

filter_commits('\\$filename', '{language}')
\\"
}}; f" git rebase -i {source_branch}"""
    new_content = content.format(
        script_location=os.path.dirname(__file__),
        language=language,
        source_branch=source_branch,
    )

    with open(temp_bash_script, "w") as f:
        f.write(new_content)

    out, err, rc = run(["bash", temp_bash_script])

    if rc == 0:
        run(["git", "push", "-u", "origin", branch_name])
        pr_title = f"Update translations for {language}"
        os.environ["GITHUB_TOKEN"] = token
        run(
            [
                "gh",
                "pr",
                "create",
                "--base",
                "main",
                "--head",
                branch_name,
                "--title",
                pr_title,
                "--body",
                f"This PR to update translations for {language} was generated by the GitHub workflow, sync-translations.yml and includes all commits from this repo's Crowdin branch for the language of interest.",
            ]
        )

        auth = Auth.Token(token)
        g = Github(auth=auth)
        repo = g.get_repo(translations_repo)
        pulls = repo.get_pulls(state="open", sort="created", direction="desc")
        pr_branch = None
        signed_by = f"{name} <{email}>"

        for pr in pulls:
            pr_branch = pr.head.ref
            if pr.title == pr_title and pr_branch == branch_name:
                print("\n\nFound PR try to merge it!")

                # Check if commits are signed
                checks = []
                for commit in pr.get_commits():
                    print(
                        [
                            commit.commit.verification.verified,
                            signed_by,
                            commit.commit.verification.payload,
                        ]
                    )
                    checks.append(
                        commit.commit.verification.verified
                        and signed_by in commit.commit.verification.payload
                    )

                if all(checks):
                    print("\n\nAll commits are signed, auto-merging!")
                    # https://cli.github.com/manual/gh_pr_merge
                    os.environ["GITHUB_TOKEN"] = token
                    # run(["gh", "pr", "merge", branch_name, "--auto", "--squash"])
                else:
                    print("\n\nNot all commits are signed, abort merge!")

                break

        g.close()
    else:
        if rc != 0:
            print("\n\nNothing to cherry-pick.")
            print(out, err)


def configure_git_and_checkout_repos(
    username,
    token,
    source_repo,
    source_ref,
    translations_repo,
    translations_ref,
    name,
    email,
):
    """
    Configure git information and checkout repositories.

    Parameters
    ----------
    username : str
        Username of the source repository.
    token : str
        Personal access token of the source repository.
    source_repo : str
        Source repository name.
    source_ref : str
        Source branch name.
    translations_repo : str
        .
    translations_ref : str
        .
    name : str
        Name of the bot account.
    email : str
        Email of the bot account.
    """
    print("\n\n### Configure git information and checkout repositories")
    # Configure git information
    run(["git", "config", "--global", "user.name", f'"{name}"'])
    run(["git", "config", "--global", "user.email", f'"{email}"'])

    if source_ref:
        cmds = [
            "git",
            "clone",
            "--single-branch",
            "-b",
            source_ref,
            f"https://{username}:{token}@github.com/{source_repo}.git",
        ]
    else:
        cmds = [
            "git",
            "clone",
            f"https://{username}:{token}@github.com/{source_repo}.git",
        ]

    run(cmds)

    if translations_ref:
        cmds = [
            "git",
            "clone",
            "-b",
            translations_ref,
            f"https://{username}:{token}@github.com/{translations_repo}.git",
        ]
    else:
        cmds = [
            "git",
            "clone",
            f"https://{username}:{token}@github.com/{translations_repo}.git",
        ]

    run(cmds)

    os.chdir(translations_repo.split("/")[1])
    print("\n\ngetcwd:", os.getcwd())


def main():
    try:
        gh_input = parse_input()
        client = ScientificCrowdinClient(
            token=gh_input["crowdin_token"], organization="Scientific-python"
        )
        valid_languages = client.get_valid_languages(
            gh_input["crowdin_project"],
            int(gh_input["translation_percentage"]),
            int(gh_input["approval_percentage"]),
        )
        configure_git_and_checkout_repos(
            username=gh_input["username"],
            token=gh_input["token"],
            source_repo=gh_input["source_repo"],
            source_ref=gh_input["source_ref"],
            translations_repo=gh_input["translations_repo"],
            translations_ref=gh_input["translations_ref"],
            name=gh_input["name"],
            email=gh_input["email"],
        )
        for language_code, data in valid_languages.items():
            create_translations_pr(
                token=gh_input["token"],
                source_repo=gh_input["source_repo"],
                source_folder=gh_input["source_folder"],
                source_ref=gh_input["source_ref"],
                translations_repo=gh_input["translations_repo"],
                translations_folder=gh_input["translations_folder"],
                translations_ref=gh_input["translations_ref"],
                name=gh_input["name"],
                email=gh_input["email"],
                language=data["language_name"],
                language_code=language_code,
            )
    except Exception as e:
        print("Error: ", e)
        print(traceback.format_exc())
        raise e


if __name__ == "__main__":
    main()
