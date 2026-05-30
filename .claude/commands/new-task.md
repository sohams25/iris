---
description: Scaffold a new task folder under $PROJECTS_DIR/<N>_<kebab-name>/ (default Projects/) with a template populated by the latest handover context.
---

The user wants to start a new task area. Their input is:

    $ARGUMENTS

(Expected: a kebab-case slug like `bot-52-acceptance` or a free-form title
that you should slug yourself.)

Do this end-to-end with shell + Edit only:

0. **Resolve the projects directory.** Read `PROJECTS_DIR` from the
   environment; if unset, parse it from `.env` (a line starting
   `PROJECTS_DIR=...`); if still unset, default to `Projects`. Treat the
   resolved value as a path **relative to the workspace root**. Create
   the directory with `mkdir -p` if it does not exist; the user has
   declared the directory name even if they have not populated it yet.
1. **Validate the slug.** If `$ARGUMENTS` is empty, ask the user for a
   name once and stop. Otherwise, normalise: lowercase, replace
   whitespace/underscores with `-`, strip non-`[a-z0-9-]`, max 50 chars.
2. **Compute the next index** by scanning existing
   `$PROJECTS_DIR/*` directories for a leading `<N>_` prefix. The new
   task gets `max(N)+1`, zero-padded to one digit (so `1_…`, `2_…`,
   etc.). If the directory is empty, start at `1_`.
3. **Create the structure:**

   ```
   $PROJECTS_DIR/<N>_<slug>/
   ├── README.md
   ├── docs/
   │   ├── summaries/.gitkeep
   │   └── reports/.gitkeep
   └── archive/.gitkeep
   ```

4. **Populate `README.md`** using this template. Fill in the bracketed
   placeholders from context: the slug for the title, the current
   handover's title as a starting prompt, today's date.

   ```markdown
   # <Title cased from slug>

   _Created <YYYY-MM-DD>. Active handover at session start:
   `<current handover id>`._

   ## Overview

   _One paragraph: what is this task, why does it exist, what is the
   success state? Replace this stub before the first session ends._

   ## Goals

   - _<Goal 1>_
   - _<Goal 2>_

   ## Status

   | Date | Status | Notes |
   |---|---|---|
   | <YYYY-MM-DD> | scaffolded | _Initial creation_ |

   ## Layout

   ```
   .
   ├── docs/
   │   ├── summaries/  ← narrative writeups (one document per decision)
   │   └── reports/    ← timestamped point-in-time output
   └── archive/        ← read-only originals once they get superseded
   ```

   ## Links

   - Related handover: `/memory current`
   - Related backlog tasks: see `docs/plan.md`

   ## Conventions

   - New analysis writeup with a conclusion → `docs/summaries/`
   - New validation run output → `docs/reports/<name>_<ISO8601_UTC>.md`
   - Read-only artefacts → `archive/`
   ```

5. **Confirm.** Print the created path and the next likely action:

   ```
   created $PROJECTS_DIR/<N>_<slug>/
   open README.md to fill in Overview + Goals, then submit your first
   task with /submit "<short description>".
   ```

Do NOT commit. Do NOT modify `docs/plan.md`. Do NOT touch the obsidian
vault. This command only scaffolds the directory.

Note for plugin packaging: the default `PROJECTS_DIR=Projects` is the
convention iris ships. A consumer sets the variable to whatever name fits
their repo (`Tasks`, `Work`,
`Initiatives`, etc.). The variable is the only thing that points at the
project-area root; the slash command, the README template, and the
scaffolding logic all read it.
