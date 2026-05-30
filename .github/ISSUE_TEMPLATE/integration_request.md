---
name: New integration
about: Propose an adapter for a new medium (Discord, Teams, queue, etc.)
labels: integration
---

## Medium

(Discord, MS Teams, email, RabbitMQ, ...)

## Why

What workflow does this unlock?

## API surface you'll wrap

The five `client.py` shape verbs: notify, get-status, get-tasks, get-
handover, start-headless-run. Mark any that don't fit the medium.

## Auth model

How does the medium authenticate? Token? OAuth? mTLS?

## Are you willing to write the PR?
