import yaml
import os
import traceback
import tempfile
import shutil

from datetime import datetime
from subprocess import Popen, PIPE
from pathlib import Path
from typing import Optional, Union
from crowdin_api import CrowdinClient  # type: ignore
from github import Github, Auth
from dotenv import load_dotenv


load_dotenv()  # take environment variables


def parse_input() -> dict:
    gh_input = {
        # Automations Bot account
        "username": "scientificpythontranslations",
        # Provided by organization secrets
        "token": os.environ["TOKEN"],
        "crowdin_token": os.environ["CROWDIN_TOKEN"],
        # Provided by user action input
        "source_repo": os.environ["INPUT_SOURCE-REPO"],
        "source_path": os.environ["INPUT_SOURCE-PATH"],
        "source_ref": os.environ["INPUT_SOURCE-REF"],
        "translations_repo": os.environ["INPUT_TRANSLATIONS-REPO"],
        "translations_path": os.environ["INPUT_TRANSLATIONS-PATH"],
        "translations_source_path": os.environ["INPUT_TRANSLATIONS-SOURCE-PATH"],
        "translations_ref": os.environ["INPUT_TRANSLATIONS-REF"],
        "crowdin_project": os.environ["INPUT_CROWDIN-PROJECT"],
        "approval_percentage": os.environ["INPUT_APPROVAL-PERCENTAGE"],
        "translation_percentage": os.environ["INPUT_TRANSLATION-PERCENTAGE"],
        "use_precommit": os.environ["INPUT_USE-PRECOMMIT"].lower() == "true",
        "create_toml_file": os.environ["INPUT_CREATE-TOML-FILE"].lower() == "true",
        "create_upstream_pr": os.environ["INPUT_CREATE-UPSTREAM-PR"].lower() == "true",
        "auto_merge": os.environ["INPUT_AUTO-MERGE"].lower() == "true",
        # Provided by gpg action based on organization secrets
        "name": os.environ["GPG_NAME"],
        "email": os.environ["GPG_EMAIL"],
        "run_local": os.environ.get("RUN_LOCAL", "False").lower() == "true",
    }
    return gh_input


def run(
    cmds: list[str], cwd: Optional[Union[str, Path]] = None
) -> tuple[str, str, int]:
    """Run a command in the shell and print the standard output, error and return code.

    Parameters
    ----------
    cmds : list
        List of commands to run.
    cwd : str, optional
        Current working directory to run the command in. If None, use the current working directory.

    Returns
    -------
    out : str
        Output of the command.
    err : str
        Error of the command.
    rc : int
        Return code of the command.
    """
    p = Popen(cmds, stdout=PIPE, stderr=PIPE, cwd=cwd)
    out, err = p.communicate()
    stdout = out.decode()
    stderr = err.decode()
    print("\n\n\nCmd: \n" + " ".join(cmds))
    print("Cwd: \n", cwd or os.getcwd())
    print("Out: \n", stdout)
    print("Err: \n", stderr)
    print("Code: \n", p.returncode)
    return stdout, stderr, p.returncode


def generate_card(
    name: str,
    img_link: str,
    link: str = "https://scientific-python-translations.github.io/contributors/",
) -> str:
    """
    Generate a card in TOML format.
    """
    toml_card_template = """[[item]]
type = 'card'
classcard = 'text-center'
body = '''{{{{< image >}}}}
src = '{img_link}'
alt = 'Avatar of {name}'
{{{{< /image >}}}}
{name}'''
link = '{link}'"""
    return toml_card_template.format(
        img_link=img_link,
        name=name,
        link=link,
    )


