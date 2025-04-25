import yaml
import os
import traceback
import tempfile
from datetime import datetime
from subprocess import Popen, PIPE
from pathlib import Path
import shutil


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
        "source_folder": os.environ["INPUT_SOURCE-FOLDER"],
        "source_ref": os.environ["INPUT_SOURCE-REF"],
        "translations_repo": os.environ["INPUT_TRANSLATIONS-REPO"],
        "translations_folder": os.environ["INPUT_TRANSLATIONS-FOLDER"],
        "translations_ref": os.environ["INPUT_TRANSLATIONS-REF"],
        "crowdin_project": os.environ["INPUT_CROWDIN-PROJECT"],
        "approval_percentage": os.environ["INPUT_APPROVAL-PERCENTAGE"],
        "translation_percentage": os.environ["INPUT_TRANSLATION-PERCENTAGE"],
        "use_precommit": os.environ["INPUT_USE-PRECOMMIT"].lower() == "true",
        "create_toml_file": os.environ["INPUT_CREATE-TOML-FILE"].lower() == "true",
        # Provided by gpg action based on organization secrets
        "name": os.environ["GPG_NAME"],
        "email": os.environ["GPG_EMAIL"],
    }
    return gh_input


def run(cmds: list[str]) -> tuple[str, str, int]:
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
    stdout = out.decode()
    stderr = err.decode()
    print("\n\n\nCmd: \n" + " ".join(cmds))
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
    source_ref: str,
    translations_repo: str,
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
    print("\n\ngetcwd:", os.getcwd())
    run(["ls"])

    # Configure git information
    run(["git", "config", "--global", "user.name", f'"{name}"'])
    run(["git", "config", "--global", "user.email", f'"{email}"'])

    _owner, repo = source_repo.split("/")
    source_repo_fork = f"scientificpythontranslations/{repo}"
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

    run(cmds)
    print("\n\ngetcwd:", os.getcwd())
    run(["ls"])

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
    run(["ls"])


