import json
import os
import traceback
from datetime import datetime
from subprocess import Popen, PIPE

from crowdin_api import CrowdinClient
from github import Github, Auth


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

    def get_languages(self):
        result = {}
        projects = self._client.projects.with_fetch_all().list_projects()
        for project in projects["data"]:
            result[project["data"]["name"]] = project["data"]["targetLanguageIds"]
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

    def get_projects_status(self):
        for project, project_id in self.get_projects().items():
            languages = self._client.translation_status.get_project_progress(
                project_id
            )["data"]
            for language in languages:
                language_name = language["data"]["language"]["name"]
                language_id = language["data"]["language"]["id"]
                progress = language["data"]["translationProgress"]
                approval = language["data"]["approvalProgress"]
                if progress > 0:
                    print(
                        f"{project} - {language_name} ({language_id}) - {progress}% / {approval}%"
                    )
            # print(json.dumps(languages, indent=4, default=str))

    def get_members(self):
        for project, project_id in self.get_projects().items():
            print(f"\n# {project}")
            members = self._client.users.list_project_members(project_id)["data"]
            for member in members:
                roles = member["data"]["roles"]
                permissions = member["data"]["permissions"]
                if roles and permissions:
                    role_names = ", ".join([role["name"] for role in roles])
                    permission_names = ", ".join([perm for perm in permissions])
                    # member_id = member["data"]["id"]
                    print(
                        f"{member['data']['username']} ({role_names}) {permission_names}"
                    )

            # print(json.dumps(members, indent=4, default=str))

    def get_translators(self):
        results = {}
        languages = self.get_languages()
        for project, project_id in sorted(self.get_projects().items()):
            results[project] = {}
            print(f"\n\n{project}")
            langs = languages[project]
            for lang in sorted(langs):
                results[project][lang] = {}
                users = set([])
                translation_ids = set([])
                offset = 0
                limit = 500
                while True:
                    items = self._client.string_translations.list_language_translations(
                        lang, project_id, limit=limit, offset=offset
                    )
                    if data := items["data"]:
                        # print(data)
                        for item in data:
                            users.add(item["data"]["user"]["username"])
                            translation_ids.add(item["data"]["translationId"])
                        # print(items['pagination'], items['data'])
                        offset += limit
                    else:
                        if users:
                            results[project][lang]["translators"] = sorted(users)
                            results[project][lang]["translation_ids"] = sorted(
                                translation_ids
                            )
                            print(lang, sorted(users))
                        else:
                            results[project][lang]["translation_ids"] = []
                        break

        return results

    def get_translations(self):
        results = {}
        languages = self.get_languages()
        for project, project_id in sorted(self.get_projects().items()):
            print(f"\n\n{project}")
            results[project] = {}
            langs = languages[project]
            for lang in sorted(langs):
                results[project][lang] = []
                users = set([])
                offset = 0
                limit = 500
                while True:
                    items = self._client.string_translations.list_language_translations(
                        lang, project_id, limit=limit, offset=offset
                    )
                    if data := items["data"]:
                        # print(data)
                        for item in data:
                            # print(item['data'])
                            results[project][lang].append(item["data"]["translationId"])
                            users.add(item["data"]["user"]["username"])
                        # print(items['pagination'], items['data'])
                        offset += limit
                    else:
                        if users:
                            print(lang, sorted(users))
                        break

        return results
        # FIXME: Return something useful

    def get_reviewers(self, translators):
        languages = self.get_languages()
        for project, project_id in sorted(self.get_projects().items()):
            print(f"\n\n{project}")
            langs = languages[project]
            for lang in sorted(langs):
                # users = set([])
                translation_ids = translators[project][lang]["translation_ids"]
                # offset = 0
                # limit = 500
                for trans_id in translation_ids:
                    items = self._client.string_translations.list_translation_approvals(
                        projectId=project_id, translationId=trans_id
                    )
                    if data := items["data"]:
                        print(data)
                # while True:
                #     items = self._client.string_translations.list_translation_approvals(projectId=project_id, languageId=lang, translationId=, limit=limit, offset=offset)
                #     if data := items['data']:
                #         # print(data)
                #         # for item in data:
                #         #     users.add(item['data']['user']['username'])
                #         print(items['pagination'], items['data'])
                #         offset += limit
                #     else:
                #         # if users:
                #             # print(lang, sorted(users))
                #         break

    def get_valid_languages(
        self, project_name, translation_percentage, approval_percentage
    ):
        """"""
        valid_languages = {}
        project_languages = self.get_project_status(project_name)
        print(json.dumps(project_languages, sort_keys=True, indent=4))
        for language_id, data in project_languages.items():
            approval = data["approval"]
            progress = data["progress"]
            language_name = data["language_name"]
            if progress >= translation_percentage and approval >= approval_percentage:
                print(f"\n{language_id} {language_name}:  {progress}% / {approval}%")
                valid_languages[language_id] = {
                    "language_name": language_name,
                    "progress": progress,
                    "approval": approval,
                }
        return valid_languages


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
    with open(filename) as f:
        lines = [line.strip().split(maxsplit=2) for line in f.readlines()]
    lines = [
        line for line in lines if line and line[0] == "pick" and language in line[-1]
    ]
    output = "\n".join(" ".join(line) for line in lines) + "\n"
    with open(filename, "w") as f:
        f.write(output)


def create_translations_pr(
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
    language,
):
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


"""
../automations/scripts/create_branch_for_language.sh origin main l10n_main ${{ github.event.inputs.language_code }}
          branch_name=$(git rev-parse --abbrev-ref HEAD)
          git push -u origin $branch_name
          echo "BRANCH_NAME=$branch_name" >> $GITHUB_ENV


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
"""


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
        for _language_id, data in valid_languages.items():
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
            )
            print(valid_languages)
    except Exception as e:
        print("Error: ", e)
        print(traceback.format_exc())
        raise e


if __name__ == "__main__":
    main()