class ScientificCrowdinClient:

    def __init__(self, token: str, organization: str):
        self._token = token
        self._organization = organization
        self._client = CrowdinClient(token=token, organization=organization)

    def get_projects(self) -> dict:
        """Get projects from Crowdin."""
        result = {}
        projects = self._client.projects.with_fetch_all().list_projects()
        for project in projects["data"]:
            result[project["data"]["name"]] = project["data"]["id"]
        return result

    def get_project_id(self, project_name: str) -> int:
        """Get project ID from Crowdin."""
        projects = self._client.projects.with_fetch_all().list_projects()
        for project in projects["data"]:
            if project["data"]["name"] == project_name:
                return project["data"]["id"]
        else:
            raise ValueError(f"Project '{project_name}' not found.")

    def get_project_status(self, project_name: str) -> dict:
        """Get project status from Crowdin."""
        results = {}
        for p_name, project_id in self.get_projects().items():
            if project_name != p_name:
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

    def get_project_languages(self, project_name: str) -> list:
        """Get project languages from Crowdin."""
        projects = self._client.projects.with_fetch_all().list_projects()
        for project in projects["data"]:
            if project["data"]["name"] == project_name:
                return project["data"]["targetLanguageIds"]
        else:
            raise ValueError(f"Project '{project_name}' not found.")

    def get_valid_languages(
        self, project_name: str, translation_percentage: int, approval_percentage: int
    ) -> dict:
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

    def get_project_translators(self, project_name: str) -> dict:
        """Get project translators from Crowdin."""
        results: dict = {}
        project_id = self.get_project_id(project_name)
        languages = self.get_project_languages(project_name)
        for lang in sorted(languages):
            results[lang] = []
            offset = 0
            limit = 500
            while True:
                items = self._client.string_translations.list_language_translations(
                    lang, project_id, limit=limit, offset=offset
                )
                if data := items["data"]:
                    for item in data:
                        user_data = {
                            "username": item["data"]["user"]["username"],
                            "name": item["data"]["user"]["fullName"],
                            "img_link": item["data"]["user"]["avatarUrl"].replace(
                                "/medium/", "/large/"
                            ),
                        }
                        if user_data not in results[lang]:
                            results[lang].append(user_data)
                    offset += limit
                else:
                    break

        return results


def configure_git_and_checkout_repos(
    username: str,
    token: str,
    source_repo: str,
    source_path: str,
    source_ref: str,
    translations_repo: str,
    translations_path: str,
    translations_source_path: str,
    translations_ref: str,
    name: str,
    email: str,
) -> None:
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
    os.environ["GITHUB_TOKEN"] = token
    print("\n\n### Configure git information and checkout repositories")

    base_path = Path(os.getcwd())
    base_source_path = base_path / source_repo.split("/")[-1]
    src_path = base_source_path / source_path

    base_translations_path = base_path / translations_repo.split("/")[-1]
    trans_source_path = base_translations_path / translations_source_path
    trans_path = base_translations_path / translations_path

    print("\n\nBase path:\n", base_path)
    print("\n\nBase source path:\n", base_source_path)
    print("\n\nSource path:\n", src_path)
    print("\n\nBase translations path:\n", base_translations_path)
    print("\n\nTranslations path:\n", trans_path)
    print("\n\nTranslations source path:\n", trans_source_path)

    owner, repo = source_repo.split("/")
    source_repo_fork = f"scientificpythontranslations/{repo}"
    upstream = f"https://github.com/{owner}/{repo}.git"
    run(["gh", "repo", "fork", source_repo, "--clone=false"])

    if source_ref:
        cmds = [
            "git",
            "clone",
            "--single-branch",
            "-b",
            source_ref,
            f"https://{username}:{token}@github.com/{source_repo_fork}.git",
        ]
    else:
        cmds = [
            "git",
            "clone",
            f"https://{username}:{token}@github.com/{source_repo}.git",
        ]

    run(cmds, cwd=base_path)

    # Keep the bots fork in sync with the upstream repo
    run(["git", "remote", "add", "upstream", upstream], cwd=base_source_path)
    run(["git", "checkout", source_ref], cwd=base_source_path)
    run(["git", "pull", "upstream", source_ref], cwd=base_source_path)
    run(["git", "push", "origin", source_ref], cwd=base_source_path)

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

    run(cmds, cwd=base_path)

    # Configure git information
    for path in [base_translations_path, base_source_path]:
        run(["git", "config", "user.name", f'"{name}"'], cwd=path)
        run(["git", "config", "user.email", f'"{email}"'], cwd=path)