def verify_signature(
    token: str, repo: str, name: str, email: str, pr_title: str, branch_name: str
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
    source_folder: str,
    source_ref: str,
    translations_repo: str,
    translations_folder: str,
    translations_ref: str,
    name: str,
    email: str,
    language: str,
    language_code: str,
    use_precommit: bool = False,
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

    Returns
    -------
    out : str
        Output of the command.
    """
    print("\n\n### Folders")
    two_letter_lang_code = language_code[:2]
    base_folder = Path(os.getcwd())
    source_folder_path = str(Path(os.getcwd()).parent / source_repo.split("/")[1])
    source_folder_lang_path = base_folder.parent / source_folder
    trans_folder_path = (
        base_folder.parent / translations_folder
    ).parent / two_letter_lang_code
    print(f"\n\nbase_folder: {base_folder}")
    print(f"\n\nsource_folder_path: {source_folder_path}")
    print(f"\n\nsource_folder_lang_path: {source_folder_lang_path}")
    print(f"\n\ntrans_folder_path: {trans_folder_path}")

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
        prefix=f"git_sequence_editor_{language_code}_",
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

    # Copy files from the source folder to the translations folder
    # that are not in the translations folder
    trans_files = []
    for root, _dirs, files in os.walk(trans_folder_path):
        for name in files:
            trans_files.append(
                str(os.path.join(root, name)).replace(str(trans_folder_path), "")
            )

    print("\n\n### Checking files found in source but not in translations")
    for root, _dirs, files in os.walk(source_folder_lang_path):
        for name in files:
            file_path = str(os.path.join(root, name)).replace(
                str(source_folder_lang_path), ""
            )
            if file_path not in trans_files:
                source_copy = str(source_folder_lang_path) + file_path
                dest_copy = str(trans_folder_path) + file_path
                print("\n\nCopying file:", source_copy, dest_copy)
                shutil.copy(source_copy, dest_copy)

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

        if verify_signature(
            token=token,
            repo=translations_repo,
            name=name,
            email=email,
            pr_title=pr_title,
            branch_name=branch_name,
        ):
            print("\n\nAll commits are signed, auto-merging!")
            # https://cli.github.com/manual/gh_pr_merge
            os.environ["GITHUB_TOKEN"] = token
            # run(["gh", "pr", "merge", branch_name, "--auto", "--squash", '--delete-branch'])
        else:
            print("\n\nNot all commits are signed, abort merge!")

        # Create PR upstream
        translations_branch_name = f"add/translations-{language_code}"
        dest_path = (base_folder.parent / source_folder).parent
        os.chdir(source_folder_path)
        run(["git", "checkout", "-b", translations_branch_name])
        print("PATH:", trans_folder_path)
        run(["rsync", "-av", "--delete", str(trans_folder_path), str(dest_path)])
        run(["git", "add", "."])
        _out, _err, rc = run(["git", "diff", "--staged", "--quiet"])
        pr_title = f"Add translations for {language}"
        if rc:
            # run(["git", "commit", "-m", f"Add {language} translations."])
            run(["git", "commit", "-S", "-m", f"Add {language} translations."])

            if use_precommit:
                run(["pre-commit", "run", "--all-files"])
                run(["git", "add", "."])
                _out, _err, rc = run(["git", "diff", "--staged", "--quiet"])
                if rc:
                    # run(["git", "commit", "-m", "Run pre-commit."])
                    run(["git", "commit", "-S", "-m", "Run pre-commit."])

            run(["git", "push", "-u", "origin", translations_branch_name, "--force"])
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
                    f"This PR adds the translations for {language} to the project.\n\nThis PR was automatically created by the @scientificpythontranslations bot and no commits should be pushed directly to this branch/PR. Any modifications should be addressed directly in the https://scientific-python.crowdin.com/ site.\n\nThe Crowdin integration for this repository is located at https://github.com/{translations_repo}.",
                ]
            )
        run(["git", "checkout", "main"])
        os.chdir(base_folder)
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

    Returns
    -------
    translators : dict
        Dictionary with the updated translators information.
    """
    print("\n\n### Creating translators file")
    run(["git", "checkout", "-b", "add/translators-file"])
    existing_translators = translators
    if os.path.exists("translators.yml"):
        with open("translators.yml") as fh:
            existing_translators = yaml.safe_load(fh)

        for lang, translators_list in translators.items():
            if lang in existing_translators:
                for translator in translators_list:
                    if translator not in existing_translators[lang]:
                        existing_translators[lang].append(translator)
            else:
                existing_translators[lang] = translators_list

    with open("translators.yml", "w") as fh:
        fh.write(
            yaml.dump(
                existing_translators, default_flow_style=False, allow_unicode=True
            )
        )

    if create_toml_file:
        all_translators = []
        all_cards = []
        for lang, translators_list in existing_translators.items():
            for translator in translators_list:
                if translator not in all_translators:
                    all_translators.append(translator)
                    all_cards.append(
                        generate_card(
                            name=translator["name"],
                            img_link=translator["img_link"],
                        )
                    )

        with open("translations-team.toml", "w") as fh:
            fh.write("\n\n".join(all_cards))

    branch_name = "add/translators-file"
    pr_title = "Add/update translators file."
    run(["git", "add", "."])
    # run(["git", "commit", "-m", pr_title])
    run(["git", "commit", "-S", "-m", pr_title])
    run(["git", "push", "-u", "origin", branch_name, "--force"])
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
            "Update translations file.",
        ]
    )
    if verify_signature(
        token=token,
        repo=translations_repo,
        name=name,
        email=email,
        pr_title=pr_title,
        branch_name=branch_name,
    ):
        print("\n\nAll commits are signed, auto-merging!")
        # https://cli.github.com/manual/gh_pr_merge
        os.environ["GITHUB_TOKEN"] = token
        # run(["gh", "pr", "merge", branch_name, "--auto", "--squash", '--delete-branch'])
    else:
        print("\n\nNot all commits are signed, abort merge!")

    run(["git", "checkout", "main"])
    return existing_translators


def main() -> None:
    """Main function to run the script."""
    try:
        gh_input = parse_input()
        crowdin_project = gh_input["crowdin_project"]
        client = ScientificCrowdinClient(
            token=gh_input["crowdin_token"], organization="Scientific-python"
        )
        valid_languages = client.get_valid_languages(
            crowdin_project,
            int(gh_input["translation_percentage"]),
            int(gh_input["approval_percentage"]),
        )
        translators = client.get_project_translators(
            crowdin_project,
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
        create_translators_file(
            translators,
            token=gh_input["token"],
            name=gh_input["name"],
            email=gh_input["email"],
            translations_repo=gh_input["translations_repo"],
            create_toml_file=gh_input["create_toml_file"],
        )
        for language_code, data in valid_languages.items():
            create_translations_pr(
                username=gh_input["username"],
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
                use_precommit=gh_input["use_precommit"],
            )
    except Exception as e:
        print("Error: ", e)
        print(traceback.format_exc())
        raise e


if __name__ == "__main__":
    main()
