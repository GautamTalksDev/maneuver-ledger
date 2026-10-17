# Security policy

Maneuver Ledger publishes research numbers and a static page. People may quote them, so their integrity is part of
its security. Please report anything that could change what this repository publishes, run code in a reader's
browser, or misuse the project's CI.

## Reporting a vulnerability

**Please do not open a public issue.**

* Preferred: [report privately through GitHub](https://github.com/GautamTalksDev/maneuver-ledger/security/advisories/new)
  (Security tab, "Report a vulnerability").
* Or email developwith.gt@gmail.com with "Maneuver Ledger security" in the subject.

Include what you found, how to reproduce it, and what an attacker could do with it.

## What to expect

| Step | Target |
|---|---|
| Acknowledgement | within 3 days |
| First assessment | within 7 days |
| Fix or mitigation for high or critical issues | within 30 days |
| Public advisory and credit (if you want it) | when the fix ships |

The project is maintained by one person, so these are best-effort targets, but they are taken seriously.

## In scope

* The GitHub Actions workflow: injection, token or permission misuse, anything that could alter the repository.
* The pipeline: a crafted input file (a DODGE day file, a CelesTrak download) that causes code execution, or that
  passes the SHA-256 checks while changing the results.
* The results page (`site/index.html`, and the copy under dodge.gautamkhosla.com/ledger/): anything that runs code in
  a reader's browser.
* `tools/reproduce.sh`: anything that makes it trust an input it should not.

## Out of scope

* Whether a number is right. That is a method question: open an issue, ideally with the satellite and the date.
* CelesTrak, DODGE's own infrastructure, GitHub and Cloudflare. Report those to their owners (DODGE:
  [its security policy](https://github.com/GautamTalksDev/dodge/security/policy)).
* Findings from automated scanners without a demonstrated impact.

## Safe harbour

Good-faith research that respects this policy is welcome. Do not access data that is not yours, do not degrade
services for others, and give a reasonable time to fix before you publish. If you follow these rules, the maintainer
will not pursue or support legal action against you.

## How the repository is protected

* No secrets: the code needs no keys, the workflow uses only the read-only `GITHUB_TOKEN`
  (`permissions: contents: read`), and `persist-credentials: false` keeps it out of the checkout.
* Every third-party action is pinned to a full commit SHA; Dependabot proposes updates after a 7 day cooldown.
* Dependencies are installed with `pip --require-hashes --no-deps` from a hash-pinned `requirements.txt`.
* Inputs are checked against DODGE's sealed SHA-256 manifests, and the committed results' inputs against
  `data/inputs-2026-10-17.sha256`.
* The page has no scripts and no third-party resources; its Content Security Policy allows only its own styles.
* Secret scanning with push protection, private vulnerability reporting and a protected `main` branch are enabled in
  the repository settings.