def verify_signature(
    token: str,
    repo: str,
    name: str,
    email: str,
    pr_title: str,
    branch_name: str,
    run_local: bool = False,
) -> bool:
    """Verify the signature of the pull request.

    Parameters
    ----------
    token : str

    repo : str
        Repository name.
    name : str
        Name of the bot account.
    email : str
        Email of the bot account.
    pr_title : str
        Title of the pull request.
    branch_name : str
        Branch name of the pull request.
    """
    if run_local:
        return True

    auth = Auth.Token(token)
    g = Github(auth=auth)
    pulls = g.get_repo(repo).get_pulls(state="open", sort="created", direction="desc")
    pr_branch = None
    signed_by = f"{name} <{email}>"
    checks = []
    for pr in pulls:
        pr_branch = pr.head.ref
        if pr.title == pr_title and pr_branch == branch_name:
            print("\n\nFound PR try to merge it!")
            # Check if commits are signed
            for commit in pr.get_commits():
                print(
                    [
                        commit.commit.verification.verified,  # type: ignore
                        signed_by,
                        commit.commit.verification.payload,  # type: ignore
                    ]
                )
                checks.append(
                    commit.commit.verification.verified  # type: ignore
                    and signed_by in commit.commit.verification.payload  # type: ignore
                )
            break

    g.close()
    return all(checks)


def filter_commits(filename: str, language: str) -> None:
    """Edits the git-rebase-todo file to pick only commits for one language.

    Used in GIT_SEQUENCE_EDITOR for scripted interactive rebase.

    Parameters
    ----------
    filename : str

    language : str
        Crowdin language.
    """
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
    username: str,
    token: str,
    source_repo: str,
    source_path: str,
    source_ref: str,
    translations_repo: str,
    translations_path: str,
    translations_source_path: str,
    translations_ref: str,
    name: str,
    email: str,
    all_languages: list,
    language: str,
    language_code: str,
    create_upstream_pr: bool = False,
    use_precommit: bool = False,
    auto_merge: bool = False,
    project_id: int = 0,
    run_local: bool = False,
) -> None:
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
    language_code : str
        Language code.
    create_upstream_pr : bool
        Whether to create a pull request upstream.
    use_precommit : bool
        Whether to use pre-commit.
    auto_merge : bool
        Whether to auto-merge the pull request.

    Returns
    -------
    out : str
        Output of the command.
    """
    base_path = Path(os.getcwd())
    base_source_path = base_path / source_repo.split("/")[-1]
    base_translations_path = base_path / translations_repo.split("/")[-1]
    trans_path = base_translations_path / translations_path
    trans_source_path = base_translations_path / translations_source_path
    trans_lang_path = base_translations_path / translations_path / language_code[:2]
    src_path = base_source_path / source_path

    print(language_code)
    print(
        "\n\n### Syncing content from source repository to translations repository.\n\n"
    )
    print("\n\nBase path:\n", base_path)
    print("\n\nBase source path:\n", base_source_path)
    print("\n\nSource path:\n", source_path)
    print("\n\nBase translations path:\n", base_translations_path)
    print("\n\nTranslations path:\n", trans_path)
    print("\n\nTranslations source path:\n", trans_source_path)
    print("\n\nTranslations language path:\n", trans_lang_path)

    print(f"\n\n### Creating PR for {language}")
    upstream_remote = "origin"
    source_branch = translations_ref
    crowdin_branch = "l10n_main"

    # Make sure source branch is up to date with upstream
    run(["git", "checkout", source_branch], cwd=base_translations_path)
    run(["git", "fetch", upstream_remote], cwd=base_translations_path)
    run(
        ["git", "merge", "--ff-only", f"{upstream_remote}/{source_branch}"],
        cwd=base_translations_path,
    )

    # Make sure the corresponding Crowdin branch is up to date
    run(["git", "checkout", crowdin_branch], cwd=base_translations_path)
    run(
        ["git", "merge", "--ff-only", f"{upstream_remote}/{crowdin_branch}"],
        cwd=base_translations_path,
    )

    # Check that crowdin branch has no merge conflicts with respect to the source branch
    run(["git", "checkout", source_branch], cwd=base_translations_path)
    _, _, rc = run(
        ["git", "merge", "--no-commit", "--no-ff", crowdin_branch],
        cwd=base_translations_path,
    )
    if rc != 0:
        raise Exception("Merge conflict between source and crowdin branch.")

    run(["git", "merge", "--abort"], cwd=base_translations_path)
    run(["git", "checkout", crowdin_branch], cwd=base_translations_path)

    date_time = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    branch_name = f"{crowdin_branch}_{language_code}_{date_time}"

    # Checkout a new branch for these translations
    run(["git", "checkout", "-b", branch_name], cwd=base_translations_path)

    # Run interactive rebase and cherry-pick only the commits for the language
    _, temp_bash_script = tempfile.mkstemp(
        prefix=f"git_sequence_editor_{language_code}_",
        suffix=".sh",
    )

    content = """#!/bin/bash
