---
name: assess-n1-security
description: Use when a dispatch plan must be checked for surviving a single element outage, because a plan that is feasible in the intact network can still be unsafe the moment one branch trips.
metadata:
  version: 1.0.0
---

# Assess N-1 security

## When to use this

The base case passes and the question is whether the plan survives a single contingency.

## Steps

1. Declare the outages explicitly in the study's `outages` array. Each entry names a `branchId`
   to take out of service. The engine does not enumerate the credible contingency list for
   you, because that list is a judgement about which elements matter.

2. Run `loadcurve verify <study.json>` and read the N-1 section.

3. Sort the findings by status. Three statuses, and the distinction is operational rather than
   cosmetic:
   - `secure` — the plan survives with headroom to spare.
   - `violated` — a limit is breached on the outaged network. The entry carries its own core,
     computed on the post-contingency topology, so it may name different limits than the base
     case.
   - `islanded` — dropping that branch split the network, so no DC power flow exists at all.
     An islanded feeder is a supply-continuity problem, not a loading problem, and it must be
     escalated differently.

4. Report `baseFeasible` alongside the screen. "Feasible, but not secure under N-1" is the
   common and important result; a screen that omits the base-case verdict hides it.

5. For any `violated` outage, run `loadcurve explain` on a study carrying that single outage to
   get the cheapest fix for the post-contingency case specifically.

## Watch for

Radial networks island under almost any outage. If every outage reports `islanded`, the model is
a lateral with no loop and the N-1 question is really a reconfiguration question. Say that
rather than reporting a screen that found nothing but islanding.

## Verify

The screen counts reconcile: `secure + violated + islanded` equals the number of distinct
outages screened. Duplicate `branchId` entries are collapsed, so count distinct branches rather
than assuming the array length matches.
