# translations-sync

**A GitHub Action to synchronize translated content from Crowdin into Scientific Python project repositories.**

This action automates the process of fetching translated content from [Crowdin](https://crowdin.com/) and integrating it into the appropriate branches of translation repositories. It is designed to work seamlessly with the [Scientific Python Translations](https://scientific-python-translations.github.io/) infrastructure.

---

## 📦 Features

- **Automated Translation Syncing**: Periodically syncs translated content from Crowdin to the specified GitHub repository.
- **Customizable Configuration**: Supports specifying source and translation repositories, folder paths, branches, and more.
- **Integration with Crowdin**: Fetches translations based on specified thresholds for translation and approval percentages.
- **GitHub Actions Workflow**: Easily integrate into existing CI/CD pipelines using GitHub Actions.

## 🚀 Getting Started

### Prerequisites

- A Crowdin project set up for your content.
- A separate translations repository set up to receive and manage translated content part of the Scientific Python Translations organization.
- GitHub Actions enabled on the repository.

## ⚙️ Usage

### Basic Example

Here's a sample GitHub Actions workflow that uses the `translations-sync` action to sync translations for the `numpy.org` website:

```yaml
name: Sync Translations

on:
  schedule:
    - cron: "0 12 * * MON" # Every Monday at noon
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Sync NumPy.Org translations
        uses: Scientific-Python-Translations/translations-sync@main
        with:
          # Provided by user
          crowdin-project: "NumPy.Org"
          source-repo: "numpy/numpy.org"
          source-folder: "numpy.org/content/en/"
          source-ref: "main"
          translations-repo: "Scientific-Python-Translations/numpy.org-translations"
          translations-folder: "numpy.org-translations/content/en/"
          translations-ref: "main"
          translation-percentage: "90"
          approval-percentage: "0"
          use-precommit: "true"
          create-toml-file: "true"
          # Provided by organization secrets
          gpg-private-key: ${{ secrets.GPG_PRIVATE_KEY }}
          passphrase: ${{ secrets.PASSPHRASE }}
          token: ${{ secrets.TOKEN }}
          crowdin-token: ${{ secrets.CROWDIN_TOKEN }}
```

### Inputs

| Input                    | Required | Default | Description                                                                     |
| ------------------------ | -------- | ------- | ------------------------------------------------------------------------------- |
| `crowdin-project`        | ✅       | —       | The identifier of the Crowdin project.                                          |
| `source-repo`            | ✅       | —       | The GitHub repository containing the source content (e.g., `scipy/scipy.org`).  |
| `source-folder`          | ✅       | —       | The folder path within the source repository to sync from.                      |
| `source-ref`             | ❌       | `main`  | The branch or tag in the source repository to sync from.                        |
| `translations-repo`      | ✅       | —       | The GitHub repository to sync the translated content into.                      |
| `translations-folder`    | ✅       | —       | The folder path within the translations repository to place the synced content. |
| `translations-ref`       | ❌       | `main`  | The branch in the translations repository to sync into.                         |
| `translation-percentage` | ❌       | `90`    | Minimum translation percentage required to include translated content.          |
| `approval-percentage`    | ❌       | `0`     | Minimum approval percentage required to include translated content.             |
| `use-precommit`          | ❌       | `false` | Whether to run pre-commit hooks on the translated content.                      |
| `create-toml-file`       | ❌       | `false` | Whether to create toml file with cards for the translators and contributors.    |

## 🛠️ Setup Instructions

1. **Create a Translations Repository**: Set up a separate repository to hold the translated content. You can use the [translations-cookiecutter](https://github.com/Scientific-Python-Translations/translations-cookiecutter) as template for the repository.

2. **Configure Crowdin**: Integrate your translations repository with Crowdin to manage translations. Ensure that the `translations-folder` is set up correctly for Crowdin.

3. **Set Up the Workflow**: Add the above GitHub Actions workflow to your source repository (e.g., `.github/workflows/sync-translations.yml`). This is created automatically if you used the `translations-cookiecutter`.

## 🔄 How It Works

1. **Fetch Translations**: The action fetches translated files from the specified Crowdin project, filtering based on the provided translation and approval percentages.

2. **Checkout Repositories**: It checks out the specified source and translations repositories and branches.

3. **Integrate Translations**: The action integrates the fetched translations into the specified folder within the translations repository.

4. **Optional Pre-commit Hooks**: If enabled, it runs pre-commit hooks on the synced content.

5. **Commit and PR Creation**: The action commits the changes with the specified and creates a Pull Request with signed commits back on the source repository per language. An additional PR will be created on the translations repo to inlcude a `translators.yml` with information of all translators and contributors. If `create-toml-file` is enabled, the PR will include a `translators-team.toml` file.

## 🤖 Bot Activity

All synchronization pull requests and automated commits are performed by the dedicated bot account:
[@scientificpythontranslations](https://github.com/scientificpythontranslations)

This ensures consistent and traceable contributions from a centralized automation identity.
If you need to grant permissions or configure branch protection rules, make sure to allow actions and PRs from this bot.

## 🙌 Community & Support

- Join the [Scientific Python Discord](https://scientific-python.org/community/) and visit the `#translation` channel
- Browse the [Scientific Python Translations documentation](https://scientific-python-translations.github.io/docs/)
- Visit the [content-sync](https://github.com/Scientific-Python-Translations/content-sync) and [translations-sync](https://github.com/Scientific-Python-Translations/translations-sync) Github actions.

## 🤝 Contributing

Contributions are welcome! Please open an issue or submit a pull request for any enhancements or bug fixes.

## 📄 License

This project is licensed under the [MIT License](LICENSE.txt).