GIT_SEQUENCE_EDITOR="f() {{
    filename=\\$1
    python3 -c \\"
import sys
sys.path.insert(0, '{script_location}')
from main import filter_commits

filter_commits('\\$filename', '{language}')
\\"
}}; f" git rebase -i {source_branch} --reapply-cherry-picks"""
    new_content = content.format(
        script_location=os.path.dirname(__file__),
        language=language,
        source_branch=source_branch,
    )

    with open(temp_bash_script, "w") as f:
        f.write(new_content)

    print(run(["git", "status"], cwd=str(base_translations_path)))
    out, err, rc_cherry_pick = run(
        ["bash", temp_bash_script], cwd=base_translations_path
    )
    while rc_cherry_pick == 1:
        if "git rebase --skip" in err:
            _, err, rc_cherry_pick = run(
                ["git", "rebase", "--skip"], cwd=base_translations_path
            )
        else:
            break

    # Copy files from the source folder to the translations folder
    # that are not in the translations folder
    trans_files = []
    for root, _dirs, files in os.walk(trans_lang_path):
        for fname in files:
            trans_files.append(
                str(os.path.join(root, fname)).replace(str(trans_lang_path), "")
            )
    print("\n\n### Files in translations folder")
    for g in trans_files:
        print(g)

    # lang_prefix = [f"/{lp}/" for lp in all_languages]
    print("\n\n### Checking files found in source but not in translations")
    for root, _dirs, files in os.walk(src_path):
        for fname in files:
            file_path = str(os.path.join(root, fname)).replace(str(src_path), "")
            # if file_path not in trans_files and check:
            if file_path not in trans_files:
                source_copy = str(src_path) + file_path
                dest_copy = str(trans_lang_path) + file_path
                print("\n\nCopying file:", source_copy, dest_copy)
                os.makedirs(os.path.dirname(dest_copy), exist_ok=True)
                shutil.copy(source_copy, dest_copy)

    run(["git", "add", "."], cwd=base_translations_path)
    _out, _err, rc = run(
        ["git", "diff", "--staged", "--quiet"], cwd=base_translations_path
    )
    if rc:
        if run_local:
            run(
                ["git", "commit", "-m", "Add untranslated files."],
                cwd=base_translations_path,
            )
        else:
            run(
                ["git", "commit", "-S", "-m", "Add untranslated files."],
                cwd=base_translations_path,
            )

    if rc_cherry_pick == 0:
        run(["git", "push", "-u", "origin", branch_name], cwd=base_translations_path)
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
                f"This PR to update translations for {language} was generated by the GitHub workflow, `.github/workflows/sync_translations.yml` and includes all commits from this repo's Crowdin branch for the language of interest.",
            ],
            cwd=base_translations_path,
        )

        if auto_merge:
            if verify_signature(
                token=token,
                repo=translations_repo,
                name=name,
                email=email,
                pr_title=pr_title,
                branch_name=branch_name,
                run_local=run_local,
            ):
                print("\n\nAll commits are signed, auto-merging!")
                # https://cli.github.com/manual/gh_pr_merge
                os.environ["GITHUB_TOKEN"] = token
                run(
                    ["gh", "pr", "merge", branch_name, "--auto", "--squash"],
                    cwd=base_translations_path,
                )
            else:
                print("\n\nNot all commits are signed, abort merge!")

        # Create PR upstream
        if create_upstream_pr:
            # Make sure the repo is up to date

            translations_branch_name = f"add/translations-{language_code}"
            run(
                ["git", "checkout", "-b", translations_branch_name],
                cwd=base_source_path,
            )
            # rsync /var/www/ /home/var - copies the contents of /var/www/ but not the www folder itself.
            # rsync /var/www /home/var - copies the folder www along with all its contents.
            run(
                [
                    "rsync",
                    "-av",
                    "--delete",
                    str(trans_lang_path),
                    str(base_source_path / translations_path),
                ]
            )
            run(["git", "add", "."], cwd=base_source_path)
            _out, _err, rc = run(
                ["git", "diff", "--staged", "--quiet"], cwd=base_source_path
            )
            pr_title = f"Add translations for {language}"
            if rc:
                if run_local:
                    run(
                        ["git", "commit", "-m", f"Add {language} translations."],
                        cwd=base_source_path,
                    )
                else:
                    run(
                        ["git", "commit", "-S", "-m", f"Add {language} translations."],
                        cwd=base_source_path,
                    )

                if use_precommit:
                    run(["pre-commit", "run", "--all-files"], cwd=base_source_path)
                    run(["git", "add", "."], cwd=base_source_path)
                    _out, _err, rc = run(
                        ["git", "diff", "--staged", "--quiet"], cwd=base_source_path
                    )
                    if rc:
                        if run_local:
                            run(
                                ["git", "commit", "-m", "Run pre-commit."],
                                cwd=base_source_path,
                            )
                        else:
                            run(
                                ["git", "commit", "-S", "-m", "Run pre-commit."],
                                cwd=base_source_path,
                            )

                run(
                    [
                        "git",
                        "push",
                        "-u",
                        "origin",
                        translations_branch_name,
                        "--force",
                    ],
                    cwd=base_source_path,
                )
                os.environ["GITHUB_TOKEN"] = token
                # gh pr create --repo owner/repo --base master --head user:patch-1
                run(
                    [
                        "gh",
                        "pr",
                        "create",
                        "--repo",
                        source_repo,
                        "--base",
                        "main",
                        "--head",
                        f"{username}:{translations_branch_name}",
                        "--title",
                        pr_title,
                        "--body",
                        f"This PR adds the translations for {language} to the project.\n\nThis PR was automatically created by the @scientificpythontranslations bot and only commits that resolve any merge conflicts should be pushed directly to this branch/PR. Any modifications of the translated content should be addressed directly on the [Crowdin Project Site](https://scientific-python.crowdin.com/u/projects/{project_id}/l/{language_code}).\n\nThe Crowdin integration for this repository is located at https://github.com/{translations_repo}.",
                    ],
                    cwd=base_source_path,
                )
            run(["git", "checkout", "main"], cwd=base_source_path)
        else:
            if rc != 0:
                print("\n\nNothing to cherry-pick.")
                print(out, err)


