# CLAUDE.md — softmax.com website

## Setup

Make sure that the monorepo top-level `./install.sh` script has already been run, before making changes to the website.

If you don't have the `metta` command, it has not been. It's necessary for the development loop, and will also install precommit hooks.

## Development

To bring up the site locally, run:
`metta dev softmax-com --backend local`

For first-time setup in a fresh local environment:

- start Postgres: `metta dev postgres up -d`
- run migrations: `metta dev softmax-com-db-migrate`
