# ff3_importer
Convert financial info into categorized csv for use in firefly3 to gain clarity on one's spending.

- Uses Selenium to pull data from websites
- chatgpt to translate and categorise payments
- pandas to transform data & manipulate csvs
- needs docker installed to upload to firefly3

The bank downloader waits for visible sign-on controls and the named Download
Account Activities link. It retries only explicit Access Denied pages; an unknown
login result stops the run so a verification prompt or login error does not cause
repeated credential submissions. Denial retries use exponential backoff with up
to five seconds of jitter. These settings can be supplied in the job environment:

| Setting | Default | Allowed range |
| --- | --- | --- |
| `BANK_LOGIN_ATTEMPTS` | 2 | 1–4 |
| `BANK_LOGIN_RETRY_SECONDS` | 60 | 30–600 |
| `BANK_PAGE_TIMEOUT_SECONDS` | 45 | 1–300 |
| `BANK_DOWNLOAD_TIMEOUT_SECONDS` | 120 | 1–600 |

The downloader imports only a new or changed, nonempty completed CSV from the
current download attempt. It does not log login values, page contents, or full
bank URLs. An Access Denied result still requires checking normal browser access;
these changes do not guarantee acceptance of browser automation by the bank.

todo

- fix cc selenium automation
- stop using sleep and use native selenium waits
- better error notification
- webhooks for particular transactions/notifications based on custom transactions
- 