def create_translators_file(
    translators: dict,
    token: str,
    name: str,
    email: str,
    translations_repo: str,
    create_toml_file: bool = False,
    auto_merge: bool = False,
    run_local: bool = False,
) -> dict:
    """Create a file with the translators information.

    Parameters
    ----------
    translators : dict
        Dictionary with the translators information.
    token : str
        Personal access token of the source repository.
    name : str
        Name of the bot account.
    email : str
        Email of the bot account.
    translations_repo : str
        .
    create_toml_file : bool
        Whether to create a TOML file with the translators information.
    auto_merge : bool
        Whether to auto-merge the pull request.

    Returns
    -------
    translators : dict
        Dictionary with the updated translators information.
    """
    print("\n\n### Creating translators file")
    base_path = Path(os.getcwd())
    base_translations_path = base_path / translations_repo.split("/")[-1]
    run(["git", "checkout", "main"], cwd=base_translations_path)
    run(["git", "checkout", "-b", "add/translators-file"], cwd=base_translations_path)
    existing_translators = translators
    with open(f"{base_translations_path}/translators.yml", "w") as fh:
        fh.write(
            yaml.dump(
                existing_translators, default_flow_style=False, allow_unicode=True
            )
        )

    if create_toml_file:
        print("\n\n### Creating toml file")
        all_translators = []
        all_cards = []
        for _lang, translators_list in existing_translators.items():
            for translator in translators_list:
                if translator not in all_translators:
                    all_translators.append(translator)
                    all_cards.append(
                        generate_card(
                            name=translator["name"],
                            img_link=translator["img_link"],
                        )
                    )

        fname = "translations-team.toml"
        with open(f"{base_translations_path}/{fname}", "w") as fh:
            fh.write("\n\n".join(all_cards))

        run(["git", "add", fname], cwd=base_translations_path)

    branch_name = "add/translators-file"
    pr_title = "Add/update translators file."

    fname = "translators.yml"
    run(["git", "add", fname], cwd=base_translations_path)
    if run_local:
        run(["git", "commit", "-m", pr_title], cwd=base_translations_path)
    else:
        run(["git", "commit", "-S", "-m", pr_title], cwd=base_translations_path)

    run(
        ["git", "push", "-u", "origin", branch_name, "--force"],
        cwd=base_translations_path,
    )
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
            "Update translators file.",
        ],
        cwd=base_translations_path,
    )
    if auto_merge:
        if verify_signature(
            token=token,
            repo=translations_repo,
            name=name,
            email=email,
            pr_title=pr_title,
            branch_name=branch_name,
            run_local=run_local,
        ):
            print("\n\nAll commits are signed, auto-merging!")
            # https://cli.github.com/manual/gh_pr_merge
            os.environ["GITHUB_TOKEN"] = token
            run(
                ["gh", "pr", "merge", branch_name, "--auto", "--squash"],
                cwd=base_translations_path,
            )
        else:
            print("\n\nNot all commits are signed, abort merge!")

    run(["git", "checkout", "main"], cwd=base_translations_path)
    return existing_translators


