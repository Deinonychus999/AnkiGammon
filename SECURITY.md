# Security policy

## Reporting a vulnerability

If you discover a security vulnerability in AnkiGammon, please report it privately so that a fix can be prepared before the issue is disclosed publicly.

**Preferred channels** (use whichever you prefer):

- **GitHub Private Vulnerability Reporting** — open a private advisory at <https://github.com/Deinonychus999/AnkiGammon/security/advisories/new>. This creates a private discussion thread where the fix can be developed before public disclosure.
- **Email** — send a report to **admin@ankigammon.com** with the subject line *"Security: <short description>"*.

Please include:

- A description of the vulnerability and the impact you believe it has.
- Steps to reproduce, ideally with a minimal example (a sample file, a position string, or a sequence of UI actions).
- The version of AnkiGammon you tested against (visible in the application title bar).
- Your operating system and Python version, if relevant.

You will receive an acknowledgement within **7 days**. We aim to provide an initial assessment and a tentative fix timeline within **30 days** of the report.

## Scope

In scope:

- The AnkiGammon application code in this repository.
- The GitHub Actions workflows used to build and release official binaries.
- The PyInstaller spec used to bundle the official binaries.

Out of scope:

- Vulnerabilities in third-party dependencies (please report those upstream — we will track and ship updated dependencies in our own releases as appropriate).
- The eXtreme Gammon, GNU Backgammon, or OpenGammon analysis engines themselves.
- Local Anki / AnkiConnect — please report to the relevant upstream projects.

## Supported versions

Security fixes are applied to the latest released version. Users on earlier versions are encouraged to update via [GitHub Releases](https://github.com/Deinonychus999/AnkiGammon/releases) or `pip install --upgrade ankigammon`.

## Coordinated disclosure

Please give us a reasonable opportunity to release a fix before disclosing the vulnerability publicly. Once a fix has been released, you are welcome to publish your findings; we will credit reporters in the release notes unless anonymity is requested.
