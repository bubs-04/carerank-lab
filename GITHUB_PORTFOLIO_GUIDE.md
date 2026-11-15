# GitHub Portfolio Guide

Git records versions of files locally. GitHub hosts repositories and makes code review, collaboration and automation available online. A repository contains source files and a `.git` history; a ZIP is a portable snapshot, not a hosted GitHub project.

## Start from this deliverable

Unzip the project and open a terminal inside `carerank-lab`. The archive excludes local credentials, database files, virtual environments and installed dependencies. The working repository was prepared locally; nothing has been pushed to your account.

```bash
git init -b main
# Configure your own identity, preferably GitHub's private noreply email:
git config user.name "Prabhat Mattaparthi"
git config user.email "YOUR_GITHUB_NOREPLY_EMAIL"
git status
# Inspect all files and ignored secrets before staging:
git check-ignore .env
git add .
git diff --cached --stat
git diff --cached
# Only after you have reviewed the contents:
git commit -m "feat: build synthetic provider intelligence lab"
```

A commit is a named snapshot with a message and author. A branch is a movable label pointing to a line of commits. `main` is the stable version; use a feature branch while learning. Never commit a real password, private key, access token, production data or `.env`. Deleting a secret in a later commit does not remove it from history: revoke it and clean history if a leak occurs.

## Publish when you choose

Sign in to GitHub, create a new empty repository named `carerank-lab`, and leave automatic README/license initialization unchecked. Private is useful while finishing browser and Docker verification. Copy the exact URL from GitHub rather than guessing your username.

```bash
git remote add origin https://github.com/YOUR_USERNAME/carerank-lab.git
git remote -v
git push -u origin main
```

This push publishes to the repository you selected. Use GitHub's browser login or credential manager; never paste tokens into source files or remote URLs. If origin already exists, inspect `git remote -v` and use `git remote set-url origin <VERIFIED_URL>` only for the intended destination. For an archive without history, the initialization above is expected.

## Make your first genuine modification

```bash
git switch -c feat/evidence-label
# Complete Exercise 1, then run the tests.
git diff
git add frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat: label limited provider evidence"
git push -u origin feat/evidence-label
```

Open a pull request from that branch into main. A pull request proposes a reviewed change; explain the problem, resulting behavior and test evidence. Inspect the GitHub Actions run. Merge only after the required checks pass. Delete the feature branch when finished and update local main with `git switch main` followed by `git pull --ff-only`.

## Commit messages and review habits

Use concrete verbs and one logical change per commit: `fix: exclude unscored providers from minimum-quality results`, `test: cover failed pipeline rollback`, or `docs: explain synthetic risk adjustment`. Avoid vague messages such as `updates`, fabricated history, and claims that tests passed when they were skipped. Run `git diff --check` before committing.

## Add future projects

Give each substantial project its own repository and README. Explain the user problem, demo workflow, architecture, exact setup, verification and limitations. Pin your strongest three to six projects on your GitHub profile. Keep a short profile README linking to projects and stating your real skills. Small, maintainable projects with working instructions are better evidence than a large collection of copied demos.

## Showcase CareRank Lab honestly

Suggested resume bullet, after you can explain and modify it: “Developed an AI-assisted full-stack provider analytics demo using FastAPI, React and PostgreSQL; generated 100,000 synthetic encounters and implemented specialty-level scoring, transactional ETL and automated tests.” If quoting benchmark numbers, include the environment and measured scope from the report. Never convert a microbenchmark into a production scalability claim.

Suggested LinkedIn text: “I built CareRank Lab with AI coding assistance to learn how a provider analytics product fits together: synthetic data, SQL aggregation, transparent scoring, a typed API and a React interface. I’m working through code modifications and tests so I can explain the engineering decisions. The data and scoring are educational and not clinically validated.” Add the repository URL and screenshots only after you verify them.

## Explain AI assistance

Say which code AI generated, which tests ran, which environment restrictions remained, and which exercises you personally completed. Keep a learning log with dates, diffs and your own explanations. Do not claim that you independently wrote the initial implementation or that Garner reviewed it. A strong answer includes a concrete bug you investigated and a tradeoff you can defend.

## Publication checklist

Verify Docker startup and browser tests on your machine, inspect screenshots, read the security limitations, inspect `git diff --cached`, confirm no secrets or generated database files, and make sure CI passes. Link the Word and Markdown learning materials from the README. Publication is your decision; no upload to GitHub was performed during this build.