def create_status_file(
    status: dict,
    token: str,
    name: str,
    email: str,
    translations_repo: str,
    auto_merge: bool = False,
    run_local: bool = False,
):
    """Create a file with the translators information.

    Parameters
    ----------
    translators : dict
        Dictionary with the translators information.
    token : str
        Personal access token of the source repository.
    name : str
        Name of the bot account.
    email : str
        Email of the bot account.
    translations_repo : str
        .
    create_toml_file : bool
        Whether to create a TOML file with the translators information.
    auto_merge : bool
        Whether to auto-merge the pull request.

    Returns
    -------
    translators : dict
        Dictionary with the updated translators information.
    """
    print("\n\n### Creating status file")
    base_path = Path(os.getcwd())
    base_translations_path = base_path / translations_repo.split("/")[-1]
    run(["git", "checkout", "main"], cwd=base_translations_path)
    run(["git", "checkout", "-b", "add/status-file"], cwd=base_translations_path)
    with open(f"{base_translations_path}/status.yml", "w") as fh:
        fh.write(yaml.dump(status, default_flow_style=False, allow_unicode=True))

    branch_name = "add/status-file"
    pr_title = "Add/update status file."
    fname = "status.yml"
    run(["git", "add", fname], cwd=base_translations_path)
    if run_local:
        run(["git", "commit", "-m", pr_title], cwd=base_translations_path)
    else:
        run(["git", "commit", "-S", "-m", pr_title], cwd=base_translations_path)

    run(
        ["git", "push", "-u", "origin", branch_name, "--force"],
        cwd=base_translations_path,
    )
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
            "Update status file.",
        ],
        cwd=base_translations_path,
    )
    if auto_merge:
        if verify_signature(
            token=token,
            repo=translations_repo,
            name=name,
            email=email,
            pr_title=pr_title,
            branch_name=branch_name,
            run_local=run_local,
        ):
            print("\n\nAll commits are signed, auto-merging!")
            # https://cli.github.com/manual/gh_pr_merge
            os.environ["GITHUB_TOKEN"] = token
            run(
                ["gh", "pr", "merge", branch_name, "--auto", "--squash"],
                cwd=base_translations_path,
            )
        else:
            print("\n\nNot all commits are signed, abort merge!")

    run(["git", "checkout", "main"], cwd=base_translations_path)


