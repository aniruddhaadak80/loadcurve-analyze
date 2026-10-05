# Tenets

Short, checkable principles. A change that violates one of these needs a better argument than
taste.

1. **One waist.** Every capability is a `Tool` in one registry. A second code path is a bug even
   when it works.

2. **Deterministic where it matters.** Anything that must be exactly right is code, not a model
   call. There is no provider abstraction to reach for. See
   [ADR-0004](docs/adr/0004-no-model-in-the-analysis-path.md).

3. **A proof or an admission, never a plausible answer.** `infeasible` means propagation drove a
   domain empty. A core is _verified_ minimal before it is returned. When no conclusion is
   possible the answer is `undetermined`, not a guess.

4. **Report, never silently skip.** A skill that fails to load, a plugin that is rejected, a tool
   that is shadowed — all reported, with the reason. Silent failure is how a product becomes
   unexplainable.

5. **Exactness is a design constraint, not an aspiration.** Every constraint is a linear form,
   so attainable ranges are computed rather than bounded. Adding a nonlinear constraint kind
   would make the core claim unsound; that is a design change, not an optimisation.

6. **Omission is a decision.** A surface left out is recorded with its reason. A surface left out
   silently is indistinguishable from one that was forgotten.

7. **Reproducible beats live.** A study must give the same answer years later on another machine.
   The deployed demo shows a _recorded_ result and says so, rather than a live number that would
   require a second execution environment.

8. **Content-address what matters.** Two analysts who independently produce the same inputs get
   the same study id. "Did you run the same study?" is answerable without trusting filenames.

9. **Ratchet, do not crusade.** Lint debt is baselined and frozen. Fixing debt is good; blocking
   a PR on unrelated debt is not.

10. **Earn the README.** Every command in it was run and its real output pasted. No aspirational
    commands, no invented badges, no benchmark numbers nobody measured. `check:readme-commands`
    keeps this true.
