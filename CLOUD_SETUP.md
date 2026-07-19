# Always-on cloud setup

The prepared GitHub Actions workflow runs four times per day, even when the local computer is off. It scans the enabled official sources, emails only new Student/Intern roles, and commits the SQLite history back to the private repository so a job is not emailed twice.

## Security model

- The local `.env` file is ignored and must never be uploaded.
- Only the Gmail App Password is added as the repository secret `SMTP_PASSWORD`.
- GitHub encrypts repository secrets and masks them from ordinary workflow output.
- Use a **private** repository because the saved database contains personal notification history, even though job postings themselves are public.

## Deployment steps

1. Create or sign into a GitHub account.
2. Create a new **private** repository named `hardware-job-monitor`.
3. Upload/push this project, including the current `data/jobs.db`, but excluding `.env` and `logs/`.
4. In the repository, open **Settings → Secrets and variables → Actions**.
5. Create a repository secret named `SMTP_PASSWORD` and paste the 16-character Gmail App Password.
6. Open **Actions → Hardware student job monitor → Run workflow** for the first cloud test.
7. Confirm the run succeeds and no duplicate email is sent.
8. Disable the local Windows task `Hardware VLSI Job Monitor` after the cloud run is verified.

The schedule is intentionally offset from the top of the hour because scheduled GitHub workflows can be delayed during periods of high load.
