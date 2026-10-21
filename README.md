# MR-GULLO Classroom tester preview

Install on Windows or Mac: https://mr-gullo.github.io/mr-gullo-classroom/

Open in Chrome on Mac or Edge/Chrome on Windows. Allow the first load to finish, then choose the browser's install command. The app can work offline after its assets are cached. Safari and Windows still need platform verification.

This is an unlisted public tester preview. Anyone can access or forward the link. Search-engine exclusion is requested, but it is not an access restriction. Please share directly with invited testers during this stage.

This repository contains only the built web app and distribution metadata. Source history and teacher workspaces are not included. Classroom records stay in each browser's local workspace. Export private backups before changing browser, computer, or website address. Never post backups or student data in GitHub issues.

Version history and hosting downloads: https://github.com/MR-Gullo/mr-gullo-classroom/releases

The release ZIP is a static hosting bundle for the same app on both platforms. It is not a Windows or Mac executable installer. A downloaded index.html cannot be used directly from disk.

Current channel: 0.1.0-rc.1 tester prerelease. This is not production sign-off. See each release's verification limits.

## Updates and rollback

App changes do not deploy on push. Use the manual [Tester update workflow](https://github.com/MR-Gullo/mr-gullo-classroom/actions/workflows/tester-pages.yml). Its default is verification only. Promotion and rollback both require the owner's environment approval. Read [UPDATES.md](UPDATES.md) for candidate testing, exact artifact checks, and the rollback procedure. Never approve an update without its checks and private fictional-data QA.

The live app remains v0.1.0-rc.1 until a reviewed candidate is promoted. Downloaded ZIPs and their tested receipts are retained in Releases, so rollback does not rebuild old code or rewrite Git history. Database migration recovery remains a separate requirement.
