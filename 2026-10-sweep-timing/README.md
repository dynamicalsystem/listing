---
loop: 2026-10-sweep-timing
product: listing
owner: dynamicalsystem
status: Act
parent: null
blocked-by: []
worktrees: [tinsnip/sweep-timing (branch listing-sweep-1830)]
prs: [https://github.com/dynamicalsystem/tinsnip/pull/14]
triggers:
  - when: tinsnip timer-schedule-labels reaches Closed
    then: "replace the hand-edited OnCalendar with the dockerfile LABEL org.dynamicalsystem.timer.maintain and record that the hand edit is redundant"
  - when: 2026-10-sweep-timing has 14 days of 18:30 sweeps recorded
    then: "decide whether Signal push is demonstrably needed (see backlog trigger on push latency); until then an evening reading habit is the assumed delivery"
---

# Sweep Timing

## Status

Act

**Owner:** dynamicalsystem

## Context

Simon's goal is to see a BFI IMAX announcement before tickets go on sale,
not after. The sweep has fired at 02:00 Europe/London since 2026-09-08
("after the BFI day rolls over, before anyone reads the page"). Two failure
modes were named on 2026-10-24: the alert exists at 02:00 but is not read
before a 09:00 on-sale; and a sweep that runs before BFI publishes is
24 hours late. Triggered by a friend's observation that BFI emails arrive
around 17:30 UK. Follows [[2026-09-soak-test]], which showed the 02:00
sweep is reliable but said nothing about when BFI publishes.

## Observations

Evidence gathered 2026-10-24 from the gateway database (copied read-only),
the gateway journal, and a live BFI fetch. Times UTC unless marked UK.

- BFI emails (sample of 2, one subscriber):
  - Godzilla Minus Zero: Thu 2026-10-08, received 17:31 UK.
  - Dune: Part Three: Mon 2026-10-19, received before 18:02 UK (friend's
    text at 18:02 after reading it; the email time itself is unknown). The
    email said tickets go on sale Tue 09:00 UK.
- Godzilla on the website: the Thu 2026-10-08 01:00 sweep scraped the
  Nov 3 page without it and had no Nov 5-12 dates in the horizon; the Fri
  2026-10-09 01:05 sweep found all 24 showings. Site went live within the
  24h containing the email: same-day "on sale now".
- Dune wave 2 on the website: the Dec 18 page had 1 Dune showing at the
  Tue 2026-10-20 01:02 sweep (hash identical to Oct 14) and 5 at the Wed
  2026-10-21 01:04 sweep; 19 showings added across Dec 15/18/19/20. The
  listings appeared on sale day, consistent with the stated 09:00. Nothing
  was visible on the site the evening of the email.
- Dune wave 1 (new dates Dec 16-17, Dec 21 to Jan 7, 19 dates) cannot be
  bounded tighter than Oct 14 01:00 to Oct 23 01:00: every horizon scan in
  between returned HTTP 403.
- The 09:00 on-sale used a virtual queue. Simon clicked at 08:57 UK and
  entered at position ~54000, so the queue forms before the door opens. If
  it is a Queue-it style pre-queue, arrival order before 09:00 is
  randomised and only being present before 09:00 matters; if first-come,
  earlier is better. Either way an alert after 09:00 is too late.
- Publish days since 2026-09-08 (sweep day minus one; "clean" means the
  previous sweep had a working horizon scan):

      Wed Sep 09        1 date                          clean
      Mon/Tue Sep 14-15 4 dates                         Tue sweep 403
      Mon/Tue Sep 21-22 7 dates, 6 showings             Tue sweep 403
      Thu Oct 01        9 dates, 6 showings             clean
      Thu Oct 08        12 dates, 8 showings (Godzilla) clean
      Fri Oct 09        1 date, 4 showings              clean
      Mon/Tue Oct 12-13 2 dates                         Tue sweep 403
      Tue Oct 20        19 showings (Dune wave 2)       clean for showings
      Oct 14-22         19 dates (Dune wave 1)          403 week

  Nothing has ever first appeared over a weekend. Tuesday and Thursday
  dominate.
- BFI's search payload has 98 columns; column 13 is "On Sale Date" and
  column 14 "Sales Status". Both are blank / constant 'S' on all 50 rows of
  a wide query, so BFI exposes no publish or on-sale timestamp.
- Our own data has day resolution only: every scraped_at and detected_at is
  a 01:00 sweep.
- Render-time filtering: the public page, feed and upcoming_showings view
  all filter showing_date >= date('now'), so prune time does not affect
  what subscribers see. The feed window is "scraped in the last 24 hours".
- The timer is not in the listing repo. It is tinsnip
  hosts/gateway/listing-maintain.timer, installed on the box by install.sh
  as ~/.config/systemd/user/listing-maintain.timer, OnCalendar
  "*-*-* 02:00:00 Europe/London", Persistent=true.

## Orientation

Two release types exist and they need different signals:

- "On sale now" (Godzilla): email and site listing on the same afternoon.
  A sweep after ~17:30 UK catches it the same evening. The current 02:00
  sweep catches it too, but Simon reads it after 09:00 next day.
- "On sale tomorrow 09:00" (Dune wave 2): email the evening before, site
  listing only when sales open, and a queue that must be joined before
  09:00. No website sweep at any hour can alert before the door opens. The
  email is the only pre-sale signal. A second sweep at 09:15 was considered
  and rejected: it would report a queue already 54000 deep.

So the website sweep should run once, after the afternoon publish slot, and
the pre-sale signal for queue releases comes from subscribing to the BFI
emails directly. Precision on the publish hour is not needed; an evening
sweep is after it in every observed case.

Moving the sweep also moves it off 01:00 UTC, where every 403 streak has
started (Sep 15, Sep 19, Sep 22, Oct 13, Oct 15-22; three of the four
isolated days are Tuesdays). That may be coincidence; the loop will measure
the 403 rate at the new time against the 01:00 baseline (3 of 30 days in
the soak window; 8 of 10 in the Oct 13-22 streak).

Cost of the change: feed items surface ~16.5 hours earlier than subscribers
are used to; no guid, URL or payload change, so not a breaking change under
the ask-first rule for live interfaces. The health endpoint's oldest_listing
will lag until 18:30 each day (cosmetic; render-time filtering hides the
stale rows). The "before anyone reads the page" rationale for 02:00 is
superseded: the page filters by date at render time, so there is nothing
for an early sweep to tidy.

## Decision

Decided 2026-10-24 by Simon:

1. Move the single daily sweep to **18:30 Europe/London**. One sweep, not
   two.
2. Simon subscribes to the BFI emails for the on-sale-tomorrow case. No
   system change for that signal.
3. Do not unpark Signal push yet. Run 14 days of 18:30 sweeps first and
   see whether an evening reading habit covers delivery (trigger above).
4. At the next big release, check whether the website carries any pre-sale
   signal the search results do not (whatson homepage banner, booking-flow
   holding page). Knowledge outcome; decide afterwards whether it is worth
   scraping.
5. (2026-10-24, later) The sweep time is product knowledge but lives in
   tinsnip. Agreed direction: the product declares its schedule as an OCI
   image label and tinsnip renders the timer drop-in. That is the tinsnip
   loop timer-schedule-labels (tinsnip control plane). It does not block
   this loop: the 18:30 change ships as a direct edit first and the label
   supersedes it when that loop closes (trigger above).

## Action

2026-10-24: tinsnip PR opened, https://github.com/dynamicalsystem/tinsnip/pull/14 (branch listing-sweep-1830,
worktree ~/work/tinsnip/sweep-timing). On-box restart remains Simon's step.

