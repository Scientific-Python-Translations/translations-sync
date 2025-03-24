# translations-sync

Github action to sync up translated content for Scientific Python Projects.

## Examples

### Example 1: Scipy.org

```yaml
name: Sync Translations
on:
  schedule:
    - cron: '0 12 * * MON'  # Every Monday at noon
  workflow_dispatch:
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Sync Scipy translations
        uses: Scientific-Python-Translations/translations-sync@main
        with:
          # Provided by user
          crowdin-project: "scipy.org"
          source-repo: "scipy/scipy.org"
          source-folder: "scipy.org/content/en/"
          source-ref: "main"
          translations-repo: "Scientific-Python-Translations/scipy.org-translations"
          translations-folder: "scipy.org-translations/content/en/"
          translations-ref: "main"
          translation-percentage: "90"
          approval-percentage: "0"
          use-precommit: "true"
          # Provided by organization secrets
          gpg-private-key: ${{ secrets.GPG_PRIVATE_KEY }}
          passphrase: ${{ secrets.PASSPHRASE }}
          token: ${{ secrets.TOKEN }}
          crowdin-token: ${{ secrets.CROWDIN_TOKEN }}
```

## Automations Bot (@scientificpythontranslations)

[Bot account](https://github.com/ScientificPythonTranslations).

## License

The scripts and documentation in this project are released under the [MIT License](https://github.com/Scientific-Python-Translations/translations-sync/blob/main/LICENSE.txt).