def main() -> None:
    """Main function to run the script."""
    try:
        gh_input = parse_input()
        crowdin_project = gh_input["crowdin_project"]
        client = ScientificCrowdinClient(
            token=gh_input["crowdin_token"], organization="Scientific-python"
        )
        project_id = client.get_project_id(crowdin_project)
        all_languages = client.get_project_languages(crowdin_project)
        all_languages = [lang[:2] for lang in all_languages]
        project_status = client.get_project_status(crowdin_project)
        valid_languages = client.get_valid_languages(
            crowdin_project,
            int(gh_input["translation_percentage"]),
            int(gh_input["approval_percentage"]),
        )
        print(valid_languages)
        translators = client.get_project_translators(
            crowdin_project,
        )
        configure_git_and_checkout_repos(
            username=gh_input["username"],
            token=gh_input["token"],
            source_repo=gh_input["source_repo"],
            source_path=gh_input["source_path"],
            source_ref=gh_input["source_ref"],
            translations_repo=gh_input["translations_repo"],
            translations_path=gh_input["translations_path"],
            translations_source_path=gh_input["translations_source_path"],
            translations_ref=gh_input["translations_ref"],
            name=gh_input["name"],
            email=gh_input["email"],
        )
        for language_code, data in valid_languages.items():
            create_translations_pr(
                username=gh_input["username"],
                token=gh_input["token"],
                source_repo=gh_input["source_repo"],
                source_path=gh_input["source_path"],
                source_ref=gh_input["source_ref"],
                translations_repo=gh_input["translations_repo"],
                translations_path=gh_input["translations_path"],
                translations_source_path=gh_input["translations_source_path"],
                translations_ref=gh_input["translations_ref"],
                name=gh_input["name"],
                email=gh_input["email"],
                all_languages=all_languages,
                language=data["language_name"],
                language_code=language_code,
                use_precommit=gh_input["use_precommit"],
                create_upstream_pr=gh_input["create_upstream_pr"],
                auto_merge=gh_input["auto_merge"],
                project_id=project_id,
                run_local=gh_input["run_local"],
            )
        create_translators_file(
            translators,
            token=gh_input["token"],
            name=gh_input["name"],
            email=gh_input["email"],
            translations_repo=gh_input["translations_repo"],
            create_toml_file=gh_input["create_toml_file"],
            auto_merge=gh_input["auto_merge"],
            run_local=gh_input["run_local"],
        )
        create_status_file(
            status=project_status,
            token=gh_input["token"],
            name=gh_input["name"],
            email=gh_input["email"],
            translations_repo=gh_input["translations_repo"],
            auto_merge=gh_input["auto_merge"],
            run_local=gh_input["run_local"],
        )
    except Exception as e:
        print("Error: ", e)
        print(traceback.format_exc())
        raise e


if __name__ == "__main__":
    main()