Plan:

- tinsnip: change hosts/gateway/listing-maintain.timer OnCalendar to
  "*-*-* 18:30:00 Europe/London" and the Description/comment; PR to main.
- On box (Simon, ask-first since it is the live system): git pull,
  install.sh or daemon-reload, `systemctl --user restart listing-maintain.timer`,
  confirm `systemctl --user list-timers listing-maintain.timer` shows the
  next elapse at 18:30 UK. Persistent=true means a missed firing runs at
  boot, so no gap on the switch-over day; the 02:00 firing on the day of
  the change should be allowed to happen before the restart.
- Record the first 18:30 exit code and the journal 403 count here.
- Follow-on: tinsnip timer-schedule-labels replaces the hand edit with
  LABEL org.dynamicalsystem.timer.maintain="*-*-* 18:30:00 Europe/London"
  in the listing dockerfile.

## Outcomes

### Outcome 1: Same-day BFI publishes reach the feed the same evening

Tests:
- [ ] listing-maintain.timer next-elapse is 18:30 Europe/London and the
      first 7 sweeps at the new time exit 0
- [ ] The first "added" or new-date detection after the switch corresponds
      to a BFI publish that day (cross-checked against a BFI email where one
      exists), not one from the day before

### Outcome 2: Nothing subscribers rely on regresses

Tests:
- [ ] Public page shows no past-dated showings when checked between
      09:00 and 18:00 UK (before the sweep has pruned)
- [ ] /health reports healthy with last_scrape within 24h on day 14
- [ ] 403 rate over the first 14 days at 18:30 recorded alongside the
      01:00 baseline (3/30 and 8/10) and the Tuesday pattern checked

### Outcome 3: We know whether the website carries a pre-sale signal

Tests:
- [ ] At the next on-sale-tomorrow release, the whatson homepage and the
      film's booking flow are snapshotted the evening before and the
      result (signal or none) is recorded here
