---
# iris backlog.
#
# Each task has a stable T### id. Status is one of:
#   open       — ready to work
#   blocked    — has a `blocked_by` field that names what must land first
#   in_progress— currently being worked
#   passed     — verify command returned 0; commit landed
#   skipped    — explicitly marked won't-fix or out-of-scope
#
# /run picks the lowest-id open task whose blocked_by is clear, and
# auto-routes to parallel waves when open tasks are file-disjoint.

tasks:
  - id: T001
    title: "Replace this with your first real task"
    status: open
    priority: 1
    files:
      - "<path/to/file/this/task/touches>"
    notes: |
      One paragraph describing the work. The /submit command appends new
      tasks in this shape; you rarely write this section by hand.

  - id: T002
    title: "A second sample task to show the file-disjoint rule"
    status: blocked
    blocked_by: T001
    priority: 2
    files:
      - "<another/file/this/task/touches>"
    notes: |
      Tasks that share a `files` entry are serialized; tasks with no
      overlap can run together in the same parallel wave.
---

# Backlog notes

Free-form prose under the YAML lives here. Use it for context the YAML
schema can't carry — e.g. release plans, deprecation timelines, the
mental model behind a particular phase.

When you delete this section, /backlog still works — it only reads the
YAML.
