# Goals (draft, for the operator to accept or rewrite)

The `goals` ledger holds 0 rows, so `Goals.md` is empty and the two are in sync.
That is the honest state, and it has been the state since day one. This draft is
what I would put in the ledger if writing goals were mine to write. It is not
recorded: a goal is the operator's call, and the Nov 5 escalation on this is
still parked.

Everything below is grounded in evidence the company actually gathered on
2026-11-07 to 2026-11-10, not in what sounds good.

## 1. Every daily pass observes something outside the loop

**Measure:** each day's `signals` row contains at least one reading from an
external source (GitHub org, CoinGecko), with the endpoint and the numbers
quoted. A pass that produces no signal row counts as a miss.

**How you would know it failed:** a day with no signal row, or a row whose only
subject is the board and the ledgers. That was 55 of the first 56 rows.

**Why this shape:** it can fail visibly, it is checkable from the ledger alone,
and it asks for nothing the bot cannot already do with a `User-Agent` header.

## 2. The org's shipping pace is a series, not a snapshot

**Measure:** consecutive daily readings of `tinyhumansai/openhuman` stars, forks,
open issues and open PRs (from the search endpoints, not `open_issues_count`),
plus the count of org repos pushed since the previous pass. Baseline 2026-11-10:
42,619 / 4,214 / 331 issues / 35 PRs, 6 repos pushed on Nov 9.

**How you would know it failed:** a gap in the series, or a reading with no
previous day to compare against. Four data points exist (Nov 7 to Nov 10). A
reading that treats an issue jump as demand should also count as a miss: the
+33 on Nov 10 was 40 Sentry triage issues filed by one member, not users.

## 3. At least one learning becomes a change to the definition

**Measure:** rows in the `changes` ledger. It has held 0 rows for 56 days while
`learnings` grew to 14 open / 3 closed. The specific first candidate is the retry
policy: three identical `http_request` retries of a request that can only fail
the same way cost the Nov 8 pass its entire output.

**How you would know it failed:** another 30 days with `changes` still at 0.
The failure mode this goal exists to catch is a company that learns fluently and
changes nothing.

## 4. The board's count means what it says

**Measure:** the number of cards in `pending` equals the number of genuinely
open tasks. Today it reads 8, and two of those are one task written twice
(`set-the-first-goals` and `write-the-first-goals`, same done-condition, both
high priority), while `run-the-first-reflect` has met its own done-condition
since 2026-09-15 and still shows pending. So the real figure is 6.

**How you would know it failed:** a pass report that quotes "8 pending" without
saying two of them are duplicates and one is already done. That has happened
every day for two months.

## What I deliberately did not include

- Anything about the $TINY price. A $247,791 market cap with $25,998 of daily
  volume is the mascot's number, not the work's, and a goal aimed at it would
  push the bot toward price talk it has no business doing. The org shipped to
  6 repos on Nov 9 on the same morning the token was down 36.18% on the week.
- Anything requiring wallet actions, a second token, or numbers recalled from
  memory. Every figure above is copied from a tool result on the date shown.
