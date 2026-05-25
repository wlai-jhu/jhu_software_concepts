Robots.txt Evidence Explanation

This folder contains evidence that Grad Cafe's robots.txt file was checked before
scraping public applicant result pages.

Files:
- robots_check.txt: the robots.txt text fetched programmatically with urllib by running:
  python scrape.py --check-robots-only
- screenshot.jpg: a browser screenshot of the same public robots.txt page.

The screenshot.jpg file documents the visual browser check of:
https://www.thegradcafe.com/robots.txt

The saved robots.txt content shows a User-agent: * section with Allow: /, which permits
public pages generally. It also lists disallowed private/account-related paths, including
/signin, /register, /forgot-password, /reset-password, /confirm-password, /verify-email,
and /profile. The scraper targets the public survey/results pages only and does not scrape
login-protected, account, profile, CAPTCHA, or restricted pages.

The scraper also checks robots.txt in code before scraping. If robots.txt does not permit
the configured target URL, scrape.py raises a PermissionError and stops instead of
collecting data.
