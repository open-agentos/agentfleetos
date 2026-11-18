# Lesson eval cases

Every lesson ships with an eval case (GOV-0032), and the replay gate (#1189, FEAT-19; `launcher/rehearsal.py`) won't let a lesson go active until its case passes. The librarian drafts a case when it proposes a lesson, as `evals/lessons/L-NNNN.toml`, and names it in the lesson's `eval_case`.

A case is a past task from the lesson's source episodes (an issue and the repo at that commit), the behaviour the lesson should change, and a check for it:

```toml
lesson = "L-0007"                       # the lesson it tests
repo = "open-agentos/agentfleetos"      # whose clone the task replays in
commit = "<40-character sha>"           # the repo as the session found it
issue = 1150                            # the task's issue (optional)
episodes = ["<episode id>", "..."]      # the source episodes it comes from
behaviour = "What the lesson should change, in one sentence."
task = """
The task as the session got it, in plain words. Say which file to write if the check reads one.
"""

[check]                                 # every line given must hold
reply_matches = ['regex']               # the replay's final reply matches each
reply_lacks = ['regex']                 # ... and none of these
diff_matches = ['regex']                # the diff of everything it changed matches each
diff_lacks = ['regex']
changed = ['glob']                      # some changed path matches each glob
unchanged = ['glob']                    # no changed path matches any of these
```

Patterns are Python regular expressions matched line by line (`re.M`). Globs work as a lesson's `paths` do: `**` crosses directories. A check only reads what the replay left behind and never runs code from the case.

**Write a check that fails without the lesson.** The gate promotes a lesson only if its case fails without it and passes with it, or passes both ways at no extra cost. A check that anything passes proves nothing. Replays don't read `CLAUDE.md` (they run with `--bare`), but they can open any file in the repo. So the check should test what the lesson adds, not something the repo already says.

`evals/lessons/drill/` holds the planted-correction drill's lesson and case (`evals/drills.md`). It isn't a real lesson: it sits outside `memory/lessons/` and is rehearsed only with `--store`.
