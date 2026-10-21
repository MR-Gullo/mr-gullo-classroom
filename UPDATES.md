# Safe tester updates

The permanent tester address is
https://mr-gullo.github.io/mr-gullo-classroom/.
The distribution repository contains built files and release tooling only.
Never push the local application source history, student records or private QA
evidence into it.

## What prevents accidental updates

GitHub Pages uses the manually started **Tester update** workflow, not branch
publishing. Ordinary commits and release creation do not deploy an app.
The default action is **verify**, which cannot deploy. **Promote** and **rollback**
both stop for MR-Gullo's approval in the `github-pages` environment. Agents must
leave that approval to the user. The environment permits only `main` and disables
administrator bypass. Self-review is allowed so the owner can approve a workflow
they started.

Candidates are built from a fixed local source commit in an isolated worktree.
Preparation runs the release guard tests, the full `npm run check` suite and
packaging checks. A receipt binds these results to the exact ZIP, all its files
and its source commit. GitHub checks the receipt, ZIP hashes, file allowlist,
archive safety, permanent URL and manual QA before accepting an artifact.
It treats the downloaded ZIP as data and does not execute its scripts.
Full source tests run locally; GitHub does not have the private source repository.
Receipts record the release operator's checks and are not independent proof that
a privileged maintainer honestly performed every test.

Updates are serialized. A deployment rechecks the live ZIP hash after approval,
so a candidate reviewed against an older live build cannot overwrite a newer one.
Actions are pinned to exact commits. Deployment permission is confined to the
approval-gated deployment job.

## Prepare and review a candidate

1. Coordinate with active source owners. Integrate their accepted commits safely.
   Keep the shared index free of unrelated files. Choose a committed source ref;
   dirty working files are deliberately excluded from candidate builds.
2. From the source project, run:

   ```sh
   python3 scripts/tester-release.py prepare --ref <source-commit> --tag v0.1.0-rc.2
   ```

   This creates `release/candidates/v0.1.0-rc.2/`. It does not upload or deploy.
   Logs and the isolated worktree stay in `.scratch/tester-release-v0.1.0-rc.2/`.
   A failure retains its evidence. Use a fresh tag for a revised candidate.
3. Preview the exact packaged files:

   ```sh
   python3 scripts/tester-release.py preview --candidate release/candidates/v0.1.0-rc.2
   ```

   Open `http://127.0.0.1:1460/mr-gullo-classroom/` in the in-app browser.
   Use fictional data and an isolated origin. To test update and rollback,
   serve the old and new packages in sequence at this SAME origin, stopping the
   old preview server before starting the next. A fresh empty origin alone does
   not test existing-data compatibility. Preserve real1431/1435 workspaces.
4. Verify common tasks, keyboard/Undo, import/export, backup/restore, offline
   restart and an update with populated existing data. Then reopen the previous
   version against the updated fictional workspace and check its data readback.
   Record useful screenshots and observations privately. Check platform-specific
   changes on the affected platforms, or retain a clearly stated release hold.
5. Complete the generated private `qa-template.json`. Its SHA, source commit and
   rollback target must match this artifact. Change each check to true only after
   observing it. Keep supporting evidence alongside it. Record the attestation:

   ```sh
   python3 scripts/tester-release.py attest \
     --candidate release/candidates/v0.1.0-rc.2 \
     --evidence .scratch/tester-release-v0.1.0-rc.2/qa-template.json
   ```

   Only check results and an evidence fingerprint enter the public receipt.
   The raw QA file, browser data and logs stay local. The hash is not a backup.
6. Write concise public release notes with no student information, then stage:

   ```sh
   python3 scripts/tester-release.py stage \
     --candidate release/candidates/v0.1.0-rc.2 \
     --notes <reviewed-public-notes-file>
   ```

   This creates a draft prerelease with the ZIP and receipt. It does not update
   Pages. Failed uploads must be inspected; do not overwrite or reuse a published
   tag to repair a changed artifact.

## Promote to testers

1. Open https://github.com/MR-Gullo/mr-gullo-classroom/actions/workflows/tester-pages.yml.
2. Choose **Run workflow**, branch `main`, action **verify**, and the exact tag.
   Wait for success. Inspect its SHA, source commit and check summary.
3. Read the current `sha256` at
   https://mr-gullo.github.io/mr-gullo-classroom/version.json.
4. Start the workflow again with action **promote**, the same tag and that exact
   current live hash. This checks the candidate again before asking for approval.
5. The user reviews the concrete candidate and approves the waiting
   `github-pages` deployment in GitHub. Do not approve deployments on their behalf.
6. The job deploys the already verified artifact, checks the public version
   marker and publishes the candidate as a prerelease in version history.
   Check a real browser after deployment. Existing installed apps receive the
   app's normal update prompt; offline clients can remain on cached versions
   until they reconnect and accept an update.

## Roll back

Release ZIPs and receipts remain in GitHub Releases. Rollback does not rebuild
old source, force-push Git history or depend on expiring Actions artifacts.

1. Read the current public version marker and find its `rollbackTo` ZIP hash.
   Find the earlier release matching that hash. The initial known-good release
   is `v0.1.0-rc.1`, ZIP SHA-256
   `2dfe1a22b51163eb4959c1548030187f33d579ecfb841ee9141e0c3dd9ace77f`.
2. Start **Tester update** with action **rollback**, the earlier tag and the
   CURRENT live ZIP hash as `expected_live_sha`.
3. The workflow verifies the old archive and that the current release attested
   data-safe rollback to it. The user approves the concrete rollback in GitHub.
4. Check the live marker and app. Tell testers to reconnect and accept the update.
   Keep their local data intact. Never clear site storage as a rollback step.

Restoring old app files does not undo a data migration. A release that cannot
demonstrate prior-version readback must not be promoted through this workflow.
It needs a separate, reviewed recovery plan with private backups first. This
pipeline does not automatically back up teacher devices or roll back the
invitation-only staff hub's server database.

## Separate staff-hub hosting

The optional staff hub at `mr-gullo-classroom.joelhgullo.chatgpt.site` is a
distinct hosted origin with separate local browser storage and deployment rules.
Its invitation-only server and database require their own checks and recovery
plan. Do not redirect the GitHub tester URL to that origin or assume its
deployments update the GitHub PWA. Teachers move local workspaces between origins
only through a private backup export/import.

## Maintenance

The source copies under `scripts/tester-updates/` own the workflow and verifier. Publish
reviewed tooling changes to `.github/workflows/tester-pages.yml` and
`release-tools/verify_bundle.py` in the distribution repository. The trusted
baseline file is generated once from the independently checked original release.
Do not edit baseline hashes or remove environment protection to make a failing
candidate pass. Repository administrators can still change repository policy;
these controls prevent routine mistakes, not a malicious account administrator.
